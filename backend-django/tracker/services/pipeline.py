"""
Pipeline orchestrator: geocode, fetch imagery, run detection.

This is the one service that needed significant changes from the FastAPI
version because it replaces raw SQL queries with Django ORM calls.
"""
import asyncio
import json
from datetime import datetime
from typing import Awaitable, Callable, Optional

from asgiref.sync import sync_to_async
from django.conf import settings

from tracker.services.detector import batch_detect
from tracker.services.geocoder import batch_geocode
from tracker.services.imagery import batch_fetch_imagery

PipelineEmitter = Optional[Callable[[dict], Awaitable[None] | None]]


def _now_iso() -> str:
    return datetime.now().isoformat()


async def _emit(emitter: PipelineEmitter, event: dict):
    if not emitter:
        return
    maybe_coro = emitter(event)
    if asyncio.iscoroutine(maybe_coro):
        await maybe_coro


def _init_totals():
    return {
        "geocode": {"attempted": 0, "processed": 0},
        "imagery": {"attempted": 0, "processed": 0},
        "detection": {"attempted": 0, "processed": 0},
    }


@sync_to_async
def _get_ungeocoded(limit: int) -> list[dict]:
    from tracker.models import Property
    qs = Property.objects.filter(latitude__isnull=True).values("id", "address")[:limit]
    return list(qs)


@sync_to_async
def _update_geocoded(prop_id: int, lat: float, lng: float, formatted_address: str):
    from tracker.models import Property
    Property.objects.filter(pk=prop_id).update(
        latitude=lat,
        longitude=lng,
        formatted_address=formatted_address,
        geocoded_at=datetime.now(),
    )


@sync_to_async
def _get_needs_imagery(limit: int) -> list[dict]:
    from tracker.models import Property
    qs = Property.objects.filter(
        latitude__isnull=False, imagery_fetched_at__isnull=True,
    ).values("id", "address", "latitude", "longitude")[:limit]
    return list(qs)


@sync_to_async
def _update_imagery(prop_id: int, result):
    from tracker.models import Property
    Property.objects.filter(pk=prop_id).update(
        streetview_path=result.streetview_path,
        streetview_available=result.streetview_available,
        streetview_date=result.streetview_date,
        satellite_path=result.satellite_path,
        imagery_fetched_at=datetime.now(),
    )


@sync_to_async
def _get_needs_detection(limit: int) -> list[dict]:
    from tracker.models import Property
    qs = Property.objects.filter(
        imagery_fetched_at__isnull=False, detection_ran_at__isnull=True,
    ).values("id", "streetview_path", "satellite_path")[:limit]
    return list(qs)


@sync_to_async
def _update_detection(prop_id: int, result):
    from tracker.models import Property
    Property.objects.filter(pk=prop_id).update(
        detection_score=result.score,
        detection_label=result.label,
        detection_details=result.details,
        detection_ran_at=datetime.now(),
    )


async def _run_geocode_step(
    limit: int, cycle: int, emitter: PipelineEmitter,
) -> dict:
    rows = await _get_ungeocoded(limit)
    total = len(rows)
    await _emit(emitter, {"step": "geocode", "status": "started", "total": total, "cycle": cycle})

    if not rows:
        done = {"attempted": 0, "processed": 0, "message": "All geocoded"}
        await _emit(emitter, {"step": "geocode", "status": "done", "cycle": cycle, **done})
        return done

    async def on_result(_address, _result, current, count):
        await _emit(emitter, {"step": "geocode", "status": "progress", "current": current, "total": count, "cycle": cycle})

    geo_results = await batch_geocode(
        [row["address"] for row in rows],
        concurrency=settings.GEOCODE_CONCURRENCY,
        on_result=on_result,
    )

    processed = 0
    for row in rows:
        result = geo_results.get(row["address"])
        if not result:
            continue
        await _update_geocoded(row["id"], result.lat, result.lng, result.formatted_address)
        processed += 1

    done = {"attempted": total, "processed": processed}
    await _emit(emitter, {"step": "geocode", "status": "done", "cycle": cycle, **done})
    return done


async def _run_imagery_step(
    limit: int, cycle: int, emitter: PipelineEmitter,
) -> dict:
    rows = await _get_needs_imagery(limit)
    total = len(rows)
    await _emit(emitter, {"step": "imagery", "status": "started", "total": total, "cycle": cycle})

    if not rows:
        done = {"attempted": 0, "processed": 0, "message": "All imagery fetched"}
        await _emit(emitter, {"step": "imagery", "status": "done", "cycle": cycle, **done})
        return done

    async def on_result(_prop_id, _result, current, count):
        await _emit(emitter, {"step": "imagery", "status": "progress", "current": current, "total": count, "cycle": cycle})

    img_results = await batch_fetch_imagery(
        rows,
        concurrency=settings.IMAGERY_CONCURRENCY,
        on_result=on_result,
    )

    processed = 0
    with_imagery = 0
    for row in rows:
        result = img_results.get(row["id"])
        if not result:
            continue
        await _update_imagery(row["id"], result)
        processed += 1
        if result.streetview_available or bool(result.satellite_path):
            with_imagery += 1

    done = {"attempted": total, "processed": processed, "with_imagery": with_imagery}
    await _emit(emitter, {"step": "imagery", "status": "done", "cycle": cycle, **done})
    return done


async def _run_detection_step(
    limit: int, cycle: int, emitter: PipelineEmitter,
) -> dict:
    rows = await _get_needs_detection(limit)
    total = len(rows)
    await _emit(emitter, {"step": "detection", "status": "started", "total": total, "cycle": cycle})

    if not rows:
        done = {"attempted": 0, "processed": 0, "message": "All analyzed"}
        await _emit(emitter, {"step": "detection", "status": "done", "cycle": cycle, **done})
        return done

    async def on_result(_prop_id, _result, current, count):
        await _emit(emitter, {"step": "detection", "status": "progress", "current": current, "total": count, "cycle": cycle})

    det_results = await batch_detect(
        rows,
        workers=settings.DETECTION_WORKERS,
        on_result=on_result,
    )

    processed = 0
    summary: dict[str, int] = {}
    for row in rows:
        result = det_results.get(row["id"])
        if not result:
            continue
        await _update_detection(row["id"], result)
        processed += 1
        summary[result.label] = summary.get(result.label, 0) + 1

    done = {"attempted": total, "processed": processed, "summary": summary}
    await _emit(emitter, {"step": "detection", "status": "done", "cycle": cycle, **done})
    return done


async def run_pipeline(
    geocode: bool = True,
    fetch_images: bool = True,
    run_detection_step: bool = True,
    limit: int = 0,
    process_all: bool = False,
    emitter: PipelineEmitter = None,
) -> dict:
    """Run the processing pipeline with optional process_all looping."""
    batch_limit = max(1, limit or settings.PIPELINE_BATCH_SIZE)
    totals = _init_totals()
    cycle_count = 0

    while True:
        cycle_count += 1
        cycle_processed = 0
        await _emit(emitter, {"step": "cycle", "status": "started", "cycle": cycle_count})

        if geocode:
            step = await _run_geocode_step(batch_limit, cycle_count, emitter)
            totals["geocode"]["attempted"] += step.get("attempted", 0)
            totals["geocode"]["processed"] += step.get("processed", 0)
            cycle_processed += step.get("processed", 0)

        if fetch_images:
            step = await _run_imagery_step(batch_limit, cycle_count, emitter)
            totals["imagery"]["attempted"] += step.get("attempted", 0)
            totals["imagery"]["processed"] += step.get("processed", 0)
            cycle_processed += step.get("processed", 0)

        if run_detection_step:
            step = await _run_detection_step(batch_limit, cycle_count, emitter)
            totals["detection"]["attempted"] += step.get("attempted", 0)
            totals["detection"]["processed"] += step.get("processed", 0)
            cycle_processed += step.get("processed", 0)

        await _emit(emitter, {"step": "cycle", "status": "done", "cycle": cycle_count})

        if not process_all:
            break
        if cycle_processed == 0:
            break

    return {
        "process_all": process_all,
        "batch_size": batch_limit,
        "cycles": cycle_count,
        "totals": totals,
        "steps": [
            {"geocode": totals["geocode"]},
            {"imagery": totals["imagery"]},
            {"detection": totals["detection"]},
        ],
    }
