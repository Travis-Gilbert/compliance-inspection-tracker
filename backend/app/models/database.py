from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import aiosqlite

try:
    import asyncpg
except ImportError:  # pragma: no cover, exercised only when Postgres support is unavailable
    asyncpg = None

from app.config import DATABASE_PATH, DATABASE_URL
from app.utils.address import build_address_key

DatabaseConnection = Any


SQLITE_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS properties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address TEXT NOT NULL,
        address_key TEXT DEFAULT '',
        parcel_id TEXT DEFAULT '',
        buyer_name TEXT DEFAULT '',
        program TEXT DEFAULT '',
        closing_date TEXT DEFAULT '',
        commitment TEXT DEFAULT '',
        email TEXT DEFAULT '',
        organization TEXT DEFAULT '',
        purchase_type TEXT DEFAULT '',
        compliance_1st_attempt TEXT DEFAULT '',
        compliance_2nd_attempt TEXT DEFAULT '',

        latitude REAL,
        longitude REAL,
        formatted_address TEXT DEFAULT '',
        geocoded_at TEXT,

        streetview_path TEXT DEFAULT '',
        streetview_date TEXT DEFAULT '',
        streetview_available INTEGER DEFAULT 0,
        streetview_historical_path TEXT DEFAULT '',
        streetview_historical_date TEXT DEFAULT '',
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS import_batches (
        id TEXT PRIMARY KEY,
        filename TEXT DEFAULT '',
        row_count INTEGER DEFAULT 0,
        imported_at TEXT DEFAULT (datetime('now')),
        notes TEXT DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_properties_finding ON properties(finding)",
    "CREATE INDEX IF NOT EXISTS idx_properties_detection ON properties(detection_label)",
    "CREATE INDEX IF NOT EXISTS idx_properties_parcel ON properties(parcel_id)",
    "CREATE INDEX IF NOT EXISTS idx_comms_property ON communications(property_id)",
]

POSTGRES_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS properties (
        id SERIAL PRIMARY KEY,
        address TEXT NOT NULL,
        address_key TEXT DEFAULT '',
        parcel_id TEXT DEFAULT '',
        buyer_name TEXT DEFAULT '',
        program TEXT DEFAULT '',
        closing_date TEXT DEFAULT '',
        commitment TEXT DEFAULT '',
        email TEXT DEFAULT '',
        organization TEXT DEFAULT '',
        purchase_type TEXT DEFAULT '',
        compliance_1st_attempt TEXT DEFAULT '',
        compliance_2nd_attempt TEXT DEFAULT '',

        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        formatted_address TEXT DEFAULT '',
        geocoded_at TEXT,

        streetview_path TEXT DEFAULT '',
        streetview_date TEXT DEFAULT '',
        streetview_available INTEGER DEFAULT 0,
        streetview_historical_path TEXT DEFAULT '',
        streetview_historical_date TEXT DEFAULT '',
        satellite_path TEXT DEFAULT '',
        imagery_fetched_at TEXT,

        detection_score DOUBLE PRECISION,
        detection_label TEXT DEFAULT '',
        detection_details TEXT DEFAULT '',
        detection_ran_at TEXT,

        finding TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        reviewed_at TEXT,
        reviewed_by TEXT DEFAULT 'staff',

        import_batch TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP::text,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS communications (
        id SERIAL PRIMARY KEY,
        property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
        method TEXT NOT NULL,
        direction TEXT DEFAULT 'outbound',
        date_sent TEXT,
        subject TEXT DEFAULT '',
        body TEXT DEFAULT '',
        response_received INTEGER DEFAULT 0,
        response_date TEXT,
        response_notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP::text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS import_batches (
        id TEXT PRIMARY KEY,
        filename TEXT DEFAULT '',
        row_count INTEGER DEFAULT 0,
        imported_at TEXT DEFAULT CURRENT_TIMESTAMP::text,
        notes TEXT DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_properties_finding ON properties(finding)",
    "CREATE INDEX IF NOT EXISTS idx_properties_detection ON properties(detection_label)",
    "CREATE INDEX IF NOT EXISTS idx_properties_parcel ON properties(parcel_id)",
    "CREATE INDEX IF NOT EXISTS idx_comms_property ON communications(property_id)",
]

MIGRATION_COLUMNS = [
    ("email", "TEXT DEFAULT ''"),
    ("organization", "TEXT DEFAULT ''"),
    ("purchase_type", "TEXT DEFAULT ''"),
    ("compliance_1st_attempt", "TEXT DEFAULT ''"),
    ("compliance_2nd_attempt", "TEXT DEFAULT ''"),
    ("streetview_historical_path", "TEXT DEFAULT ''"),
    ("streetview_historical_date", "TEXT DEFAULT ''"),
    ("address_key", "TEXT DEFAULT ''"),
]


def using_postgres() -> bool:
    return bool(DATABASE_URL)


def _has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


class DBRow(dict):
    def __init__(self, mapping: dict[str, Any]):
        super().__init__(mapping)
        self._values = list(mapping.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, rows: list[DBRow] | None = None, lastrowid=None):
        self._rows = rows or []
        self._index = 0
        self.lastrowid = lastrowid

    async def fetchone(self):
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    async def fetchall(self):
        if self._index >= len(self._rows):
            return []
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows


def _translate_postgres_placeholders(query: str) -> str:
    translated: list[str] = []
    param_index = 1
    in_single_quote = False

    for char in query:
        if char == "'":
            in_single_quote = not in_single_quote
            translated.append(char)
            continue
        if char == "?" and not in_single_quote:
            translated.append(f"${param_index}")
            param_index += 1
            continue
        translated.append(char)

    return "".join(translated)


class PostgresConnection:
    def __init__(self, connection):
        self._connection = connection
        self.row_factory = None
        self.is_postgres = True

    @classmethod
    async def connect(cls, dsn: str):
        if asyncpg is None:
            raise RuntimeError("asyncpg is required when DATABASE_URL is set")
        connection = await asyncpg.connect(dsn, statement_cache_size=0)
        return cls(connection)

    async def execute(self, query: str, params=None):
        params = list(params or [])
        translated = _translate_postgres_placeholders(query)
        normalized = query.lstrip().lower()

        if normalized.startswith("select") or normalized.startswith("with"):
            rows = await self._connection.fetch(translated, *params)
            return PostgresCursor([DBRow(dict(row)) for row in rows])

        if normalized.startswith("insert"):
            insert_query = translated
            if " returning " not in normalized:
                insert_query = f"{translated.rstrip()} RETURNING id"
            row = await self._connection.fetchrow(insert_query, *params)
            rows = [DBRow(dict(row))] if row else []
            lastrowid = row["id"] if row and "id" in row else None
            return PostgresCursor(rows=rows, lastrowid=lastrowid)

        await self._connection.execute(translated, *params)
        return PostgresCursor()

    async def commit(self):
        return None

    async def close(self):
        await self._connection.close()


async def _open_db_connection():
    if using_postgres():
        return await PostgresConnection.connect(DATABASE_URL)

    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


@asynccontextmanager
async def connect_db():
    db = await _open_db_connection()
    try:
        yield db
    finally:
        await db.close()


def _dedupe_score(row: dict) -> int:
    score = 0
    weighted_fields = {
        "finding": 50,
        "notes": 40,
        "reviewed_at": 30,
        "detection_ran_at": 20,
        "imagery_fetched_at": 15,
        "geocoded_at": 10,
        "streetview_historical_path": 6,
        "compliance_1st_attempt": 5,
        "compliance_2nd_attempt": 5,
        "email": 3,
        "organization": 3,
        "purchase_type": 3,
    }
    for field, weight in weighted_fields.items():
        if _has_value(row.get(field)):
            score += weight
    if row.get("streetview_available"):
        score += 8
    if _has_value(row.get("satellite_path")):
        score += 8
    return score


def _merge_notes(*values: str) -> str:
    seen = set()
    lines = []
    for value in values:
        if not _has_value(value):
            continue
        for line in str(value).splitlines():
            clean = line.strip()
            if clean and clean not in seen:
                seen.add(clean)
                lines.append(clean)
    return "\n".join(lines)


def _merge_property_rows(primary: dict, duplicates: list[dict]) -> dict:
    merged = dict(primary)
    for row in duplicates:
        for field in [
            "address",
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
            "streetview_historical_path",
            "streetview_historical_date",
            "satellite_path",
            "imagery_fetched_at",
            "detection_score",
            "detection_label",
            "detection_details",
            "detection_ran_at",
            "finding",
            "reviewed_at",
            "reviewed_by",
            "import_batch",
        ]:
            if not _has_value(merged.get(field)) and _has_value(row.get(field)):
                merged[field] = row[field]

        if not merged.get("streetview_available") and row.get("streetview_available"):
            merged["streetview_available"] = row["streetview_available"]

        merged["notes"] = _merge_notes(merged.get("notes", ""), row.get("notes", ""))

        created_at = [
            value for value in [merged.get("created_at"), row.get("created_at")]
            if _has_value(value)
        ]
        if created_at:
            merged["created_at"] = min(created_at)

        updated_at = [
            value for value in [merged.get("updated_at"), row.get("updated_at")]
            if _has_value(value)
        ]
        if updated_at:
            merged["updated_at"] = max(updated_at)

    merged["address_key"] = build_address_key(merged.get("address", ""))
    return merged


async def _dedupe_properties(db: DatabaseConnection):
    cursor = await db.execute("SELECT * FROM properties ORDER BY id")
    rows = [dict(row) for row in await cursor.fetchall()]
    groups = {}

    for row in rows:
        parcel_id = (row.get("parcel_id") or "").strip().lower()
        address_key = row.get("address_key") or build_address_key(row.get("address", ""))
        key = f"parcel:{parcel_id}" if parcel_id else f"address:{address_key}"
        if key in {"parcel:", "address:"}:
            continue
        groups.setdefault(key, []).append(row)

    for group_rows in groups.values():
        if len(group_rows) < 2:
            continue

        ranked = sorted(group_rows, key=lambda row: (-_dedupe_score(row), row["id"]))
        primary = ranked[0]
        duplicates = ranked[1:]
        merged = _merge_property_rows(primary, duplicates)

        await db.execute(
            """
            UPDATE properties
            SET address = ?, address_key = ?, parcel_id = ?, buyer_name = ?, program = ?,
                closing_date = ?, commitment = ?, email = ?, organization = ?, purchase_type = ?,
                compliance_1st_attempt = ?, compliance_2nd_attempt = ?, latitude = ?, longitude = ?,
                formatted_address = ?, geocoded_at = ?, streetview_path = ?, streetview_date = ?,
                streetview_available = ?, streetview_historical_path = ?, streetview_historical_date = ?,
                satellite_path = ?, imagery_fetched_at = ?, detection_score = ?, detection_label = ?,
                detection_details = ?, detection_ran_at = ?, finding = ?, notes = ?, reviewed_at = ?,
                reviewed_by = ?, import_batch = ?, created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            [
                merged.get("address", ""),
                merged.get("address_key", ""),
                merged.get("parcel_id", ""),
                merged.get("buyer_name", ""),
                merged.get("program", ""),
                merged.get("closing_date", ""),
                merged.get("commitment", ""),
                merged.get("email", ""),
                merged.get("organization", ""),
                merged.get("purchase_type", ""),
                merged.get("compliance_1st_attempt", ""),
                merged.get("compliance_2nd_attempt", ""),
                merged.get("latitude"),
                merged.get("longitude"),
                merged.get("formatted_address", ""),
                merged.get("geocoded_at"),
                merged.get("streetview_path", ""),
                merged.get("streetview_date", ""),
                1 if merged.get("streetview_available") else 0,
                merged.get("streetview_historical_path", ""),
                merged.get("streetview_historical_date", ""),
                merged.get("satellite_path", ""),
                merged.get("imagery_fetched_at"),
                merged.get("detection_score"),
                merged.get("detection_label", ""),
                merged.get("detection_details", ""),
                merged.get("detection_ran_at"),
                merged.get("finding", ""),
                merged.get("notes", ""),
                merged.get("reviewed_at"),
                merged.get("reviewed_by", "staff"),
                merged.get("import_batch", ""),
                merged.get("created_at"),
                merged.get("updated_at"),
                primary["id"],
            ],
        )

        duplicate_ids = [row["id"] for row in duplicates]
        placeholders = ", ".join("?" for _ in duplicate_ids)
        await db.execute(
            f"UPDATE communications SET property_id = ? WHERE property_id IN ({placeholders})",
            [primary["id"], *duplicate_ids],
        )
        await db.execute(
            f"DELETE FROM properties WHERE id IN ({placeholders})",
            duplicate_ids,
        )


async def _ensure_postgis(db: DatabaseConnection):
    try:
        await db.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        await db.execute(
            "ALTER TABLE properties ADD COLUMN IF NOT EXISTS location geography(Point, 4326)"
        )
        await db.execute(
            """
            CREATE OR REPLACE FUNCTION set_property_location()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
                    NEW.location = ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)::geography;
                ELSE
                    NEW.location = NULL;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        await db.execute("DROP TRIGGER IF EXISTS trg_properties_location ON properties")
        await db.execute(
            """
            CREATE TRIGGER trg_properties_location
            BEFORE INSERT OR UPDATE OF latitude, longitude ON properties
            FOR EACH ROW EXECUTE FUNCTION set_property_location()
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_properties_location ON properties USING GIST (location)"
        )
        await db.execute(
            """
            UPDATE properties
            SET location = CASE
                WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
                ELSE NULL
            END
            """
        )
    except Exception as exc:  # pragma: no cover, depends on target Postgres capabilities
        print(f"Warning: PostGIS setup skipped: {exc}")


async def get_db():
    """Yield a portable database connection."""
    db = await _open_db_connection()
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """Create tables if they don't exist, then run lightweight migrations."""
    async with connect_db() as db:
        schema_statements = POSTGRES_SCHEMA_STATEMENTS if using_postgres() else SQLITE_SCHEMA_STATEMENTS
        for statement in schema_statements:
            await db.execute(statement)

        for col_name, col_type in MIGRATION_COLUMNS:
            try:
                if using_postgres():
                    await db.execute(
                        f"ALTER TABLE properties ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    )
                else:
                    await db.execute(f"ALTER TABLE properties ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        await db.execute("CREATE INDEX IF NOT EXISTS idx_properties_address_key ON properties(address_key)")

        cursor = await db.execute(
            "SELECT id, address FROM properties WHERE COALESCE(address_key, '') = ''"
        )
        for row in await cursor.fetchall():
            await db.execute(
                "UPDATE properties SET address_key = ? WHERE id = ?",
                [build_address_key(row["address"]), row["id"]],
            )

        if using_postgres():
            await _ensure_postgis(db)

        await _dedupe_properties(db)
        await db.commit()
