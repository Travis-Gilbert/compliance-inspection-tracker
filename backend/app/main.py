from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.models.database import init_db
from app.api.properties import router as properties_router
from app.api.imagery import router as imagery_router
from app.api.detection import router as detection_router
from app.api.comms import router as comms_router
from app.config import IMAGE_CACHE_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="GCLBA Compliance Inspection Tracker",
    description="Desk research triage tool for property compliance inspections",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for React frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:3000",    # Alternate dev port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(properties_router)
app.include_router(imagery_router)
app.include_router(detection_router)
app.include_router(comms_router)

# Serve cached images as static files
if IMAGE_CACHE_DIR.exists():
    app.mount("/images", StaticFiles(directory=str(IMAGE_CACHE_DIR)), name="images")


@app.get("/")
async def root():
    return {
        "name": "GCLBA Compliance Inspection Tracker",
        "version": "1.0.0",
        "endpoints": {
            "properties": "/api/properties",
            "imagery": "/api/imagery",
            "detection": "/api/detection",
            "communications": "/api/communications",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Pipeline endpoint: run the full flow ---

@app.post("/api/pipeline/process")
async def run_pipeline(
    geocode: bool = True,
    fetch_images: bool = True,
    run_detection: bool = True,
    limit: int = 25,
):
    """
    Run the full processing pipeline:
    1. Geocode un-geocoded properties
    2. Fetch imagery for geocoded properties
    3. Run smart detection on properties with imagery

    This is the "one button" endpoint that processes a batch end-to-end.
    """
    from app.models.database import get_db
    import aiosqlite
    from app.config import DATABASE_PATH

    results = {"steps": []}

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Step 1: Geocode
        if geocode:
            from app.services.geocoder import batch_geocode
            from datetime import datetime

            cursor = await db.execute(
                "SELECT id, address FROM properties WHERE latitude IS NULL LIMIT ?", [limit]
            )
            rows = await cursor.fetchall()
            if rows:
                addresses = [r["address"] for r in rows]
                geo_results = await batch_geocode(addresses)
                geocoded = 0
                for row in rows:
                    result = geo_results.get(row["address"])
                    if result:
                        await db.execute("""
                            UPDATE properties SET latitude=?, longitude=?, formatted_address=?,
                            geocoded_at=?, updated_at=? WHERE id=?
                        """, [result.lat, result.lng, result.formatted_address,
                              datetime.now().isoformat(), datetime.now().isoformat(), row["id"]])
                        geocoded += 1
                await db.commit()
                results["steps"].append({"geocode": {"processed": geocoded, "attempted": len(rows)}})
            else:
                results["steps"].append({"geocode": {"processed": 0, "message": "All geocoded"}})

        # Step 2: Fetch imagery
        if fetch_images:
            from app.services.imagery import batch_fetch_imagery
            from datetime import datetime

            cursor = await db.execute("""
                SELECT id, address, latitude, longitude FROM properties
                WHERE latitude IS NOT NULL AND imagery_fetched_at IS NULL LIMIT ?
            """, [limit])
            rows = await cursor.fetchall()
            if rows:
                props = [dict(r) for r in rows]
                img_results = await batch_fetch_imagery(props)
                fetched = 0
                for pid, result in img_results.items():
                    await db.execute("""
                        UPDATE properties SET streetview_path=?, streetview_available=?,
                        streetview_date=?, satellite_path=?, imagery_fetched_at=?, updated_at=?
                        WHERE id=?
                    """, [result.streetview_path, 1 if result.streetview_available else 0,
                          result.streetview_date, result.satellite_path,
                          datetime.now().isoformat(), datetime.now().isoformat(), pid])
                    fetched += 1
                await db.commit()
                results["steps"].append({"imagery": {"fetched": fetched, "attempted": len(rows)}})
            else:
                results["steps"].append({"imagery": {"fetched": 0, "message": "All imagery fetched"}})

        # Step 3: Detection
        if run_detection:
            from app.services.detector import batch_detect
            from datetime import datetime
            import json

            cursor = await db.execute("""
                SELECT id, streetview_path, satellite_path FROM properties
                WHERE imagery_fetched_at IS NOT NULL AND detection_ran_at IS NULL LIMIT ?
            """, [limit])
            rows = await cursor.fetchall()
            if rows:
                props = [dict(r) for r in rows]
                det_results = await batch_detect(props)
                analyzed = 0
                for pid, result in det_results.items():
                    await db.execute("""
                        UPDATE properties SET detection_score=?, detection_label=?,
                        detection_details=?, detection_ran_at=?, updated_at=?
                        WHERE id=?
                    """, [result.score, result.label, json.dumps(result.details),
                          datetime.now().isoformat(), datetime.now().isoformat(), pid])
                    analyzed += 1
                await db.commit()

                label_counts = {}
                for r in det_results.values():
                    label_counts[r.label] = label_counts.get(r.label, 0) + 1
                results["steps"].append({"detection": {"analyzed": analyzed, "summary": label_counts}})
            else:
                results["steps"].append({"detection": {"analyzed": 0, "message": "All analyzed"}})

    return results


# --- Pipeline SSE endpoint: stream progress updates ---

@app.post("/api/pipeline/process-stream")
async def run_pipeline_stream(
    geocode: bool = True,
    fetch_images: bool = True,
    run_detection: bool = True,
    limit: int = 25,
):
    """
    Stream pipeline progress via Server-Sent Events.
    Each event is a JSON object with step name, status, and counts.
    """
    import asyncio
    import json as json_mod
    import aiosqlite
    from datetime import datetime
    from starlette.responses import StreamingResponse
    from app.config import DATABASE_PATH

    async def event_generator():
        def sse(data: dict) -> str:
            return f"data: {json_mod.dumps(data)}\n\n"

        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Step 1: Geocode
            if geocode:
                cursor = await db.execute(
                    "SELECT id, address FROM properties WHERE latitude IS NULL LIMIT ?", [limit]
                )
                rows = await cursor.fetchall()
                total = len(rows)
                yield sse({"step": "geocode", "status": "started", "total": total})

                if rows:
                    from app.services.geocoder import batch_geocode
                    addresses = [r["address"] for r in rows]
                    geo_results = await batch_geocode(addresses)
                    processed = 0
                    for row in rows:
                        result = geo_results.get(row["address"])
                        if result:
                            await db.execute("""
                                UPDATE properties SET latitude=?, longitude=?, formatted_address=?,
                                geocoded_at=?, updated_at=? WHERE id=?
                            """, [result.lat, result.lng, result.formatted_address,
                                  datetime.now().isoformat(), datetime.now().isoformat(), row["id"]])
                            processed += 1
                    await db.commit()
                    yield sse({"step": "geocode", "status": "done", "processed": processed, "total": total})
                else:
                    yield sse({"step": "geocode", "status": "done", "processed": 0, "total": 0, "message": "All geocoded"})

            # Step 2: Fetch imagery
            if fetch_images:
                cursor = await db.execute("""
                    SELECT id, address, latitude, longitude FROM properties
                    WHERE latitude IS NOT NULL AND imagery_fetched_at IS NULL LIMIT ?
                """, [limit])
                rows = await cursor.fetchall()
                total = len(rows)
                yield sse({"step": "imagery", "status": "started", "total": total})

                if rows:
                    from app.services.imagery import fetch_imagery_for_property
                    fetched = 0
                    for i, row in enumerate(rows):
                        prop = dict(row)
                        try:
                            result = await fetch_imagery_for_property(
                                prop["latitude"], prop["longitude"], prop["address"]
                            )
                            await db.execute("""
                                UPDATE properties SET streetview_path=?, streetview_available=?,
                                streetview_date=?, satellite_path=?, imagery_fetched_at=?, updated_at=?
                                WHERE id=?
                            """, [result.streetview_path, 1 if result.streetview_available else 0,
                                  result.streetview_date, result.satellite_path,
                                  datetime.now().isoformat(), datetime.now().isoformat(), prop["id"]])
                            fetched += 1
                        except Exception:
                            pass
                        # Emit progress every property
                        yield sse({"step": "imagery", "status": "progress", "current": i + 1, "total": total})
                    await db.commit()
                    yield sse({"step": "imagery", "status": "done", "processed": fetched, "total": total})
                else:
                    yield sse({"step": "imagery", "status": "done", "processed": 0, "total": 0, "message": "All imagery fetched"})

            # Step 3: Detection
            if run_detection:
                cursor = await db.execute("""
                    SELECT id, streetview_path, satellite_path FROM properties
                    WHERE imagery_fetched_at IS NOT NULL AND detection_ran_at IS NULL LIMIT ?
                """, [limit])
                rows = await cursor.fetchall()
                total = len(rows)
                yield sse({"step": "detection", "status": "started", "total": total})

                if rows:
                    from app.services.detector import detect_property_condition
                    analyzed = 0
                    label_counts = {}
                    for i, row in enumerate(rows):
                        prop = dict(row)
                        try:
                            result = detect_property_condition(prop.get("streetview_path"), prop.get("satellite_path"))
                            await db.execute("""
                                UPDATE properties SET detection_score=?, detection_label=?,
                                detection_details=?, detection_ran_at=?, updated_at=?
                                WHERE id=?
                            """, [result.score, result.label, json_mod.dumps(result.details),
                                  datetime.now().isoformat(), datetime.now().isoformat(), prop["id"]])
                            analyzed += 1
                            label_counts[result.label] = label_counts.get(result.label, 0) + 1
                        except Exception:
                            pass
                        yield sse({"step": "detection", "status": "progress", "current": i + 1, "total": total})
                    await db.commit()
                    yield sse({"step": "detection", "status": "done", "processed": analyzed, "total": total, "summary": label_counts})
                else:
                    yield sse({"step": "detection", "status": "done", "processed": 0, "total": 0, "message": "All analyzed"})

            yield sse({"step": "complete", "status": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
