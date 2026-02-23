import asyncio
import httpx
from datetime import datetime
from typing import Optional
from app.config import (
    GOOGLE_MAPS_API_KEY, STREETVIEW_URL, STREETVIEW_METADATA_URL,
    STATIC_MAP_URL, STREETVIEW_SIZE, SATELLITE_SIZE, SATELLITE_ZOOM,
)
from app.utils.images import get_image_path, save_image, image_exists


class ImageryResult:
    def __init__(
        self,
        streetview_path: str = "",
        streetview_available: bool = False,
        streetview_date: str = "",
        satellite_path: str = "",
    ):
        self.streetview_path = streetview_path
        self.streetview_available = streetview_available
        self.streetview_date = streetview_date
        self.satellite_path = satellite_path


async def check_streetview_availability(
    lat: float, lng: float, client: httpx.AsyncClient
) -> tuple[bool, str]:
    """
    Check if Street View imagery exists for a location.
    Returns (available, date_string).
    """
    response = await client.get(STREETVIEW_METADATA_URL, params={
        "location": f"{lat},{lng}",
        "key": GOOGLE_MAPS_API_KEY,
        "source": "outdoor",
    })

    if response.status_code != 200:
        return False, ""

    data = response.json()
    if data.get("status") != "OK":
        return False, ""

    # Extract the image date if available
    date_str = data.get("date", "")
    return True, date_str


async def fetch_streetview_image(
    lat: float, lng: float, address: str, client: httpx.AsyncClient
) -> tuple[str, bool, str]:
    """
    Fetch a Street View image for the given coordinates.
    Returns (file_path, available, date).
    """
    # Check cache first
    if image_exists(address, "streetview"):
        path = get_image_path(address, "streetview")
        # We don't have the date cached, but the image exists
        return str(path), True, ""

    # Check availability
    available, date_str = await check_streetview_availability(lat, lng, client)
    if not available:
        return "", False, ""

    # Fetch the actual image
    response = await client.get(STREETVIEW_URL, params={
        "location": f"{lat},{lng}",
        "size": STREETVIEW_SIZE,
        "key": GOOGLE_MAPS_API_KEY,
        "source": "outdoor",
        "return_error_code": "true",
    })

    if response.status_code != 200:
        return "", False, date_str

    # Save to cache
    path = get_image_path(address, "streetview")
    if save_image(response.content, path):
        return str(path), True, date_str

    return "", False, date_str


async def fetch_satellite_image(
    lat: float, lng: float, address: str, client: httpx.AsyncClient
) -> str:
    """
    Fetch a satellite/aerial image for the given coordinates.
    Returns file_path or empty string.
    """
    # Check cache first
    if image_exists(address, "satellite"):
        return str(get_image_path(address, "satellite"))

    response = await client.get(STATIC_MAP_URL, params={
        "center": f"{lat},{lng}",
        "zoom": SATELLITE_ZOOM,
        "size": SATELLITE_SIZE,
        "maptype": "satellite",
        "key": GOOGLE_MAPS_API_KEY,
    })

    if response.status_code != 200:
        return ""

    path = get_image_path(address, "satellite")
    if save_image(response.content, path):
        return str(path)

    return ""


async def fetch_imagery_for_property(
    lat: float, lng: float, address: str
) -> ImageryResult:
    """
    Fetch both Street View and satellite imagery for a single property.
    """
    if not GOOGLE_MAPS_API_KEY:
        return ImageryResult()

    async with httpx.AsyncClient(timeout=15.0) as client:
        sv_path, sv_available, sv_date = await fetch_streetview_image(lat, lng, address, client)
        sat_path = await fetch_satellite_image(lat, lng, address, client)

    return ImageryResult(
        streetview_path=sv_path,
        streetview_available=sv_available,
        streetview_date=sv_date,
        satellite_path=sat_path,
    )


async def batch_fetch_imagery(
    properties: list[dict],
) -> dict[int, ImageryResult]:
    """
    Fetch imagery for multiple properties concurrently.
    Each property dict should have: id, latitude, longitude, address.
    Returns dict mapping property_id -> ImageryResult.
    """
    results = {}

    if not GOOGLE_MAPS_API_KEY:
        return results

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Process in batches of 5 to avoid rate limits
        batch_size = 5
        for i in range(0, len(properties), batch_size):
            batch = properties[i:i + batch_size]

            async def fetch_one(prop):
                lat, lng = prop["latitude"], prop["longitude"]
                addr = prop["address"]
                if lat is None or lng is None:
                    return prop["id"], ImageryResult()
                sv_path, sv_avail, sv_date = await fetch_streetview_image(lat, lng, addr, client)
                sat_path = await fetch_satellite_image(lat, lng, addr, client)
                return prop["id"], ImageryResult(
                    streetview_path=sv_path,
                    streetview_available=sv_avail,
                    streetview_date=sv_date,
                    satellite_path=sat_path,
                )

            tasks = [fetch_one(p) for p in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    continue
                prop_id, imagery = result
                results[prop_id] = imagery

            if i + batch_size < len(properties):
                await asyncio.sleep(0.3)

    return results
