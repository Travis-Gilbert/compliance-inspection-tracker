import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite

from app.models.database import init_db
from app.services.csv_parser import parse_csv_text
from app.services.exporter import export_properties_csv


LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,
    parcel_id TEXT DEFAULT '',
    buyer_name TEXT DEFAULT '',
    program TEXT DEFAULT '',
    closing_date TEXT DEFAULT '',
    commitment TEXT DEFAULT '',
    latitude REAL,
    longitude REAL,
    formatted_address TEXT DEFAULT '',
    geocoded_at TEXT,
    streetview_path TEXT DEFAULT '',
    streetview_date TEXT DEFAULT '',
    streetview_available INTEGER DEFAULT 0,
    satellite_path TEXT DEFAULT '',
    imagery_fetched_at TEXT,
    detection_score REAL,
    detection_label TEXT DEFAULT '',
    detection_details TEXT DEFAULT '',
    detection_ran_at TEXT,
    finding TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    reviewed_at TEXT,
    reviewed_by TEXT DEFAULT 'staff',
    import_batch TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS communications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,
    method TEXT NOT NULL,
    direction TEXT DEFAULT 'outbound',
    date_sent TEXT,
    subject TEXT DEFAULT '',
    body TEXT DEFAULT '',
    response_received INTEGER DEFAULT 0,
    response_date TEXT,
    response_notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS import_batches (
    id TEXT PRIMARY KEY,
    filename TEXT DEFAULT '',
    row_count INTEGER DEFAULT 0,
    imported_at TEXT DEFAULT (datetime('now')),
    notes TEXT DEFAULT ''
);
"""


class TestDatabaseAndCsv(unittest.IsolatedAsyncioTestCase):
    async def test_migration_adds_new_columns_without_reset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "tracker.db"
            async with aiosqlite.connect(db_path) as db:
                await db.executescript(LEGACY_SCHEMA)
                await db.commit()

            with (
                patch("app.config.DATABASE_PATH", str(db_path)),
                patch("app.models.database.DATABASE_PATH", str(db_path)),
            ):
                await init_db()

            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute("PRAGMA table_info(properties)")
                columns = {row[1] for row in await cursor.fetchall()}

            expected = {
                "email",
                "organization",
                "purchase_type",
                "compliance_1st_attempt",
                "compliance_2nd_attempt",
                "streetview_historical_path",
                "streetview_historical_date",
            }
            self.assertTrue(expected.issubset(columns))

    async def test_csv_parser_maps_new_fields_and_export_includes_them(self):
        csv_text = (
            "address,parcel_id,buyer_name,email,organization,purchase_type,program,"
            "closing_date,commitment,compliance_1st_attempt,compliance_2nd_attempt\n"
            "307 Mason St,41-06-538-004,John Smith,john@example.org,Mason Dev LLC,Individual,"
            "Featured Homes,2024-03-15,$45000,2025-10-01,2025-11-01\n"
        )

        properties, errors, _ = parse_csv_text(csv_text, "import.csv")
        self.assertEqual(errors, [])
        self.assertEqual(len(properties), 1)
        record = properties[0]
        self.assertEqual(record.email, "john@example.org")
        self.assertEqual(record.organization, "Mason Dev LLC")
        self.assertEqual(record.purchase_type, "Individual")
        self.assertEqual(record.compliance_1st_attempt, "2025-10-01")
        self.assertEqual(record.compliance_2nd_attempt, "2025-11-01")

        export_row = record.model_dump()
        export_row.update(
            {
                "finding": "",
                "notes": "",
                "reviewed_at": "",
                "streetview_available": False,
                "streetview_date": "",
                "detection_label": "",
                "detection_score": "",
                "streetview_historical_date": "",
                "streetview_historical_path": "",
            }
        )
        csv_out = export_properties_csv([export_row])
        self.assertIn("Email", csv_out)
        self.assertIn("Organization", csv_out)
        self.assertIn("Purchase Type", csv_out)
        self.assertIn("Compliance 1st Attempt", csv_out)
        self.assertIn("john@example.org", csv_out)


if __name__ == "__main__":
    unittest.main()
