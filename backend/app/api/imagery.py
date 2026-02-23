import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
import aiosqlite

from app.models.database import get_db
from app.services.geocoder import geocode_address, batch_geocode
from app.services.imagery import fetch_imagery_for_property, batch_fetch_imagery
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


@router.get("/image/{property_id}/{image_type}")
async def get_image(property_id: int, image_type: str, db: aiosqlite.Connection = Depends(get_db)):
    """Serve a cached image file. image_type: streetview or satellite."""
    if image_type not in ("streetview", "satellite"):
        raise HTTPException(status_code=400, detail="image_type must be 'streetview' or 'satellite'")

    column = f"{image_type}_path"
    cursor = await db.execute(f"SELECT {column} FROM properties WHERE id = ?", [property_id])
    row = await cursor.fetchone()

    if not row or not row[column]:
        raise HTTPException(status_code=404, detail=f"No {image_type} image for this property")

    path = Path(row[column])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    return FileResponse(path, media_type="image/jpeg")
