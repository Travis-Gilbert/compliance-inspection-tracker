"""
Google Geocoding API service.

Carried over verbatim from FastAPI backend. Framework-agnostic (uses httpx).
Only change: reads config from Django settings instead of app.config.
"""
import asyncio
from typing import Awaitable, Callable, Optional

import httpx
from django.conf import settings

from tracker.utils.address import build_full_address


class GeocodingResult:
    def __init__(self, lat: float, lng: float, formatted_address: str):
        self.lat = lat
        self.lng = lng
        self.formatted_address = formatted_address


async def geocode_address(address: str) -> Optional[GeocodingResult]:
    """Convert a street address to lat/lng coordinates."""
    if not settings.GOOGLE_MAPS_API_KEY:
        return None

    full_address = build_full_address(address)
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await geocode_address_with_client(full_address, client)


async def geocode_address_with_client(
    full_address: str,
    client: httpx.AsyncClient,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> Optional[GeocodingResult]:
    async def _request() -> Optional[GeocodingResult]:
        response = await client.get(settings.GEOCODE_URL, params={
            "address": full_address,
            "key": settings.GOOGLE_MAPS_API_KEY,
            "bounds": "42.85,-83.95|43.20,-83.55",
        })

        if response.status_code != 200:
            return None

        data = response.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None

        result = data["results"][0]
        location = result["geometry"]["location"]
        return GeocodingResult(
            lat=location["lat"],
            lng=location["lng"],
            formatted_address=result.get("formatted_address", full_address),
        )

    if semaphore:
        async with semaphore:
            return await _request()
    return await _request()


async def batch_geocode(
    addresses: list[str],
    concurrency: Optional[int] = None,
    client: Optional[httpx.AsyncClient] = None,
    on_result: Optional[Callable[[str, Optional[GeocodingResult], int, int], Awaitable[None] | None]] = None,
) -> dict[str, Optional[GeocodingResult]]:
    """Geocode multiple addresses concurrently."""
    if concurrency is None:
        concurrency = settings.GEOCODE_CONCURRENCY

    results = {}
    if not addresses:
        return results
    if not settings.GOOGLE_MAPS_API_KEY:
        return {address: None for address in addresses}

    total = len(addresses)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def geocode_one(index: int, raw_address: str, shared_client: httpx.AsyncClient):
        try:
            full_address = build_full_address(raw_address)
            result = await geocode_address_with_client(full_address, shared_client, semaphore=semaphore)
        except Exception:
            result = None
        results[raw_address] = result
        if on_result:
            maybe_coro = on_result(raw_address, result, index + 1, total)
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro

    if client:
        await asyncio.gather(
            *(geocode_one(index, address, client) for index, address in enumerate(addresses)),
            return_exceptions=True,
        )
        return results

    async with httpx.AsyncClient(timeout=10.0) as shared_client:
        await asyncio.gather(
            *(geocode_one(index, address, shared_client) for index, address in enumerate(addresses)),
            return_exceptions=True,
        )
    return results
