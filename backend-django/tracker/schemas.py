"""
Pydantic schemas for the Django Ninja API layer.

Carried over from the FastAPI backend with additions for new fields
(compliance_status, tax_status, outreach tracking, portal/regrid).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from ninja import Schema
from pydantic import Field


# --- Enums (plain string sets, not Python Enum, for Ninja compatibility) ---

FINDING_VALUES = {
    "visibly_renovated", "occupied_maintained", "partial_progress",
    "appears_vacant", "structure_gone", "inconclusive",
}

RESOLVED_FINDINGS = {
    "visibly_renovated", "occupied_maintained", "partial_progress",
    "appears_vacant", "structure_gone",
}

DETECTION_LABELS = {
    "likely_occupied", "likely_vacant", "likely_demolished",
    "no_streetview", "unprocessed",
}

COMPLIANCE_STATUSES = {
    "compliant", "in_progress", "needs_outreach", "non_compliant", "unknown",
}

TAX_STATUSES = {
    "current", "delinquent", "payment_plan", "unknown",
}


# --- Property Schemas ---

class PropertyCreate(Schema):
    address: str
    parcel_id: str = ""
    buyer_name: str = ""
    program: str = ""
    closing_date: str = ""
    commitment: str = ""
    email: str = ""
    organization: str = ""
    purchase_type: str = ""
    compliance_1st_attempt: str = ""
    compliance_2nd_attempt: str = ""
    streetview_historical_path: str = ""
    streetview_historical_date: str = ""


class PropertyUpdate(Schema):
    finding: Optional[str] = None
    notes: Optional[str] = None
    address: Optional[str] = None
    parcel_id: Optional[str] = None
    buyer_name: Optional[str] = None
    program: Optional[str] = None
    closing_date: Optional[str] = None
    commitment: Optional[str] = None
    email: Optional[str] = None
    organization: Optional[str] = None
    purchase_type: Optional[str] = None
    compliance_1st_attempt: Optional[str] = None
    compliance_2nd_attempt: Optional[str] = None
    streetview_historical_path: Optional[str] = None
    streetview_historical_date: Optional[str] = None
    # New fields
    compliance_status: Optional[str] = None
    tax_status: Optional[str] = None
    last_tax_payment: Optional[date] = None
    tax_amount_owed: Optional[Decimal] = None
    homeowner_exemption: Optional[bool] = None
    outreach_attempts: Optional[int] = None
    last_outreach_date: Optional[date] = None
    last_outreach_method: Optional[str] = None
    regrid_condition: Optional[str] = None
    portal_survey_date: Optional[date] = None


class PropertyResponse(Schema):
    id: int
    address: str
    parcel_id: str
    buyer_name: str
    program: str
    closing_date: str
    commitment: str
    email: str = ""
    organization: str = ""
    purchase_type: str = ""
    compliance_1st_attempt: str = ""
    compliance_2nd_attempt: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    formatted_address: str = ""
    geocoded_at: Optional[datetime] = None
    streetview_path: str = ""
    streetview_date: str = ""
    streetview_available: bool = False
    streetview_historical_path: str = ""
    streetview_historical_date: str = ""
    satellite_path: str = ""
    imagery_fetched_at: Optional[datetime] = None
    detection_score: Optional[float] = None
    detection_label: str = ""
    detection_details: dict = Field(default_factory=dict)
    detection_ran_at: Optional[datetime] = None
    finding: str = ""
    notes: str = ""
    reviewed_at: Optional[datetime] = None
    reviewed_by: str = "staff"
    # New fields
    compliance_status: str = "unknown"
    tax_status: str = "unknown"
    last_tax_payment: Optional[date] = None
    tax_amount_owed: Optional[Decimal] = None
    homeowner_exemption: bool = False
    outreach_attempts: int = 0
    last_outreach_date: Optional[date] = None
    last_outreach_method: str = ""
    regrid_condition: str = ""
    portal_survey_date: Optional[date] = None
    # Tracking
    import_batch: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    communication_count: int = 0
    manual_compliance_outcome: str = "pending"
    photo_summary: dict = Field(default_factory=dict)
    primary_before_photo: Optional[dict] = None
    primary_after_photo: Optional[dict] = None

    class Config:
        from_attributes = True


class PropertyPhotoResponse(Schema):
    id: int
    property_id: int
    side: str
    image_url: str
    original_filename: str = ""
    caption: str = ""
    source: str = "manual_upload"
    is_primary: bool = False
    photo_date: Optional[date] = None
    photo_latitude: Optional[float] = None
    photo_longitude: Optional[float] = None
    distance_from_property_meters: Optional[float] = None
    proximity_status: str = "unlocated"
    metadata: dict = Field(default_factory=dict)
    uploaded_at: Optional[datetime] = None


# --- Stats ---

class StatsResponse(Schema):
    total: int = 0
    unreviewed: int = 0
    reviewed: int = 0
    resolved: int = 0
    needs_inspection: int = 0
    inspection_candidates: int = 0
    geocoded: int = 0
    imagery_fetched: int = 0
    detection_ran: int = 0
    by_finding: dict = Field(default_factory=dict)
    by_program: dict = Field(default_factory=dict)
    by_detection: dict = Field(default_factory=dict)
    unreviewed_by_detection: dict = Field(default_factory=dict)
    # New
    by_compliance_status: dict = Field(default_factory=dict)
    percent_reviewed: float = 0.0
    compliant_reviewed: int = 0
    non_compliant_reviewed: int = 0
    in_progress_reviewed: int = 0
    compliant_percent_reviewed: float = 0.0
    photo_ready: int = 0
    uploaded_before_count: int = 0
    uploaded_after_count: int = 0


# --- Import ---

class ImportResult(Schema):
    batch_id: str
    total_rows: int
    imported: int
    inserted: int = 0
    updated: int = 0
    skipped: int
    errors: list[str] = Field(default_factory=list)


# --- Batch Update ---

class BatchUpdateRequest(Schema):
    property_ids: list[int]
    finding: str
    notes: str = ""


# --- Communication Schemas ---

class CommunicationCreate(Schema):
    property_id: int
    method: str
    direction: str = "outbound"
    date_sent: Optional[date] = None
    subject: str = ""
    body: str = ""


class CommunicationUpdate(Schema):
    response_received: Optional[bool] = None
    response_date: Optional[date] = None
    response_notes: Optional[str] = None


class CommunicationResponse(Schema):
    id: int
    property_id: int
    method: str
    direction: str
    date_sent: Optional[date] = None
    subject: str
    body: str
    response_received: bool
    response_date: Optional[date] = None
    response_notes: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
