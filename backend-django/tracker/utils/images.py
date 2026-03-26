"""
Image caching utilities.

Copied verbatim from backend/app/utils/images.py. Uses Django settings
for cache directory instead of app.config.
"""
import hashlib
from pathlib import Path

from django.conf import settings
from PIL import Image


def get_image_path(address: str, image_type: str, ext: str = "jpg") -> Path:
    """Generate a consistent file path for a cached image."""
    safe_name = hashlib.md5(address.lower().encode()).hexdigest()
    return settings.IMAGE_CACHE_DIR / f"{safe_name}_{image_type}.{ext}"


def save_image(data: bytes, path: Path) -> bool:
    """Save raw image bytes to disk."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True
    except Exception:
        return False


def create_thumbnail(source_path: Path, max_size: tuple = (320, 240)) -> Path:
    """Create a thumbnail version of an image."""
    thumb_path = source_path.with_stem(source_path.stem + "_thumb")
    try:
        with Image.open(source_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(thumb_path, "JPEG", quality=85)
        return thumb_path
    except Exception:
        return source_path


def image_exists(address: str, image_type: str) -> bool:
    """Check if we already have a cached image for this address."""
    path = get_image_path(address, image_type)
    return path.exists() and path.stat().st_size > 0
