"""
Google Street View and satellite imagery fetching.

Carried over from FastAPI backend. Framework-agnostic (httpx + file I/O).
Only change: reads config from Django settings.
"""
import asyncio
from typing import Awaitable, Callable, Optional

import httpx
from django.conf import settings

from tracker.utils.images import get_image_path, image_exists, save_image


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


async def _request_with_semaphore(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> httpx.Response:
    if semaphore:
        async with semaphore:
            return await client.get(url, params=params)
    return await client.get(url, params=params)


async def check_streetview_availability(
    lat: float,
    lng: float,
    client: httpx.AsyncClient,
    semaphore: Optional[asyncio.Semaphore] = None,
    date: Optional[str] = None,
) -> tuple[bool, str]:
    """Check if Street View imagery exists for a location."""
    params = {
        "location": f"{lat},{lng}",
        "key": settings.GOOGLE_MAPS_API_KEY,
        "source": "outdoor",
    }
    if date:
        params["date"] = date

    response = await _request_with_semaphore(
        client, settings.STREETVIEW_METADATA_URL, params=params, semaphore=semaphore,
    )

    if response.status_code != 200:
        return False, ""

    data = response.json()
    if data.get("status") != "OK":
        return False, ""

    return True, data.get("date", date or "")


async def fetch_streetview_image(
    lat: float,
    lng: float,
    address: str,
    client: httpx.AsyncClient,
    semaphore: Optional[asyncio.Semaphore] = None,
    date: Optional[str] = None,
    cache_suffix: str = "streetview",
) -> tuple[str, bool, str]:
    """Fetch a Street View image. Returns (file_path, available, date)."""
    if image_exists(address, cache_suffix):
        path = get_image_path(address, cache_suffix)
        return str(path), True, date or ""

    available, date_str = await check_streetview_availability(
        lat, lng, client, semaphore=semaphore, date=date,
    )
    if not available:
        return "", False, ""

    params = {
        "location": f"{lat},{lng}",
        "size": settings.STREETVIEW_SIZE,
        "key": settings.GOOGLE_MAPS_API_KEY,
        "source": "outdoor",
        "return_error_code": "true",
    }
    if date:
        params["date"] = date

    response = await _request_with_semaphore(
        client, settings.STREETVIEW_URL, params=params, semaphore=semaphore,
    )
    if response.status_code != 200:
        return "", False, date_str

    path = get_image_path(address, cache_suffix)
    if save_image(response.content, path):
        return str(path), True, date_str
    return "", False, date_str


async def fetch_historical_streetview(
    lat: float,
    lng: float,
    address: str,
    target_date: str,
    client: Optional[httpx.AsyncClient] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> tuple[str, bool, str]:
    """Fetch a Street View image closest to target_date ("YYYY-MM")."""
    if not settings.GOOGLE_MAPS_API_KEY:
        return "", False, ""

    cache_suffix = f"streetview_historical_{target_date.replace('-', '')}"
    if image_exists(address, cache_suffix):
        path = get_image_path(address, cache_suffix)
        return str(path), True, target_date

    if client:
        return await fetch_streetview_image(
            lat, lng, address, client, semaphore=semaphore,
            date=target_date, cache_suffix=cache_suffix,
        )

    async with httpx.AsyncClient(timeout=15.0) as local_client:
        return await fetch_streetview_image(
            lat, lng, address, local_client, semaphore=semaphore,
            date=target_date, cache_suffix=cache_suffix,
        )


async def fetch_satellite_image(
    lat: float,
    lng: float,
    address: str,
    client: httpx.AsyncClient,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> str:
    """Fetch a satellite/aerial image. Returns file_path or empty string."""
    if image_exists(address, "satellite"):
        return str(get_image_path(address, "satellite"))

    response = await _request_with_semaphore(
        client, settings.STATIC_MAP_URL,
        params={
            "center": f"{lat},{lng}",
            "zoom": settings.SATELLITE_ZOOM,
            "size": settings.SATELLITE_SIZE,
            "maptype": "satellite",
            "key": settings.GOOGLE_MAPS_API_KEY,
        },
        semaphore=semaphore,
    )
    if response.status_code != 200:
        return ""

    path = get_image_path(address, "satellite")
    if save_image(response.content, path):
        return str(path)
    return ""


async def fetch_imagery_for_property(
    lat: float,
    lng: float,
    address: str,
    client: Optional[httpx.AsyncClient] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> ImageryResult:
    """Fetch both Street View and satellite imagery for a single property."""
    if not settings.GOOGLE_MAPS_API_KEY:
        return ImageryResult()

    async def _fetch(shared_client: httpx.AsyncClient) -> ImageryResult:
        sv_path, sv_available, sv_date = await fetch_streetview_image(
            lat, lng, address, shared_client, semaphore=semaphore,
        )
        sat_path = await fetch_satellite_image(
            lat, lng, address, shared_client, semaphore=semaphore,
        )
        return ImageryResult(
            streetview_path=sv_path,
            streetview_available=sv_available,
            streetview_date=sv_date,
            satellite_path=sat_path,
        )

    if client:
        return await _fetch(client)

    async with httpx.AsyncClient(timeout=15.0) as local_client:
        return await _fetch(local_client)


async def batch_fetch_imagery(
    properties: list[dict],
    concurrency: Optional[int] = None,
    client: Optional[httpx.AsyncClient] = None,
    on_result: Optional[Callable[[int, ImageryResult, int, int], Awaitable[None] | None]] = None,
) -> dict[int, ImageryResult]:
    """Fetch imagery for multiple properties concurrently."""
    if concurrency is None:
        concurrency = settings.IMAGERY_CONCURRENCY

    if not properties:
        return {}
    if not settings.GOOGLE_MAPS_API_KEY:
        return {prop["id"]: ImageryResult() for prop in properties}

    total = len(properties)
    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: dict[int, ImageryResult] = {}

    async def fetch_one(prop: dict, shared_client: httpx.AsyncClient) -> tuple[int, ImageryResult]:
        prop_id = prop["id"]
        lat = prop.get("latitude")
        lng = prop.get("longitude")
        addr = prop.get("address", "")
        if lat is None or lng is None:
            return prop_id, ImageryResult()
        try:
            result = await fetch_imagery_for_property(
                lat, lng, addr, client=shared_client, semaphore=semaphore,
            )
            return prop_id, result
        except Exception:
            return prop_id, ImageryResult()

    async def run_batch(shared_client: httpx.AsyncClient):
        tasks = [
            asyncio.create_task(fetch_one(prop, shared_client))
            for prop in properties
        ]
        for current, task in enumerate(asyncio.as_completed(tasks), start=1):
            prop_id, imagery = await task
            results[prop_id] = imagery
            if on_result:
                maybe_coro = on_result(prop_id, imagery, current, total)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro

    if client:
        await run_batch(client)
        return results

    async with httpx.AsyncClient(timeout=15.0) as shared_client:
        await run_batch(shared_client)
    return results
