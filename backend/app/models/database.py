import aiosqlite

from app.config import DATABASE_PATH
from app.utils.address import build_address_key


def _has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


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


async def _dedupe_properties(db: aiosqlite.Connection):
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


async def get_db():
    """Yield an async SQLite connection."""
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(
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

                -- Geocoding results
                latitude REAL,
                longitude REAL,
                formatted_address TEXT DEFAULT '',
                geocoded_at TEXT,

                -- Imagery
                streetview_path TEXT DEFAULT '',
                streetview_date TEXT DEFAULT '',
                streetview_available INTEGER DEFAULT 0,
                streetview_historical_path TEXT DEFAULT '',
                streetview_historical_date TEXT DEFAULT '',
                satellite_path TEXT DEFAULT '',
                imagery_fetched_at TEXT,

                -- Smart detection
                detection_score REAL,
                detection_label TEXT DEFAULT '',
                detection_details TEXT DEFAULT '',
                detection_ran_at TEXT,

                -- Review
                finding TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                reviewed_at TEXT,
                reviewed_by TEXT DEFAULT 'staff',

                -- Metadata
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

            CREATE INDEX IF NOT EXISTS idx_properties_finding ON properties(finding);
            CREATE INDEX IF NOT EXISTS idx_properties_detection ON properties(detection_label);
            CREATE INDEX IF NOT EXISTS idx_properties_parcel ON properties(parcel_id);
            CREATE INDEX IF NOT EXISTS idx_comms_property ON communications(property_id);
            """
        )

        migration_columns = [
            ("email", "TEXT DEFAULT ''"),
            ("organization", "TEXT DEFAULT ''"),
            ("purchase_type", "TEXT DEFAULT ''"),
            ("compliance_1st_attempt", "TEXT DEFAULT ''"),
            ("compliance_2nd_attempt", "TEXT DEFAULT ''"),
            ("streetview_historical_path", "TEXT DEFAULT ''"),
            ("streetview_historical_date", "TEXT DEFAULT ''"),
            ("address_key", "TEXT DEFAULT ''"),
        ]
        for col_name, col_type in migration_columns:
            try:
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

        await _dedupe_properties(db)
        await db.commit()
