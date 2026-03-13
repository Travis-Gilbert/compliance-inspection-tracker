from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class FindingType(str, Enum):
    VISIBLY_RENOVATED = "visibly_renovated"
    OCCUPIED_MAINTAINED = "occupied_maintained"
    PARTIAL_PROGRESS = "partial_progress"
    APPEARS_VACANT = "appears_vacant"
    STRUCTURE_GONE = "structure_gone"
    INCONCLUSIVE = "inconclusive"


class DetectionLabel(str, Enum):
    LIKELY_OCCUPIED = "likely_occupied"
    LIKELY_VACANT = "likely_vacant"
    LIKELY_DEMOLISHED = "likely_demolished"
    NO_STREETVIEW = "no_streetview"
    UNPROCESSED = "unprocessed"


class Program(str, Enum):
    FEATURED_HOMES = "Featured Homes"
    READY_FOR_REHAB = "Ready for Rehab"
    VIP_SPOTLIGHT = "VIP Spotlight"
    DEMOLITION = "Demolition"
    UNKNOWN = ""


RESOLVED_FINDINGS = {
    FindingType.VISIBLY_RENOVATED,
    FindingType.OCCUPIED_MAINTAINED,
    FindingType.PARTIAL_PROGRESS,
    FindingType.APPEARS_VACANT,
    FindingType.STRUCTURE_GONE,
}


class PropertyCreate(BaseModel):
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


class PropertyUpdate(BaseModel):
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


class PropertyResponse(BaseModel):
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
    geocoded_at: Optional[str] = None
    streetview_path: str = ""
    streetview_date: str = ""
    streetview_available: bool = False
    streetview_historical_path: str = ""
    streetview_historical_date: str = ""
    satellite_path: str = ""
    imagery_fetched_at: Optional[str] = None
    detection_score: Optional[float] = None
    detection_label: str = ""
    detection_details: str = ""
    detection_ran_at: Optional[str] = None
    finding: str = ""
    notes: str = ""
    reviewed_at: Optional[str] = None
    import_batch: str = ""
    created_at: str = ""
    updated_at: str = ""
    communication_count: int = 0

    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    total: int = 0
    unreviewed: int = 0
    reviewed: int = 0
    resolved: int = 0
    needs_inspection: int = 0
    geocoded: int = 0
    imagery_fetched: int = 0
    detection_ran: int = 0
    by_finding: dict = Field(default_factory=dict)
    by_program: dict = Field(default_factory=dict)
    by_detection: dict = Field(default_factory=dict)
    percent_reviewed: float = 0.0


class ImportResult(BaseModel):
    batch_id: str
    total_rows: int
    imported: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
