from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

from app.models.database import get_db
from app.models.communication import (
    CommunicationCreate, CommunicationUpdate, CommunicationResponse,
)

router = APIRouter(prefix="/api/communications", tags=["communications"])


@router.get("/{property_id}", response_model=list[CommunicationResponse])
async def list_communications(property_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """List all communications for a property."""
    cursor = await db.execute(
        "SELECT * FROM communications WHERE property_id = ? ORDER BY created_at DESC",
        [property_id],
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.post("/", response_model=CommunicationResponse)
async def create_communication(comm: CommunicationCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Log a communication attempt."""
    cursor = await db.execute("""
        INSERT INTO communications (property_id, method, direction, date_sent, subject, body)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [comm.property_id, comm.method, comm.direction,
          comm.date_sent or datetime.now().isoformat(), comm.subject, comm.body])
    await db.commit()

    cursor = await db.execute("SELECT * FROM communications WHERE id = ?", [cursor.lastrowid])
    row = await cursor.fetchone()
    return dict(row)


@router.patch("/{comm_id}", response_model=CommunicationResponse)
async def update_communication(
    comm_id: int,
    updates: CommunicationUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update a communication (e.g., mark response received)."""
    fields = []
    values = []
    update_data = updates.model_dump(exclude_none=True)

    for field, value in update_data.items():
        fields.append(f"{field} = ?")
        values.append(value)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(comm_id)
    await db.execute(f"UPDATE communications SET {', '.join(fields)} WHERE id = ?", values)
    await db.commit()

    cursor = await db.execute("SELECT * FROM communications WHERE id = ?", [comm_id])
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Communication not found")
    return dict(row)


@router.get("/stats/overview")
async def communication_stats(db: aiosqlite.Connection = Depends(get_db)):
    """Get communication statistics across all properties."""
    cursor = await db.execute("""
        SELECT
            method,
            COUNT(*) as total_sent,
            SUM(CASE WHEN response_received = 1 THEN 1 ELSE 0 END) as responses
        FROM communications
        GROUP BY method
    """)
    rows = await cursor.fetchall()

    return {
        "by_method": [
            {
                "method": row["method"],
                "total_sent": row["total_sent"],
                "responses": row["responses"],
                "response_rate": round(row["responses"] / row["total_sent"] * 100, 1) if row["total_sent"] > 0 else 0,
            }
            for row in rows
        ]
    }
