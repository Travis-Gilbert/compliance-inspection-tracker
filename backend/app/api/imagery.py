from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
import aiosqlite

from app.models.database import get_db
from app.services.geocoder import geocode_address, batch_geocode
from app.services.imagery import (
    fetch_imagery_for_property,
    batch_fetch_imagery,
    fetch_historical_streetview,
    batch_fetch_historical_imagery,
)
from app.services.enrichment import parse_closing_date
from app.config import GOOGLE_MAPS_API_KEY

router = APIRouter(prefix="/api/imagery", tags=["imagery"])


@router.get("/status")
async def api_status():
    """Check if Google Maps API is configured."""
    return {
        "configured": bool(GOOGLE_MAPS_API_KEY),
        "key_preview": GOOGLE_MAPS_API_KEY[:8] + "..." if GOOGLE_MAPS_API_KEY else None,
    }


@router.post("/geocode/{property_id}")
async def geocode_property(property_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Geocode a single property's address."""
    cursor = await db.execute("SELECT address FROM properties WHERE id = ?", [property_id])
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")

    result = await geocode_address(row["address"])
    if not result:
        raise HTTPException(status_code=422, detail="Could not geocode address")

    await db.execute("""
        UPDATE properties SET
            latitude = ?, longitude = ?, formatted_address = ?, geocoded_at = ?, updated_at = ?
        WHERE id = ?
    """, [result.lat, result.lng, result.formatted_address, datetime.now().isoformat(),
          datetime.now().isoformat(), property_id])
    await db.commit()

    return {
        "property_id": property_id,
        "latitude": result.lat,
        "longitude": result.lng,
        "formatted_address": result.formatted_address,
    }


@router.post("/geocode-batch")
async def geocode_batch(
    limit: int = Query(50, description="Max properties to geocode"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Geocode all un-geocoded properties."""
    cursor = await db.execute(
        "SELECT id, address FROM properties WHERE latitude IS NULL LIMIT ?",
        [limit],
    )
    rows = await cursor.fetchall()
    if not rows:
        return {"geocoded": 0, "message": "All properties already geocoded"}

    addresses = [row["address"] for row in rows]
    results = await batch_geocode(addresses)

    geocoded = 0
    for row in rows:
        result = results.get(row["address"])
        if result:
            await db.execute("""
                UPDATE properties SET
                    latitude = ?, longitude = ?, formatted_address = ?, geocoded_at = ?, updated_at = ?
                WHERE id = ?
            """, [result.lat, result.lng, result.formatted_address,
                  datetime.now().isoformat(), datetime.now().isoformat(), row["id"]])
            geocoded += 1

    await db.commit()
    return {"geocoded": geocoded, "total_attempted": len(rows)}


@router.post("/fetch/{property_id}")
async def fetch_property_imagery(property_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Fetch Street View and satellite imagery for a single property."""
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=503, detail="Google Maps API key is not configured")

    cursor = await db.execute(
        "SELECT address, latitude, longitude FROM properties WHERE id = ?",
        [property_id],
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")
    if row["latitude"] is None:
        raise HTTPException(status_code=422, detail="Property not geocoded yet. Run geocode first.")

    result = await fetch_imagery_for_property(row["latitude"], row["longitude"], row["address"])

    await db.execute("""
        UPDATE properties SET
            streetview_path = ?, streetview_available = ?, streetview_date = ?,
            satellite_path = ?, imagery_fetched_at = ?, updated_at = ?
        WHERE id = ?
    """, [result.streetview_path, 1 if result.streetview_available else 0,
          result.streetview_date, result.satellite_path,
          datetime.now().isoformat(), datetime.now().isoformat(), property_id])
    await db.commit()

    return {
        "property_id": property_id,
        "streetview_available": result.streetview_available,
        "streetview_date": result.streetview_date,
        "satellite_fetched": bool(result.satellite_path),
    }


@router.post("/fetch-batch")
async def fetch_batch_imagery(
    limit: int = Query(25, description="Max properties to fetch imagery for"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Fetch imagery for all geocoded properties that don't have images yet."""
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=503, detail="Google Maps API key is not configured")

    cursor = await db.execute("""
        SELECT id, address, latitude, longitude FROM properties
        WHERE latitude IS NOT NULL AND imagery_fetched_at IS NULL
        LIMIT ?
    """, [limit])
    rows = await cursor.fetchall()
    if not rows:
        return {"fetched": 0, "message": "All geocoded properties already have imagery"}

    props = [dict(r) for r in rows]
    results = await batch_fetch_imagery(props)

    fetched = 0
    for prop_id, result in results.items():
        await db.execute("""
            UPDATE properties SET
                streetview_path = ?, streetview_available = ?, streetview_date = ?,
                satellite_path = ?, imagery_fetched_at = ?, updated_at = ?
            WHERE id = ?
        """, [result.streetview_path, 1 if result.streetview_available else 0,
              result.streetview_date, result.satellite_path,
              datetime.now().isoformat(), datetime.now().isoformat(), prop_id])
        fetched += 1

    await db.commit()
    return {"fetched": fetched, "total_attempted": len(rows)}


@router.post("/fetch-historical/{property_id}")
async def fetch_historical_imagery(property_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """
    Fetch and cache historical Street View imagery using the closing date.
    """
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=503, detail="Google Maps API key is not configured")

    cursor = await db.execute(
        """
        SELECT address, latitude, longitude, closing_date,
               streetview_historical_path, streetview_historical_date
        FROM properties WHERE id = ?
        """,
        [property_id],
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")
    if row["latitude"] is None or row["longitude"] is None:
        raise HTTPException(status_code=422, detail="Property not geocoded yet")

    parsed = parse_closing_date(row["closing_date"] or "")
    if not parsed:
        raise HTTPException(status_code=422, detail="No usable closing date available")
    target_date = parsed.strftime("%Y-%m")

    path, available, actual_date = await fetch_historical_streetview(
        lat=row["latitude"],
        lng=row["longitude"],
        address=row["address"],
        target_date=target_date,
    )

    await db.execute(
        """
        UPDATE properties
        SET streetview_historical_path = ?,
            streetview_historical_date = ?,
            historical_imagery_checked_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        [
            path if available else "",
            actual_date if available else "",
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            property_id,
        ],
    )
    await db.commit()

    return {
        "property_id": property_id,
        "historical_available": available,
        "target_date": target_date,
        "actual_date": actual_date,
        "streetview_historical_path": path,
    }


@router.post("/fetch-historical-batch")
async def fetch_historical_batch(
    limit: int = Query(25, description="Max properties to fetch historical imagery for"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Fetch historical Street View imagery near the closing date for properties with current coverage."""
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=503, detail="Google Maps API key is not configured")

    cursor = await db.execute(
        """
        SELECT id, address, latitude, longitude, closing_date FROM properties
        WHERE streetview_available = 1
          AND COALESCE(closing_date, '') != ''
          AND COALESCE(historical_imagery_checked_at, '') = ''
        LIMIT ?
        """,
        [limit],
    )
    rows = await cursor.fetchall()
    if not rows:
        return {"fetched": 0, "message": "All eligible properties already have historical imagery checked"}

    results = await batch_fetch_historical_imagery([dict(row) for row in rows])

    fetched = 0
    available = 0
    now = datetime.now().isoformat()
    for row in rows:
        result = results.get(row["id"])
        if result is None:
            continue
        await db.execute(
            """
            UPDATE properties
            SET streetview_historical_path = ?,
                streetview_historical_date = ?,
                historical_imagery_checked_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            [
                result.streetview_historical_path if result.historical_available else "",
                result.streetview_historical_date if result.historical_available else "",
                now,
                now,
                row["id"],
            ],
        )
        fetched += 1
        if result.historical_available:
            available += 1

    await db.commit()
    return {
        "fetched": fetched,
        "available": available,
        "total_attempted": len(rows),
    }


@router.get("/image/{property_id}/{image_type}")
async def get_image(property_id: int, image_type: str, db: aiosqlite.Connection = Depends(get_db)):
    """Serve a cached image file."""
    image_column_map = {
        "streetview": "streetview_path",
        "satellite": "satellite_path",
        "streetview_historical": "streetview_historical_path",
    }
    column = image_column_map.get(image_type)
    if not column:
        raise HTTPException(
            status_code=400,
            detail="image_type must be one of: streetview, satellite, streetview_historical",
        )

    cursor = await db.execute(f"SELECT {column} FROM properties WHERE id = ?", [property_id])
    row = await cursor.fetchone()

    if not row or not row[column]:
        raise HTTPException(status_code=404, detail=f"No {image_type} image for this property")

    path = Path(row[column])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    return FileResponse(path, media_type="image/jpeg")
