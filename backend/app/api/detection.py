import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

from app.models.database import get_db
from app.services.detector import detect_property_condition, batch_detect

router = APIRouter(prefix="/api/detection", tags=["detection"])


@router.post("/analyze/{property_id}")
async def analyze_property(property_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Run smart detection on a single property's imagery."""
    cursor = await db.execute(
        "SELECT streetview_path, satellite_path, streetview_available FROM properties WHERE id = ?",
        [property_id],
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")

    if not row["streetview_path"] and not row["satellite_path"]:
        raise HTTPException(
            status_code=422,
            detail="No imagery available. Fetch imagery first.",
        )

    result = detect_property_condition(
        streetview_path=row["streetview_path"] or None,
        satellite_path=row["satellite_path"] or None,
    )

    await db.execute("""
        UPDATE properties SET
            detection_score = ?, detection_label = ?, detection_details = ?,
            detection_ran_at = ?, updated_at = ?
        WHERE id = ?
    """, [result.score, result.label, json.dumps(result.details),
          datetime.now().isoformat(), datetime.now().isoformat(), property_id])
    await db.commit()

    return {
        "property_id": property_id,
        "score": result.score,
        "label": result.label,
        "details": result.details,
    }


@router.post("/analyze-batch")
async def analyze_batch(
    limit: int = Query(50, description="Max properties to analyze"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Run detection on all properties with imagery but no detection results."""
    cursor = await db.execute("""
        SELECT id, streetview_path, satellite_path FROM properties
        WHERE imagery_fetched_at IS NOT NULL AND detection_ran_at IS NULL
        LIMIT ?
    """, [limit])
    rows = await cursor.fetchall()

    if not rows:
        return {"analyzed": 0, "message": "All properties with imagery already analyzed"}

    props = [dict(r) for r in rows]
    results = await batch_detect(props)

    analyzed = 0
    for prop_id, result in results.items():
        await db.execute("""
            UPDATE properties SET
                detection_score = ?, detection_label = ?, detection_details = ?,
                detection_ran_at = ?, updated_at = ?
            WHERE id = ?
        """, [result.score, result.label, json.dumps(result.details),
              datetime.now().isoformat(), datetime.now().isoformat(), prop_id])
        analyzed += 1

    await db.commit()

    # Summary of results
    label_counts = {}
    for result in results.values():
        label_counts[result.label] = label_counts.get(result.label, 0) + 1

    return {
        "analyzed": analyzed,
        "total_attempted": len(rows),
        "results_summary": label_counts,
    }


@router.get("/summary")
async def detection_summary(db: aiosqlite.Connection = Depends(get_db)):
    """Get a summary of detection results across all properties."""
    cursor = await db.execute("""
        SELECT
            detection_label,
            COUNT(*) as count,
            AVG(detection_score) as avg_score,
            MIN(detection_score) as min_score,
            MAX(detection_score) as max_score
        FROM properties
        WHERE detection_ran_at IS NOT NULL
        GROUP BY detection_label
    """)
    rows = await cursor.fetchall()

    cursor2 = await db.execute("SELECT COUNT(*) as n FROM properties WHERE detection_ran_at IS NULL AND imagery_fetched_at IS NOT NULL")
    pending = (await cursor2.fetchone())["n"]

    return {
        "results": [
            {
                "label": row["detection_label"],
                "count": row["count"],
                "avg_score": round(row["avg_score"], 3) if row["avg_score"] else 0,
                "min_score": round(row["min_score"], 3) if row["min_score"] else 0,
                "max_score": round(row["max_score"], 3) if row["max_score"] else 0,
            }
            for row in rows
        ],
        "pending_analysis": pending,
    }
