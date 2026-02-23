import httpx
from typing import Optional
from app.config import GOOGLE_MAPS_API_KEY, GEOCODE_URL
from app.utils.address import build_full_address


class GeocodingResult:
    def __init__(self, lat: float, lng: float, formatted_address: str):
        self.lat = lat
        self.lng = lng
        self.formatted_address = formatted_address


async def geocode_address(address: str) -> Optional[GeocodingResult]:
    """
    Convert a street address to lat/lng coordinates.
    Appends Flint, MI if no city is detected.
    """
    if not GOOGLE_MAPS_API_KEY:
        return None

    full_address = build_full_address(address)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(GEOCODE_URL, params={
            "address": full_address,
            "key": GOOGLE_MAPS_API_KEY,
            # Bias results toward Genesee County
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


async def batch_geocode(addresses: list[str]) -> dict[str, Optional[GeocodingResult]]:
    """
    Geocode multiple addresses concurrently.
    Returns a dict mapping address -> GeocodingResult.
    """
    import asyncio

    results = {}

    # Process in batches of 10 to avoid rate limits
    batch_size = 10
    for i in range(0, len(addresses), batch_size):
        batch = addresses[i:i + batch_size]
        tasks = [geocode_address(addr) for addr in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for addr, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                results[addr] = None
            else:
                results[addr] = result

        # Small delay between batches to respect rate limits
        if i + batch_size < len(addresses):
            await asyncio.sleep(0.2)

    return results
