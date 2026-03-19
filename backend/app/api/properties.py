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
from app.services.enrichment import (
    apply_priority_scores,
    filter_by_contact,
    haversine_clusters,
    summarize_buyers,
)
from app.utils.address import build_address_key

router = APIRouter(prefix="/api/properties", tags=["properties"])


def row_to_dict(row) -> dict:
    """Convert an aiosqlite Row to a dict."""
    return dict(row)


def resolved_values_sql() -> str:
    return ", ".join(f"'{f.value}'" for f in RESOLVED_FINDINGS)


async def find_existing_property(db: aiosqlite.Connection, prop: PropertyCreate):
    parcel_id = (prop.parcel_id or "").strip()
    if parcel_id:
        cursor = await db.execute(
            "SELECT id, address, address_key, parcel_id FROM properties WHERE parcel_id = ? LIMIT 1",
            [parcel_id],
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)

    address_key = build_address_key(prop.address)
    if not address_key:
        return None

    cursor = await db.execute(
        "SELECT id, address, address_key, parcel_id FROM properties WHERE address_key = ? LIMIT 1",
        [address_key],
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def merge_import_property(
    db: aiosqlite.Connection,
    property_id: int,
    prop: PropertyCreate,
    batch_id: str,
):
    await db.execute(
        """
        UPDATE properties
        SET address = COALESCE(NULLIF(?, ''), address),
            address_key = COALESCE(NULLIF(?, ''), address_key),
            parcel_id = COALESCE(NULLIF(?, ''), parcel_id),
            buyer_name = COALESCE(NULLIF(?, ''), buyer_name),
            program = COALESCE(NULLIF(?, ''), program),
            closing_date = COALESCE(NULLIF(?, ''), closing_date),
            commitment = COALESCE(NULLIF(?, ''), commitment),
            email = COALESCE(NULLIF(?, ''), email),
            organization = COALESCE(NULLIF(?, ''), organization),
            purchase_type = COALESCE(NULLIF(?, ''), purchase_type),
            compliance_1st_attempt = COALESCE(NULLIF(?, ''), compliance_1st_attempt),
            compliance_2nd_attempt = COALESCE(NULLIF(?, ''), compliance_2nd_attempt),
            streetview_historical_path = COALESCE(NULLIF(?, ''), streetview_historical_path),
            streetview_historical_date = COALESCE(NULLIF(?, ''), streetview_historical_date),
            import_batch = ?,
            updated_at = ?
        WHERE id = ?
        """,
        [
            prop.address,
            build_address_key(prop.address),
            prop.parcel_id,
            prop.buyer_name,
            prop.program,
            prop.closing_date,
            prop.commitment,
            prop.email,
            prop.organization,
            prop.purchase_type,
            prop.compliance_1st_attempt,
            prop.compliance_2nd_attempt,
            prop.streetview_historical_path,
            prop.streetview_historical_date,
            batch_id,
            datetime.now().isoformat(),
            property_id,
        ],
    )


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
        conditions.append("(address LIKE ? OR parcel_id LIKE ? OR buyer_name LIKE ? OR organization LIKE ? OR email LIKE ?)")
        params.extend([f"%{search}%"] * 5)

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


# --- Leadership & Enrichment ---

@router.get("/map/all")
async def get_map_properties(
    program: str = Query(None),
    contact: str = Query("all"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Return all geocoded properties with server-computed compliance priority.
    """
    conditions = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    params = []

    if program:
        conditions.append("program = ?")
        params.append(program)

    where = f"WHERE {' AND '.join(conditions)}"
    cursor = await db.execute(
        f"""
        SELECT id, address, parcel_id, buyer_name, program, closing_date, commitment,
               email, organization, purchase_type,
               compliance_1st_attempt, compliance_2nd_attempt,
               latitude, longitude, formatted_address,
               streetview_path, streetview_available, streetview_date,
               streetview_historical_path, streetview_historical_date,
               satellite_path, imagery_fetched_at,
               detection_label, detection_score,
               finding, notes, reviewed_at
        FROM properties
        {where}
        ORDER BY address ASC
        """,
        params,
    )
    rows = [dict(row) for row in await cursor.fetchall()]
    prioritized = apply_priority_scores(rows)
    prioritized = filter_by_contact(prioritized, contact)
    prioritized.sort(key=lambda row: (-float(row.get("priority_score", 0.0)), row.get("address", "")))
    return {"count": len(prioritized), "properties": prioritized}


@router.get("/buyers/summary")
async def get_buyers_summary(
    program: str = Query(None),
    contact: str = Query("all"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Return buyer portfolio rollups for leadership reporting.
    """
    conditions = []
    params = []
    if program:
        conditions.append("program = ?")
        params.append(program)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor = await db.execute(
        f"""
        SELECT id, address, parcel_id, buyer_name, program, closing_date,
               organization, compliance_1st_attempt, compliance_2nd_attempt,
               latitude, longitude, finding, detection_label, detection_score,
               streetview_available, satellite_path
        FROM properties
        {where}
        """,
        params,
    )
    rows = [dict(row) for row in await cursor.fetchall()]
    prioritized = apply_priority_scores(rows)
    prioritized = filter_by_contact(prioritized, contact)
    buyers = summarize_buyers(prioritized)
    return {"count": len(buyers), "buyers": buyers}


@router.get("/clusters")
async def get_property_clusters(
    program: str = Query(None),
    contact: str = Query("all"),
    radius_miles: float = Query(0.35, ge=0.05, le=5.0),
    min_points: int = Query(2, ge=2, le=100),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Return Haversine clusters for geocoded properties.
    """
    conditions = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    params = []
    if program:
        conditions.append("program = ?")
        params.append(program)

    where = f"WHERE {' AND '.join(conditions)}"
    cursor = await db.execute(
        f"""
        SELECT id, address, program, buyer_name, closing_date,
               compliance_1st_attempt, compliance_2nd_attempt,
               latitude, longitude, finding, detection_label, detection_score,
               streetview_available, satellite_path
        FROM properties
        {where}
        """,
        params,
    )
    rows = [dict(row) for row in await cursor.fetchall()]
    prioritized = apply_priority_scores(rows)
    prioritized = filter_by_contact(prioritized, contact)
    clusters = haversine_clusters(prioritized, radius_miles=radius_miles, min_points=min_points)
    return {"count": len(clusters), "clusters": clusters}


@router.get("/priority-queue")
async def get_priority_queue(
    filter: str = Query("all"),
    program: str = Query(None),
    detection: str = None,
    search: str = Query(None),
    sort: str = Query("priority"),
    order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Return properties sorted by composite compliance priority.
    """
    conditions = []
    params = []

    if filter == "unreviewed":
        conditions.append("(finding = '' OR finding IS NULL)")
    elif filter == "inconclusive":
        conditions.append("finding = 'inconclusive'")
    elif filter == "resolved":
        conditions.append(f"finding IN ({resolved_values_sql()})")
    elif filter == "reviewed":
        conditions.append("(finding != '' AND finding IS NOT NULL)")

    if program:
        conditions.append("program = ?")
        params.append(program)

    if detection:
        conditions.append("detection_label = ?")
        params.append(detection)

    if search:
        conditions.append("(address LIKE ? OR parcel_id LIKE ? OR buyer_name LIKE ? OR organization LIKE ? OR email LIKE ?)")
        params.extend([f"%{search}%"] * 5)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor = await db.execute(
        f"""
        SELECT p.*, COALESCE(
            (SELECT COUNT(*) FROM communications c WHERE c.property_id = p.id), 0
        ) AS communication_count
        FROM properties p
        {where}
        """,
        params,
    )
    rows = [dict(row) for row in await cursor.fetchall()]
    prioritized = apply_priority_scores(rows)
    sort_key = sort.lower()
    descending = order.lower() != "asc"
    if sort_key == "address":
        prioritized.sort(key=lambda row: row.get("address", "").lower(), reverse=descending)
    elif sort_key == "created_at":
        prioritized.sort(key=lambda row: row.get("created_at", ""), reverse=descending)
    elif sort_key == "detection_score":
        prioritized.sort(key=lambda row: float(row.get("detection_score") or 0.0), reverse=descending)
    else:
        prioritized.sort(
            key=lambda row: (
                float(row.get("priority_score", 0.0)),
                float(row.get("detection_score") or 0.0),
                row.get("address", ""),
            ),
            reverse=True,
        )

    total = len(prioritized)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "properties": prioritized[offset:offset + limit],
    }


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
        INSERT INTO properties (
            address, address_key, parcel_id, buyer_name, program, closing_date, commitment,
            email, organization, purchase_type, compliance_1st_attempt, compliance_2nd_attempt,
            streetview_historical_path, streetview_historical_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        prop.address,
        build_address_key(prop.address),
        prop.parcel_id,
        prop.buyer_name,
        prop.program,
        prop.closing_date,
        prop.commitment,
        prop.email,
        prop.organization,
        prop.purchase_type,
        prop.compliance_1st_attempt,
        prop.compliance_2nd_attempt,
        prop.streetview_historical_path,
        prop.streetview_historical_date,
    ])
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

    if "address" in update_data:
        fields.append("address_key = ?")
        values.append(build_address_key(update_data["address"]))

    if "finding" in update_data:
        fields.append("reviewed_at = ?")
        values.append(datetime.now().isoformat() if update_data["finding"] else None)

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
        """, [req.finding, now if req.finding else None, now, pid])
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

    total_rows = len(properties) + len(errors)

    # Insert batch record
    await db.execute(
        "INSERT INTO import_batches (id, filename, row_count) VALUES (?, ?, ?)",
        [batch_id, filename, total_rows],
    )

    inserted = 0
    updated = 0
    for prop in properties:
        try:
            existing = await find_existing_property(db, prop)
            if existing:
                await merge_import_property(db, existing["id"], prop, batch_id)
                updated += 1
            else:
                await db.execute("""
                    INSERT INTO properties (
                        address, address_key, parcel_id, buyer_name, program, closing_date, commitment,
                        email, organization, purchase_type, compliance_1st_attempt, compliance_2nd_attempt,
                        streetview_historical_path, streetview_historical_date, import_batch
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    prop.address,
                    build_address_key(prop.address),
                    prop.parcel_id,
                    prop.buyer_name,
                    prop.program,
                    prop.closing_date,
                    prop.commitment,
                    prop.email,
                    prop.organization,
                    prop.purchase_type,
                    prop.compliance_1st_attempt,
                    prop.compliance_2nd_attempt,
                    prop.streetview_historical_path,
                    prop.streetview_historical_date,
                    batch_id,
                ])
                inserted += 1
        except Exception as e:
            errors.append(f"Insert error for {prop.address}: {str(e)}")

    await db.commit()

    return ImportResult(
        batch_id=batch_id,
        total_rows=total_rows,
        imported=inserted + updated,
        inserted=inserted,
        updated=updated,
        skipped=len(errors),
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

    resolved_values = resolved_values_sql()
    cursor = await db.execute(f"SELECT COUNT(*) as n FROM properties WHERE finding IN ({resolved_values})")
    resolved = (await cursor.fetchone())["n"]

    cursor = await db.execute("SELECT COUNT(*) as n FROM properties WHERE finding = 'inconclusive'")
    needs_inspection = (await cursor.fetchone())["n"]

    cursor = await db.execute("""
        SELECT COUNT(*) as n FROM properties
        WHERE finding = 'inconclusive' OR detection_label IN ('likely_vacant', 'likely_demolished')
    """)
    inspection_candidates = (await cursor.fetchone())["n"]

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

    cursor = await db.execute("""
        SELECT detection_label, COUNT(*) as n FROM properties
        WHERE (finding = '' OR finding IS NULL)
          AND detection_label != '' AND detection_label IS NOT NULL
        GROUP BY detection_label
    """)
    unreviewed_by_detection = {
        row["detection_label"]: row["n"] for row in await cursor.fetchall()
    }

    return StatsResponse(
        total=total,
        unreviewed=total - reviewed,
        reviewed=reviewed,
        resolved=resolved,
        needs_inspection=needs_inspection,
        inspection_candidates=inspection_candidates,
        geocoded=geocoded,
        imagery_fetched=imagery_fetched,
        detection_ran=detection_ran,
        by_finding=by_finding,
        by_program=by_program,
        by_detection=by_detection,
        unreviewed_by_detection=unreviewed_by_detection,
        percent_reviewed=round(reviewed / total * 100, 1) if total > 0 else 0,
    )


# --- Export ---

@router.get("/export/csv")
async def export_csv(
    finding: str = Query(None),
    detection: str = Query(None),
    program: str = Query(None),
    contact: str = Query("all"),
    search: str = Query(None),
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
    if program:
        conditions.append("program = ?")
        params.append(program)
    if contact == "contacted":
        conditions.append("(COALESCE(compliance_1st_attempt, '') != '' OR COALESCE(compliance_2nd_attempt, '') != '')")
    elif contact == "no_contact":
        conditions.append("(COALESCE(compliance_1st_attempt, '') = '' AND COALESCE(compliance_2nd_attempt, '') = '')")
    if search:
        conditions.append("(address LIKE ? OR parcel_id LIKE ? OR buyer_name LIKE ? OR organization LIKE ? OR email LIKE ?)")
        params.extend([f"%{search}%"] * 5)

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


@router.get("/export/resolved")
async def export_resolved(db: aiosqlite.Connection = Depends(get_db)):
    """Export properties resolved through desk research."""
    resolved_values = resolved_values_sql()
    cursor = await db.execute(
        f"SELECT * FROM properties WHERE finding IN ({resolved_values}) ORDER BY address"
    )
    rows = await cursor.fetchall()
    csv_text = export_properties_csv([dict(r) for r in rows])
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=resolved-properties-{datetime.now().strftime('%Y%m%d')}.csv"},
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
