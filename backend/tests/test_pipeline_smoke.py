import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import init_db
from app.services.detector import DetectionResult
from app.services.geocoder import GeocodingResult
from app.services.imagery import HistoricalImageryResult, ImageryResult
from app.services.pipeline import run_pipeline


async def fake_batch_geocode(addresses, concurrency=1, client=None, on_result=None):
    results = {}
    total = len(addresses)
    for index, address in enumerate(addresses, start=1):
        result = GeocodingResult(43.01 + index * 0.001, -83.69 - index * 0.001, f"{address}, Flint, MI")
        results[address] = result
        if on_result:
            maybe_coro = on_result(address, result, index, total)
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro
    return results


async def fake_batch_fetch_imagery(properties, concurrency=1, client=None, on_result=None):
    results = {}
    total = len(properties)
    for index, prop in enumerate(properties, start=1):
        imagery = ImageryResult(
            streetview_path=f"/tmp/{prop['id']}_streetview.jpg",
            streetview_available=True,
            streetview_date="2025-08",
            satellite_path=f"/tmp/{prop['id']}_satellite.jpg",
        )
        results[prop["id"]] = imagery
        if on_result:
            maybe_coro = on_result(prop["id"], imagery, index, total)
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro
    return results


async def fake_batch_fetch_historical_imagery(properties, concurrency=1, client=None, on_result=None):
    results = {}
    total = len(properties)
    for index, prop in enumerate(properties, start=1):
        imagery = HistoricalImageryResult(
            streetview_historical_path=f"/tmp/{prop['id']}_streetview_historical.jpg",
            historical_available=True,
            streetview_historical_date="2024-03",
            target_date="2024-03",
        )
        results[prop["id"]] = imagery
        if on_result:
            maybe_coro = on_result(prop["id"], imagery, index, total)
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro
    return results


async def fake_batch_detect(properties, workers=1, on_result=None):
    results = {}
    total = len(properties)
    for index, prop in enumerate(properties, start=1):
        result = DetectionResult(
            score=0.81 if prop["id"] % 2 == 0 else 0.66,
            label="likely_demolished" if prop["id"] % 2 == 0 else "likely_vacant",
            details={"mocked": True},
        )
        results[prop["id"]] = result
        if on_result:
            maybe_coro = on_result(prop["id"], result, index, total)
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro
    return results


class TestPipelineSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_process_all_pipeline_and_event_emission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "tracker.db"
            with (
                patch("app.config.DATABASE_PATH", str(db_path)),
                patch("app.models.database.DATABASE_PATH", str(db_path)),
                patch("app.services.pipeline.DATABASE_PATH", str(db_path)),
            ):
                await init_db()

                async with aiosqlite.connect(db_path) as db:
                    await db.executemany(
                        """
                        INSERT INTO properties (address, program, closing_date)
                        VALUES (?, ?, ?)
                        """,
                        [
                            ("307 Mason St", "Featured Homes", "2024-03-15"),
                            ("1234 W Court St", "Ready for Rehab", "2023-11-20"),
                        ],
                    )
                    await db.commit()

                events = []
                with (
                    patch("app.services.pipeline.GOOGLE_MAPS_API_KEY", "test-key"),
                    patch("app.services.pipeline.batch_geocode", side_effect=fake_batch_geocode),
                    patch("app.services.pipeline.batch_fetch_imagery", side_effect=fake_batch_fetch_imagery),
                    patch(
                        "app.services.pipeline.batch_fetch_historical_imagery",
                        side_effect=fake_batch_fetch_historical_imagery,
                    ),
                    patch("app.services.pipeline.batch_detect", side_effect=fake_batch_detect),
                ):
                    results = await run_pipeline(
                        geocode=True,
                        fetch_images=True,
                        run_detection_step=True,
                        limit=1,
                        process_all=True,
                        emitter=lambda event: events.append(event),
                    )

                self.assertTrue(results["process_all"])
                self.assertEqual(results["totals"]["geocode"]["processed"], 2)
                self.assertEqual(results["totals"]["imagery"]["processed"], 2)
                self.assertEqual(results["totals"]["historical"]["processed"], 2)
                self.assertEqual(results["totals"]["detection"]["processed"], 2)

                steps = {(event["step"], event["status"]) for event in events}
                self.assertIn(("geocode", "progress"), steps)
                self.assertIn(("imagery", "progress"), steps)
                self.assertIn(("historical", "progress"), steps)
                self.assertIn(("detection", "progress"), steps)

                async with aiosqlite.connect(db_path) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute(
                        """
                        SELECT COUNT(*) AS n FROM properties
                        WHERE latitude IS NOT NULL
                          AND imagery_fetched_at IS NOT NULL
                          AND historical_imagery_checked_at IS NOT NULL
                          AND detection_ran_at IS NOT NULL
                        """
                    )
                    complete_count = (await cursor.fetchone())["n"]
                self.assertEqual(complete_count, 2)

    async def test_stream_endpoint_emits_sse_events(self):
        async def fake_pipeline(**kwargs):
            emitter = kwargs.get("emitter")
            if emitter:
                await emitter({"step": "geocode", "status": "started", "total": 1, "cycle": 1})
                await emitter({"step": "geocode", "status": "progress", "current": 1, "total": 1, "cycle": 1})
                await emitter({"step": "geocode", "status": "done", "processed": 1, "attempted": 1, "cycle": 1})
            return {
                    "totals": {
                        "geocode": {"processed": 1, "attempted": 1},
                        "imagery": {"processed": 0, "attempted": 0},
                        "historical": {"processed": 0, "attempted": 0},
                        "detection": {"processed": 0, "attempted": 0},
                    }
                }

        with patch("app.main.run_pipeline_service", side_effect=fake_pipeline):
            with TestClient(app) as client:
                response = client.post("/api/pipeline/process-stream?limit=5&process_all=false")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"step": "geocode"', response.text)
        self.assertIn('"status": "progress"', response.text)
        self.assertIn('"step": "complete"', response.text)


if __name__ == "__main__":
    unittest.main()
