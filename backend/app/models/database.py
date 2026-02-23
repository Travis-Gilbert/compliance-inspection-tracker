import aiosqlite
from app.config import DATABASE_PATH

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
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                parcel_id TEXT DEFAULT '',
                buyer_name TEXT DEFAULT '',
                program TEXT DEFAULT '',
                closing_date TEXT DEFAULT '',
                commitment TEXT DEFAULT '',

                -- Geocoding results
                latitude REAL,
                longitude REAL,
                formatted_address TEXT DEFAULT '',
                geocoded_at TEXT,

                -- Imagery
                streetview_path TEXT DEFAULT '',
                streetview_date TEXT DEFAULT '',
                streetview_available INTEGER DEFAULT 0,
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
                method TEXT NOT NULL,           -- email, mail, phone, site_visit
                direction TEXT DEFAULT 'outbound', -- outbound, inbound
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
        """)
        await db.commit()
