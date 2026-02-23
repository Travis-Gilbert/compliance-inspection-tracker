import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

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
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "compliance_tracker.db"))

# Image cache
IMAGE_CACHE_DIR = Path(os.getenv("IMAGE_CACHE_DIR", str(DATA_DIR / "images")))
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Detection thresholds
VACANCY_THRESHOLD = float(os.getenv("VACANCY_THRESHOLD", "0.6"))
DEMOLITION_THRESHOLD = float(os.getenv("DEMOLITION_THRESHOLD", "0.7"))

# Server
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# Google Maps API endpoints
STREETVIEW_URL = "https://maps.googleapis.com/maps/api/streetview"
STREETVIEW_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
