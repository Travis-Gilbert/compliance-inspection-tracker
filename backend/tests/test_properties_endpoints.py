import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite

from app.api.properties import get_buyers_summary, get_map_properties, get_priority_queue
from app.models.database import init_db


class TestPropertiesEndpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "tracker.db"
        self.patchers = [
            patch("app.config.DATABASE_PATH", str(self.db_path)),
            patch("app.models.database.DATABASE_PATH", str(self.db_path)),
        ]
        for patcher in self.patchers:
            patcher.start()

        await init_db()
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row

        await self.db.executemany(
            """
            INSERT INTO properties (
                address, parcel_id, buyer_name, organization, email, program, closing_date,
                compliance_1st_attempt, compliance_2nd_attempt,
                latitude, longitude, streetview_available, satellite_path,
                detection_label, detection_score, finding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "307 Mason St", "41-06-538-004", "Buyer One", "Org A", "one@example.org",
                    "Featured Homes", "2024-03-15", "", "",
                    43.01, -83.69, 1, "/tmp/sat1.jpg", "likely_vacant", 0.72, "",
                ),
                (
                    "1234 W Court St", "41-11-234-012", "Buyer One", "Org A", "one@example.org",
                    "Featured Homes", "2023-11-20", "2025-10-01", "",
                    43.011, -83.691, 1, "/tmp/sat2.jpg", "likely_occupied", 0.22, "occupied_maintained",
                ),
                (
                    "456 E Kearsley St", "41-06-102-008", "Buyer Two", "Org B", "two@example.org",
                    "Ready for Rehab", "2024-06-01", "", "",
                    43.012, -83.692, 0, "", "likely_demolished", 0.88, "inconclusive",
                ),
            ],
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    async def test_map_all_response_contains_priority_fields(self):
        response = await get_map_properties(program=None, contact="all", db=self.db)
        self.assertEqual(response["count"], 3)
        first = response["properties"][0]
        self.assertIn("priority_score", first)
        self.assertIn("priority_level", first)
        self.assertIn("has_contact_attempt", first)

    async def test_buyers_summary_rollup(self):
        response = await get_buyers_summary(program=None, contact="all", db=self.db)
        buyers = response["buyers"]
        self.assertEqual(response["count"], 2)
        top = buyers[0]
        self.assertEqual(top["buyer"], "Buyer One")
        self.assertEqual(top["property_count"], 2)
        self.assertIn("average_priority_score", top)

    async def test_priority_queue_paging_and_sort(self):
        response = await get_priority_queue(
            filter="all",
            program=None,
            search="",
            sort="priority",
            order="desc",
            limit=2,
            offset=0,
            db=self.db,
        )
        self.assertEqual(response["limit"], 2)
        self.assertEqual(response["offset"], 0)
        self.assertEqual(response["total"], 3)
        self.assertEqual(len(response["properties"]), 2)
        self.assertGreaterEqual(
            response["properties"][0]["priority_score"],
            response["properties"][1]["priority_score"],
        )


if __name__ == "__main__":
    unittest.main()
