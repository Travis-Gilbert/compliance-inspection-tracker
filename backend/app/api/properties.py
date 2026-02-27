import json
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, UploadFile, Query, HTTPException
from fastapi.responses import PlainTextResponse
import aiosqlite

from app.models.database import get_db
from app.models.property import (
    PropertyCreate, PropertyUpdate, PropertyResponse,
    StatsResponse, ImportResult, RESOLVED_FINDINGS, FindingType,
)
from app.services.csv_parser import parse_csv_text
from app.services.exporter import (
    export_properties_csv, export_inspection_list_csv, generate_summary_report,
)

router = APIRouter(prefix="/api/properties", tags=["properties"])


def row_to_dict(row) -> dict:
    """Convert an aiosqlite Row to a dict."""
    return dict(row)


# --- List & Filter ---

@router.get("/")
async def list_properties(
    finding: str = Query(None),
    detection: str = Query(None),
    program: str = Query(None),
    reviewed: bool = Query(None),
    search: str = Query(None),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    limit: int = Query(200),
    offset: int = Query(0),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List properties with optional filters. Returns {properties, total, limit, offset}."""
    conditions = []
    params = []

    if finding:
        conditions.append("finding = ?")
        params.append(finding)
    if detection:
        conditions.append("detection_label = ?")
        params.append(detection)
    if program:
        conditions.append("program = ?")
        params.append(program)
    if reviewed is True:
        conditions.append("finding != ''")
    elif reviewed is False:
        conditions.append("(finding = '' OR finding IS NULL)")
    if search:
        conditions.append("(address LIKE ? OR parcel_id LIKE ? OR buyer_name LIKE ?)")
        params.extend([f"%{search}%"] * 3)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    allowed_sorts = ["created_at", "address", "detection_score", "reviewed_at", "program"]
    sort_col = sort if sort in allowed_sorts else "created_at"
    sort_order = "ASC" if order.lower() == "asc" else "DESC"

    # Get total count for pagination
    count_query = f"SELECT COUNT(*) as n FROM properties p {where}"
    count_cursor = await db.execute(count_query, params[:])
    total = (await count_cursor.fetchone())["n"]

    query = f"""
        SELECT p.*, COALESCE(
            (SELECT COUNT(*) FROM communications c WHERE c.property_id = p.id), 0
        ) as communication_count
        FROM properties p
        {where}
        ORDER BY {sort_col} {sort_order}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return {"properties": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


# --- Single Property ---

@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(property_id: int, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("""
        SELECT p.*, COALESCE(
            (SELECT COUNT(*) FROM communications c WHERE c.property_id = p.id), 0
        ) as communication_count
        FROM properties p WHERE p.id = ?
    """, [property_id])
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Property not found")
    return dict(row)


@router.post("/", response_model=PropertyResponse)
async def create_property(prop: PropertyCreate, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("""
        INSERT INTO properties (address, parcel_id, buyer_name, program, closing_date, commitment)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [prop.address, prop.parcel_id, prop.buyer_name, prop.program, prop.closing_date, prop.commitment])
    await db.commit()

    return await get_property(cursor.lastrowid, db)


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: int,
    updates: PropertyUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    # Build dynamic update
    fields = []
    values = []
    update_data = updates.model_dump(exclude_none=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    for field, value in update_data.items():
        fields.append(f"{field} = ?")
        values.append(value)

    # Auto-set reviewed_at when finding is set
    if "finding" in update_data and update_data["finding"]:
        fields.append("reviewed_at = ?")
        values.append(datetime.now().isoformat())

    fields.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(property_id)

    await db.execute(
        f"UPDATE properties SET {', '.join(fields)} WHERE id = ?",
        values,
    )
    await db.commit()

    return await get_property(property_id, db)


@router.delete("/{property_id}")
async def delete_property(property_id: int, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM properties WHERE id = ?", [property_id])
    await db.commit()
    return {"deleted": True}


# --- Batch Update ---

from pydantic import BaseModel
from typing import List


class BatchUpdateRequest(BaseModel):
    property_ids: List[int]
    finding: str
    notes: str = ""


@router.post("/batch-update")
async def batch_update_properties(req: BatchUpdateRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Batch update finding for multiple properties at once."""
    now = datetime.now().isoformat()
    updated = 0
    for pid in req.property_ids:
        await db.execute("""
            UPDATE properties SET finding=?, reviewed_at=?, updated_at=?
            WHERE id=?
        """, [req.finding, now, now, pid])
        if req.notes:
            await db.execute("""
                UPDATE properties SET notes=CASE
                    WHEN notes IS NULL OR notes='' THEN ?
                    ELSE notes || '\n' || ?
                END WHERE id=?
            """, [req.notes, req.notes, pid])
        updated += 1
    await db.commit()
    return {"updated": updated}


# --- CSV Import ---

@router.post("/import", response_model=ImportResult)
async def import_csv(
    file: UploadFile = File(None),
    text: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Import properties from CSV file or pasted text."""
    if file:
        content = (await file.read()).decode("utf-8-sig")
        filename = file.filename or "upload.csv"
    elif text:
        content = text
        filename = "pasted_text"
    else:
        raise HTTPException(status_code=400, detail="Provide a file or text")

    properties, errors, batch_id = parse_csv_text(content, filename)

    if not properties and errors:
        raise HTTPException(status_code=400, detail=f"Parse errors: {'; '.join(errors[:5])}")

    # Insert batch record
    await db.execute(
        "INSERT INTO import_batches (id, filename, row_count) VALUES (?, ?, ?)",
        [batch_id, filename, len(properties)],
    )

    # Insert properties
    imported = 0
    for prop in properties:
        try:
            await db.execute("""
                INSERT INTO properties (address, parcel_id, buyer_name, program, closing_date, commitment, import_batch)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [prop.address, prop.parcel_id, prop.buyer_name, prop.program,
                  prop.closing_date, prop.commitment, batch_id])
            imported += 1
        except Exception as e:
            errors.append(f"Insert error for {prop.address}: {str(e)}")

    await db.commit()

    return ImportResult(
        batch_id=batch_id,
        total_rows=len(properties) + len(errors),
        imported=imported,
        skipped=len(properties) - imported,
        errors=errors[:10],
    )


# --- Stats ---

@router.get("/stats/summary", response_model=StatsResponse)
async def get_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Get aggregate statistics for the dashboard."""
    cursor = await db.execute("SELECT COUNT(*) as n FROM properties")
    total = (await cursor.fetchone())["n"]

    cursor = await db.execute("SELECT COUNT(*) as n FROM properties WHERE finding != '' AND finding IS NOT NULL")
    reviewed = (await cursor.fetchone())["n"]

    resolved_values = ", ".join(f"'{f.value}'" for f in RESOLVED_FINDINGS)
    cursor = await db.execute(f"SELECT COUNT(*) as n FROM properties WHERE finding IN ({resolved_values})")
    resolved = (await cursor.fetchone())["n"]

    cursor = await db.execute("SELECT COUNT(*) as n FROM properties WHERE finding = 'inconclusive'")
    needs_inspection = (await cursor.fetchone())["n"]

    cursor = await db.execute("SELECT COUNT(*) as n FROM properties WHERE latitude IS NOT NULL")
    geocoded = (await cursor.fetchone())["n"]

    cursor = await db.execute("SELECT COUNT(*) as n FROM properties WHERE imagery_fetched_at IS NOT NULL")
    imagery_fetched = (await cursor.fetchone())["n"]

    cursor = await db.execute("SELECT COUNT(*) as n FROM properties WHERE detection_ran_at IS NOT NULL")
    detection_ran = (await cursor.fetchone())["n"]

    # By finding
    cursor = await db.execute("""
        SELECT finding, COUNT(*) as n FROM properties
        WHERE finding != '' AND finding IS NOT NULL
        GROUP BY finding
    """)
    by_finding = {row["finding"]: row["n"] for row in await cursor.fetchall()}

    # By program
    cursor = await db.execute("SELECT program, COUNT(*) as n FROM properties GROUP BY program")
    by_program = {row["program"] or "Unknown": row["n"] for row in await cursor.fetchall()}

    # By detection
    cursor = await db.execute("""
        SELECT detection_label, COUNT(*) as n FROM properties
        WHERE detection_label != '' AND detection_label IS NOT NULL
        GROUP BY detection_label
    """)
    by_detection = {row["detection_label"]: row["n"] for row in await cursor.fetchall()}

    return StatsResponse(
        total=total,
        unreviewed=total - reviewed,
        reviewed=reviewed,
        resolved=resolved,
        needs_inspection=needs_inspection,
        geocoded=geocoded,
        imagery_fetched=imagery_fetched,
        detection_ran=detection_ran,
        by_finding=by_finding,
        by_program=by_program,
        by_detection=by_detection,
        percent_reviewed=round(reviewed / total * 100, 1) if total > 0 else 0,
    )


# --- Export ---

@router.get("/export/csv")
async def export_csv(
    finding: str = Query(None),
    detection: str = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Export properties to CSV."""
    conditions = []
    params = []
    if finding:
        conditions.append("finding = ?")
        params.append(finding)
    if detection:
        conditions.append("detection_label = ?")
        params.append(detection)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor = await db.execute(f"SELECT * FROM properties {where} ORDER BY address", params)
    rows = await cursor.fetchall()
    properties = [dict(r) for r in rows]

    csv_text = export_properties_csv(properties)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=compliance-export-{datetime.now().strftime('%Y%m%d')}.csv"},
    )


@router.get("/export/inspection-list")
async def export_inspection_list(db: aiosqlite.Connection = Depends(get_db)):
    """Export properties needing physical inspection."""
    cursor = await db.execute("""
        SELECT * FROM properties
        WHERE finding = 'inconclusive' OR detection_label IN ('likely_vacant', 'likely_demolished')
        ORDER BY detection_score DESC
    """)
    rows = await cursor.fetchall()
    csv_text = export_inspection_list_csv([dict(r) for r in rows])
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=inspection-list-{datetime.now().strftime('%Y%m%d')}.csv"},
    )


@router.get("/export/summary")
async def export_summary(db: aiosqlite.Connection = Depends(get_db)):
    """Generate a text summary report."""
    stats_response = await get_stats(db)
    report = generate_summary_report(stats_response.model_dump())
    return PlainTextResponse(content=report, media_type="text/plain")
