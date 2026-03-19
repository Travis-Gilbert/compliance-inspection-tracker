import asyncio
import json
from datetime import datetime
from typing import Awaitable, Callable, Optional

from app.config import (
    DATABASE_PATH,
    DETECTION_WORKERS,
    GEOCODE_CONCURRENCY,
    IMAGERY_CONCURRENCY,
    PIPELINE_BATCH_SIZE,
)
from app.models.database import DatabaseConnection, connect_db
from app.services.detector import batch_detect
from app.services.geocoder import batch_geocode
from app.services.imagery import batch_fetch_imagery

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


async def _run_geocode_step(
    db: DatabaseConnection,
    limit: int,
    cycle: int,
    emitter: PipelineEmitter,
) -> dict:
    cursor = await db.execute(
        "SELECT id, address FROM properties WHERE latitude IS NULL LIMIT ?",
        [limit],
    )
    rows = await cursor.fetchall()
    total = len(rows)
    await _emit(emitter, {"step": "geocode", "status": "started", "total": total, "cycle": cycle})

    if not rows:
        done = {"attempted": 0, "processed": 0, "message": "All geocoded"}
        await _emit(emitter, {"step": "geocode", "status": "done", "cycle": cycle, **done})
        return done

    async def on_result(_address: str, _result, current: int, count: int):
        await _emit(
            emitter,
            {"step": "geocode", "status": "progress", "current": current, "total": count, "cycle": cycle},
        )

    geo_results = await batch_geocode(
        [row["address"] for row in rows],
        concurrency=GEOCODE_CONCURRENCY,
        on_result=on_result,
    )

    processed = 0
    now = _now_iso()
    for row in rows:
        result = geo_results.get(row["address"])
        if not result:
            continue
        await db.execute(
            """
            UPDATE properties
            SET latitude = ?, longitude = ?, formatted_address = ?, geocoded_at = ?, updated_at = ?
            WHERE id = ?
            """,
            [result.lat, result.lng, result.formatted_address, now, now, row["id"]],
        )
        processed += 1

    await db.commit()
    done = {"attempted": total, "processed": processed}
    await _emit(emitter, {"step": "geocode", "status": "done", "cycle": cycle, **done})
    return done


async def _run_imagery_step(
    db: DatabaseConnection,
    limit: int,
    cycle: int,
    emitter: PipelineEmitter,
) -> dict:
    cursor = await db.execute(
        """
        SELECT id, address, latitude, longitude FROM properties
        WHERE latitude IS NOT NULL AND imagery_fetched_at IS NULL
        LIMIT ?
        """,
        [limit],
    )
    rows = await cursor.fetchall()
    total = len(rows)
    await _emit(emitter, {"step": "imagery", "status": "started", "total": total, "cycle": cycle})

    if not rows:
        done = {"attempted": 0, "processed": 0, "message": "All imagery fetched"}
        await _emit(emitter, {"step": "imagery", "status": "done", "cycle": cycle, **done})
        return done

    async def on_result(_prop_id: int, _result, current: int, count: int):
        await _emit(
            emitter,
            {"step": "imagery", "status": "progress", "current": current, "total": count, "cycle": cycle},
        )

    img_results = await batch_fetch_imagery(
        [dict(row) for row in rows],
        concurrency=IMAGERY_CONCURRENCY,
        on_result=on_result,
    )

    processed = 0
    with_imagery = 0
    now = _now_iso()
    for row in rows:
        result = img_results.get(row["id"])
        if not result:
            continue
        await db.execute(
            """
            UPDATE properties
            SET streetview_path = ?, streetview_available = ?, streetview_date = ?,
                satellite_path = ?, imagery_fetched_at = ?, updated_at = ?
            WHERE id = ?
            """,
            [
                result.streetview_path,
                1 if result.streetview_available else 0,
                result.streetview_date,
                result.satellite_path,
                now,
                now,
                row["id"],
            ],
        )
        processed += 1
        if result.streetview_available or bool(result.satellite_path):
            with_imagery += 1

    await db.commit()
    done = {"attempted": total, "processed": processed, "with_imagery": with_imagery}
    await _emit(emitter, {"step": "imagery", "status": "done", "cycle": cycle, **done})
    return done


async def _run_detection_step(
    db: DatabaseConnection,
    limit: int,
    cycle: int,
    emitter: PipelineEmitter,
) -> dict:
    cursor = await db.execute(
        """
        SELECT id, streetview_path, satellite_path FROM properties
        WHERE imagery_fetched_at IS NOT NULL AND detection_ran_at IS NULL
        LIMIT ?
        """,
        [limit],
    )
    rows = await cursor.fetchall()
    total = len(rows)
    await _emit(emitter, {"step": "detection", "status": "started", "total": total, "cycle": cycle})

    if not rows:
        done = {"attempted": 0, "processed": 0, "message": "All analyzed"}
        await _emit(emitter, {"step": "detection", "status": "done", "cycle": cycle, **done})
        return done

    async def on_result(_prop_id: int, _result, current: int, count: int):
        await _emit(
            emitter,
            {"step": "detection", "status": "progress", "current": current, "total": count, "cycle": cycle},
        )

    det_results = await batch_detect(
        [dict(row) for row in rows],
        workers=DETECTION_WORKERS,
        on_result=on_result,
    )

    processed = 0
    summary: dict[str, int] = {}
    now = _now_iso()
    for row in rows:
        result = det_results.get(row["id"])
        if not result:
            continue
        await db.execute(
            """
            UPDATE properties
            SET detection_score = ?, detection_label = ?, detection_details = ?,
                detection_ran_at = ?, updated_at = ?
            WHERE id = ?
            """,
            [result.score, result.label, json.dumps(result.details), now, now, row["id"]],
        )
        processed += 1
        summary[result.label] = summary.get(result.label, 0) + 1

    await db.commit()
    done = {"attempted": total, "processed": processed, "summary": summary}
    await _emit(emitter, {"step": "detection", "status": "done", "cycle": cycle, **done})
    return done


async def run_pipeline(
    geocode: bool = True,
    fetch_images: bool = True,
    run_detection_step: bool = True,
    limit: int = PIPELINE_BATCH_SIZE,
    process_all: bool = False,
    emitter: PipelineEmitter = None,
) -> dict:
    """
    Run the existing pipeline surface with optional process_all looping.
    """
    batch_limit = max(1, limit or PIPELINE_BATCH_SIZE)
    totals = _init_totals()
    cycle_count = 0

    async with connect_db() as db:
        while True:
            cycle_count += 1
            cycle_processed = 0
            await _emit(emitter, {"step": "cycle", "status": "started", "cycle": cycle_count})

            if geocode:
                step = await _run_geocode_step(db, batch_limit, cycle_count, emitter)
                totals["geocode"]["attempted"] += step.get("attempted", 0)
                totals["geocode"]["processed"] += step.get("processed", 0)
                cycle_processed += step.get("processed", 0)

            if fetch_images:
                step = await _run_imagery_step(db, batch_limit, cycle_count, emitter)
                totals["imagery"]["attempted"] += step.get("attempted", 0)
                totals["imagery"]["processed"] += step.get("processed", 0)
                cycle_processed += step.get("processed", 0)

            if run_detection_step:
                step = await _run_detection_step(db, batch_limit, cycle_count, emitter)
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
