"""
Django settings for GCLBA Compliance Inspection Tracker v2.

Reads configuration from environment variables via django-environ.
"""
import os
from pathlib import Path

import environ

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["*"]),
    CORS_ALLOWED_ORIGINS=(list, [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]),
)

BASE_DIR = Path(__file__).resolve().parent.parent

# Read .env file if it exists
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-in-production")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "tracker",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
# Postgres with PostGIS is the project database foundation.
DATABASE_URL = env(
    "DATABASE_URL",
    default="postgres://localhost:5432/compliance_tracker",
)
DATABASES = {
    "default": env.db_url_config(DATABASE_URL),
}
DATABASES["default"]["ENGINE"] = "django.db.backends.postgresql"

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Detroit"
USE_I18N = False
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media / image cache
MEDIA_ROOT = BASE_DIR / "image_cache"
MEDIA_URL = "/images/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# Google Maps API
GOOGLE_MAPS_API_KEY = env("GOOGLE_MAPS_API_KEY", default="")
STREETVIEW_SIZE = env("STREETVIEW_SIZE", default="640x480")
SATELLITE_SIZE = env("SATELLITE_SIZE", default="640x480")
SATELLITE_ZOOM = env.int("SATELLITE_ZOOM", default=19)

# Detection thresholds
VACANCY_THRESHOLD = env.float("VACANCY_THRESHOLD", default=0.6)
DEMOLITION_THRESHOLD = env.float("DEMOLITION_THRESHOLD", default=0.7)

# Pipeline concurrency
GEOCODE_CONCURRENCY = env.int("GEOCODE_CONCURRENCY", default=8)
IMAGERY_CONCURRENCY = env.int("IMAGERY_CONCURRENCY", default=6)
DETECTION_WORKERS = env.int("DETECTION_WORKERS", default=4)
PIPELINE_BATCH_SIZE = env.int("PIPELINE_BATCH_SIZE", default=100)

# Google Maps API endpoints
STREETVIEW_URL = "https://maps.googleapis.com/maps/api/streetview"
STREETVIEW_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Image cache directory (separate from MEDIA_ROOT if desired)
IMAGE_CACHE_DIR = Path(env("IMAGE_CACHE_DIR", default=str(MEDIA_ROOT)))
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
