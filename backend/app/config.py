import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _split_csv_env(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Google Maps
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
STREETVIEW_SIZE = os.getenv("STREETVIEW_SIZE", "640x480")
SATELLITE_SIZE = os.getenv("SATELLITE_SIZE", "640x480")
SATELLITE_ZOOM = int(os.getenv("SATELLITE_ZOOM", "19"))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "compliance_tracker.db"))

# Image cache
IMAGE_CACHE_DIR = Path(os.getenv("IMAGE_CACHE_DIR", str(DATA_DIR / "images")))
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Detection thresholds
VACANCY_THRESHOLD = float(os.getenv("VACANCY_THRESHOLD", "0.6"))
DEMOLITION_THRESHOLD = float(os.getenv("DEMOLITION_THRESHOLD", "0.7"))

# Pipeline concurrency and batching
GEOCODE_CONCURRENCY = int(os.getenv("GEOCODE_CONCURRENCY", "8"))
IMAGERY_CONCURRENCY = int(os.getenv("IMAGERY_CONCURRENCY", "6"))
DETECTION_WORKERS = int(os.getenv("DETECTION_WORKERS", "4"))
PIPELINE_BATCH_SIZE = int(os.getenv("PIPELINE_BATCH_SIZE", "100"))

# Server
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# CORS
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
CORS_ORIGINS = _split_csv_env(os.getenv("CORS_ORIGINS", "")) or DEFAULT_CORS_ORIGINS
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", r"^https://.*\.vercel\.app$")

# Google Maps API endpoints
STREETVIEW_URL = "https://maps.googleapis.com/maps/api/streetview"
STREETVIEW_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
