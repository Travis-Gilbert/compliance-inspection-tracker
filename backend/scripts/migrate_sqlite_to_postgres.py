#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

PROPERTIES_COLUMNS = [
    "id",
    "address",
    "address_key",
    "parcel_id",
    "buyer_name",
    "program",
    "closing_date",
    "commitment",
    "email",
    "organization",
    "purchase_type",
    "compliance_1st_attempt",
    "compliance_2nd_attempt",
    "latitude",
    "longitude",
    "formatted_address",
    "geocoded_at",
    "streetview_path",
    "streetview_date",
    "streetview_available",
    "streetview_historical_path",
    "streetview_historical_date",
    "satellite_path",
    "imagery_fetched_at",
    "detection_score",
    "detection_label",
    "detection_details",
    "detection_ran_at",
    "finding",
    "notes",
    "reviewed_at",
    "reviewed_by",
    "import_batch",
    "created_at",
    "updated_at",
]

COMMUNICATION_COLUMNS = [
    "id",
    "property_id",
    "method",
    "direction",
    "date_sent",
    "subject",
    "body",
    "response_received",
    "response_date",
    "response_notes",
    "created_at",
]

IMPORT_BATCH_COLUMNS = [
    "id",
    "filename",
    "row_count",
    "imported_at",
    "notes",
]


def read_sqlite_rows(db_path: Path, table: str, columns: list[str]) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        query = f"SELECT {', '.join(columns)} FROM {table}"
        rows = connection.execute(query).fetchall()
        return [tuple(row[column] for column in columns) for row in rows]


async def set_sequence(connection, table: str):
    max_id = await connection.fetchval(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
    if not max_id:
        return
    await connection.execute(
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), $1, true)",
        max_id,
    )


async def migrate(sqlite_path: Path, database_url: str, clear_target: bool):
    os.environ["DATABASE_URL"] = database_url

    import asyncpg
    from app.models.database import init_db

    await init_db()

    properties = read_sqlite_rows(sqlite_path, "properties", PROPERTIES_COLUMNS)
    communications = read_sqlite_rows(sqlite_path, "communications", COMMUNICATION_COLUMNS)
    import_batches = read_sqlite_rows(sqlite_path, "import_batches", IMPORT_BATCH_COLUMNS)

    connection = await asyncpg.connect(database_url, statement_cache_size=0)
    try:
        if clear_target:
            await connection.execute("TRUNCATE communications, properties, import_batches RESTART IDENTITY CASCADE")

        if import_batches:
            placeholders = ", ".join(f"${index}" for index in range(1, len(IMPORT_BATCH_COLUMNS) + 1))
            await connection.executemany(
                f"""
                INSERT INTO import_batches ({", ".join(IMPORT_BATCH_COLUMNS)})
                VALUES ({placeholders})
                """,
                import_batches,
            )

        if properties:
            placeholders = ", ".join(f"${index}" for index in range(1, len(PROPERTIES_COLUMNS) + 1))
            await connection.executemany(
                f"""
                INSERT INTO properties ({", ".join(PROPERTIES_COLUMNS)})
                VALUES ({placeholders})
                """,
                properties,
            )
            await set_sequence(connection, "properties")

        if communications:
            placeholders = ", ".join(f"${index}" for index in range(1, len(COMMUNICATION_COLUMNS) + 1))
            await connection.executemany(
                f"""
                INSERT INTO communications ({", ".join(COMMUNICATION_COLUMNS)})
                VALUES ({placeholders})
                """,
                communications,
            )
            await set_sequence(connection, "communications")
    finally:
        await connection.close()

    print(
        f"Migrated {len(properties)} properties, {len(communications)} communications, "
        f"and {len(import_batches)} import batches into Postgres."
    )
    print("Note: cached imagery files were not copied. Re-run imagery fetches or sync IMAGE_CACHE_DIR separately.")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Copy local SQLite tracker data into Postgres.")
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("DATABASE_PATH", str(ROOT_DIR / "data" / "compliance_tracker.db")),
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Destination Postgres DATABASE_URL.",
    )
    parser.add_argument(
        "--skip-clear",
        action="store_true",
        help="Keep existing destination rows instead of truncating target tables first.",
    )
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).expanduser().resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required for the migration target.")

    asyncio.run(
        migrate(
            sqlite_path=sqlite_path,
            database_url=args.database_url,
            clear_target=not args.skip_clear,
        )
    )


if __name__ == "__main__":
    main()
