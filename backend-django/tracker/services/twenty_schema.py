from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx
from django.conf import settings


TWENTY_CLOUD_BASE_URL = "https://api.twenty.com"


class TwentySchemaError(RuntimeError):
    pass


@dataclass(frozen=True)
class SelectOptionSpec:
    value: str
    label: str
    color: str
    position: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "color": self.color,
            "position": self.position,
        }


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    type: str
    icon: str
    nullable: bool = False
    default_value: Any = None
    unique: bool = False
    options: tuple[SelectOptionSpec, ...] = ()
    settings: dict[str, Any] | None = None

    def as_payload(self, object_metadata_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "objectMetadataId": object_metadata_id,
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "icon": self.icon,
            "isNullable": self.nullable,
            "isUnique": self.unique,
            "isUIEditable": True,
            "isUIReadOnly": False,
        }
        if self.default_value is not None:
            payload["defaultValue"] = self.default_value
        if self.options:
            payload["options"] = [option.as_payload() for option in self.options]
        if self.settings is not None:
            payload["settings"] = self.settings
        return payload


@dataclass(frozen=True)
class ObjectSpec:
    name_singular: str
    name_plural: str
    label_singular: str
    label_plural: str
    description: str
    icon: str
    color: str
    nav_position: int
    fields: tuple[FieldSpec, ...]
    kanban_field: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "nameSingular": self.name_singular,
            "namePlural": self.name_plural,
            "labelSingular": self.label_singular,
            "labelPlural": self.label_plural,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "isLabelSyncedWithName": False,
        }


@dataclass(frozen=True)
class SavedViewSpec:
    name: str
    object_name: str
    icon: str
    position: float
    visible_fields: tuple[str, ...] = ()
    hide_unrequested_fields: bool = False
    filters: tuple[dict[str, Any], ...] = ()
    sort_field: str | None = None
    sort_direction: str = "ASC"


@dataclass
class TwentyBootstrapResult:
    objects_created: int = 0
    objects_existing: int = 0
    objects_updated: int = 0
    fields_created: int = 0
    fields_existing: int = 0
    fields_updated: int = 0
    views_created: int = 0
    views_existing: int = 0
    navigation_created: int = 0
    navigation_existing: int = 0
    navigation_hidden: int = 0
    roles_created: int = 0
    roles_existing: int = 0
    actions: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.actions.append(message)


def _select(*items: tuple[str, str, str]) -> tuple[SelectOptionSpec, ...]:
    return tuple(
        SelectOptionSpec(value=value, label=label, color=color, position=index)
        for index, (value, label, color) in enumerate(items)
    )


GCLBA_OBJECTS: tuple[ObjectSpec, ...] = (
    ObjectSpec(
        name_singular="gclbaProperty",
        name_plural="gclbaProperties",
        label_singular="GCLBA Property",
        label_plural="GCLBA Properties",
        description="Django/PostGIS property mirror for GCLBA CRM workflows.",
        icon="IconHomeSearch",
        color="blue",
        nav_position=0,
        kanban_field="complianceStatus",
        fields=(
            FieldSpec("djangoPropertyId", "Django property ID", "NUMBER", "IconDatabase", unique=True),
            FieldSpec("parcelId", "Parcel ID", "TEXT", "IconMapPin"),
            FieldSpec("tenantId", "Tenant ID", "TEXT", "IconBuildingCommunity", default_value="'gclba'"),
            FieldSpec("propertyAddress", "Address", "TEXT", "IconMap2", nullable=True),
            FieldSpec("buyerName", "Buyer", "TEXT", "IconUser", nullable=True),
            FieldSpec("contactEmail", "Contact email", "TEXT", "IconMail", nullable=True),
            FieldSpec("contactPhone", "Contact phone", "TEXT", "IconPhone", nullable=True),
            FieldSpec("organization", "Organization", "TEXT", "IconBuilding", nullable=True),
            FieldSpec("program", "Program", "TEXT", "IconBriefcase", nullable=True),
            FieldSpec("saleDate", "Date of sale", "DATE", "IconCalendarDollar", nullable=True),
            FieldSpec("purchaseType", "Purchase type", "TEXT", "IconContract", nullable=True),
            FieldSpec("commitment", "Commitment", "TEXT", "IconClipboardText", nullable=True),
            FieldSpec(
                "complianceStatus",
                "Compliance",
                "SELECT",
                "IconShieldCheck",
                default_value="'UNKNOWN'",
                options=_select(
                    ("COMPLIANT", "Compliant", "blue"),
                    ("NEEDS_REVIEW", "Needs review", "yellow"),
                    ("NON_COMPLIANT", "Non-compliant", "red"),
                    ("UNKNOWN", "Unknown", "gray"),
                ),
            ),
            FieldSpec(
                "taxStatus",
                "Tax",
                "SELECT",
                "IconReceiptTax",
                default_value="'UNKNOWN'",
                options=_select(
                    ("CURRENT", "Current", "blue"),
                    ("DELINQUENT", "Delinquent", "red"),
                    ("PAYMENT_PLAN", "Payment plan", "yellow"),
                    ("UNKNOWN", "Unknown", "gray"),
                ),
            ),
            FieldSpec("taxAmountOwed", "Tax amount owed", "NUMBER", "IconReceiptTax", nullable=True),
            FieldSpec("lastTaxPayment", "Last tax payment", "DATE", "IconCalendarCheck", nullable=True),
            FieldSpec("homeownerExemption", "Homeowner exemption", "BOOLEAN", "IconHomeCheck", default_value=False),
            FieldSpec("assessedValue", "Assessed value", "NUMBER", "IconHomeDollar", nullable=True),
            FieldSpec("taxableValue", "Taxable value", "NUMBER", "IconCashBanknote", nullable=True),
            FieldSpec("ownerOfRecord", "Owner of record", "TEXT", "IconUserSearch", nullable=True),
            FieldSpec("propertyClass", "Property class", "TEXT", "IconCategory", nullable=True),
            FieldSpec("landUse", "Land use", "TEXT", "IconMapPins", nullable=True),
            FieldSpec("forfeitureStatus", "Forfeiture status", "TEXT", "IconAlertCircle", nullable=True),
            FieldSpec("forfeitureStatusYear", "Forfeiture year", "TEXT", "IconCalendarStats", nullable=True),
            FieldSpec("finding", "Finding", "TEXT", "IconClipboardCheck", nullable=True),
            FieldSpec("detectionLabel", "Detection label", "TEXT", "IconRadar", nullable=True),
            FieldSpec("regridCondition", "Portal condition", "TEXT", "IconHomeStats", nullable=True),
            FieldSpec("portalSurveyDate", "Portal survey date", "DATE", "IconCalendarSearch", nullable=True),
            FieldSpec("lastOutreachDate", "Last outreach date", "DATE", "IconCalendarShare", nullable=True),
            FieldSpec("lastOutreachMethod", "Last outreach method", "TEXT", "IconSend", nullable=True),
            FieldSpec("outreachAttempts", "Outreach attempts", "NUMBER", "IconRepeat", default_value=0),
            FieldSpec("latitude", "Latitude", "NUMBER", "IconLocation", nullable=True),
            FieldSpec("longitude", "Longitude", "NUMBER", "IconLocation", nullable=True),
            FieldSpec("reviewedAt", "Reviewed at", "DATE_TIME", "IconCalendarCheck", nullable=True),
            FieldSpec("reviewNotes", "Review notes", "TEXT", "IconNotes", nullable=True),
            FieldSpec("crmUrl", "Map dossier URL", "TEXT", "IconExternalLink", nullable=True),
        ),
    ),
    ObjectSpec(
        name_singular="gclbaOutreach",
        name_plural="gclbaOutreachRecords",
        label_singular="GCLBA Outreach",
        label_plural="GCLBA Outreach",
        description="Outreach and communication mirror from Django workflow events.",
        icon="IconMessages",
        color="blue",
        nav_position=1,
        kanban_field="status",
        fields=(
            FieldSpec("djangoPropertyId", "Django property ID", "NUMBER", "IconDatabase"),
            FieldSpec("parcelId", "Parcel ID", "TEXT", "IconMapPin"),
            FieldSpec(
                "action",
                "Action",
                "SELECT",
                "IconListCheck",
                default_value="'MANUAL_REVIEW'",
                options=_select(
                    ("ATTEMPT_1", "First attempt", "blue"),
                    ("ATTEMPT_2", "Second attempt", "yellow"),
                    ("WARNING", "Warning", "red"),
                    ("DEFAULT_NOTICE", "Default notice", "red"),
                    ("TAX_VERIFICATION", "Tax verification", "orange"),
                    ("MISSING_EMAIL", "Missing email", "orange"),
                    ("NEEDS_INSPECTION", "Needs inspection", "purple"),
                    ("MANUAL_REVIEW", "Manual review", "gray"),
                ),
            ),
            FieldSpec(
                "method",
                "Method",
                "SELECT",
                "IconSend",
                default_value="'EMAIL'",
                options=_select(
                    ("EMAIL", "Email", "blue"),
                    ("PHONE", "Phone", "blue"),
                    ("MAIL", "Mail", "orange"),
                    ("SITE_VISIT", "Site visit", "purple"),
                    ("TEXT", "Text", "gray"),
                ),
            ),
            FieldSpec(
                "status",
                "Status",
                "SELECT",
                "IconProgress",
                default_value="'LOGGED'",
                options=_select(
                    ("LOGGED", "Logged", "gray"),
                    ("DRAFT", "Draft", "yellow"),
                    ("SENT", "Sent", "blue"),
                    ("DELIVERED", "Delivered", "blue"),
                    ("BOUNCED", "Bounced", "red"),
                    ("FAILED", "Failed", "red"),
                ),
            ),
            FieldSpec("dueDate", "Due date", "DATE", "IconCalendarDue", nullable=True),
        ),
    ),
    ObjectSpec(
        name_singular="gclbaComplianceCase",
        name_plural="gclbaComplianceCases",
        label_singular="GCLBA Compliance Case",
        label_plural="GCLBA Compliance Cases",
        description="Case mirror for compliance review and enforcement tracking.",
        icon="IconShieldExclamation",
        color="red",
        nav_position=2,
        kanban_field="caseStatus",
        fields=(
            FieldSpec("djangoPropertyId", "Django property ID", "NUMBER", "IconDatabase"),
            FieldSpec("parcelId", "Parcel ID", "TEXT", "IconMapPin"),
            FieldSpec(
                "caseStatus",
                "Case status",
                "SELECT",
                "IconProgressCheck",
                default_value="'OPEN'",
                options=_select(
                    ("OPEN", "Open", "blue"),
                    ("INSPECTION", "Inspection", "purple"),
                    ("WARNING", "Warning", "orange"),
                    ("ENFORCEMENT", "Enforcement", "red"),
                    ("RESOLVED", "Resolved", "blue"),
                ),
            ),
            FieldSpec("enforcementLevel", "Enforcement level", "NUMBER", "IconAlertTriangle", default_value=0),
            FieldSpec("nextReviewAt", "Next review", "DATE_TIME", "IconCalendarClock", nullable=True),
        ),
    ),
    ObjectSpec(
        name_singular="gclbaSourceConflict",
        name_plural="gclbaSourceConflicts",
        label_singular="GCLBA Source Conflict",
        label_plural="GCLBA Source Conflicts",
        description="Cross-source disagreement rows from the property-intelligence index.",
        icon="IconAlertTriangle",
        color="orange",
        nav_position=3,
        kanban_field="kind",
        fields=(
            FieldSpec("djangoConflictId", "Django conflict ID", "NUMBER", "IconDatabase", unique=True),
            FieldSpec("djangoPropertyId", "Django property ID", "NUMBER", "IconHomeSearch", nullable=True),
            FieldSpec("parcelId", "Parcel ID", "TEXT", "IconMapPin"),
            FieldSpec(
                "kind",
                "Conflict kind",
                "SELECT",
                "IconArrowsShuffle",
                default_value="'OWNER_MISMATCH'",
                options=_select(
                    ("OWNER_MISMATCH", "Owner mismatch", "red"),
                    ("REVERSE_MISMATCH", "Reverse mismatch", "blue"),
                    ("PID_ORPHAN", "Parcel orphan", "purple"),
                    ("CONDITION_REGRESSION", "Condition regression", "orange"),
                    ("VALUE_DISAGREEMENT", "Value disagreement", "yellow"),
                ),
            ),
            FieldSpec(
                "severity",
                "Severity",
                "SELECT",
                "IconAlertCircle",
                default_value="'REVIEW'",
                options=_select(
                    ("WATCH", "Watch", "yellow"),
                    ("REVIEW", "Review", "orange"),
                    ("HIGH", "High", "red"),
                ),
            ),
            FieldSpec("title", "Title", "TEXT", "IconTextCaption"),
            FieldSpec("plainLanguage", "Plain language", "TEXT", "IconMessage", nullable=True),
            FieldSpec("observedAt", "Observed at", "DATE", "IconCalendar"),
            FieldSpec(
                "status",
                "Status",
                "SELECT",
                "IconProgressCheck",
                default_value="'OPEN'",
                options=_select(
                    ("OPEN", "Open", "red"),
                    ("RESOLVED", "Resolved", "blue"),
                    ("DISMISSED", "Dismissed", "gray"),
                ),
            ),
            FieldSpec("crmUrl", "Map dossier URL", "TEXT", "IconExternalLink", nullable=True),
        ),
    ),
    ObjectSpec(
        name_singular="gclbaValuationSnapshot",
        name_plural="gclbaValuationSnapshots",
        label_singular="GCLBA Valuation Snapshot",
        label_plural="GCLBA Valuation Snapshots",
        description="Assessed, taxable, and price observations for GCLBA parcels.",
        icon="IconCashBanknote",
        color="green",
        nav_position=4,
        fields=(
            FieldSpec("djangoPropertyId", "Django property ID", "NUMBER", "IconDatabase"),
            FieldSpec("parcelId", "Parcel ID", "TEXT", "IconMapPin"),
            FieldSpec("assessedValue", "Assessed value", "NUMBER", "IconHomeDollar", nullable=True),
            FieldSpec("taxableValue", "Taxable value", "NUMBER", "IconReceiptTax", nullable=True),
            FieldSpec("askingPrice", "Asking price", "NUMBER", "IconTag", nullable=True),
            FieldSpec("observedAt", "Observed at", "DATE_TIME", "IconCalendar"),
        ),
    ),
    ObjectSpec(
        name_singular="gclbaHomeQualityObservation",
        name_plural="gclbaHomeQualityObservations",
        label_singular="GCLBA Home Quality Observation",
        label_plural="GCLBA Home Quality Observations",
        description="Inspection and photo-derived home quality observations.",
        icon="IconHomeCheck",
        color="purple",
        nav_position=5,
        kanban_field="qualityBand",
        fields=(
            FieldSpec("djangoPropertyId", "Django property ID", "NUMBER", "IconDatabase"),
            FieldSpec("parcelId", "Parcel ID", "TEXT", "IconMapPin"),
            FieldSpec("propertyAddress", "Address", "TEXT", "IconMap2", nullable=True),
            FieldSpec(
                "qualityBand",
                "Quality band",
                "SELECT",
                "IconStars",
                default_value="'UNKNOWN'",
                options=_select(
                    ("GOOD", "Good", "blue"),
                    ("FAIR", "Fair", "yellow"),
                    ("POOR", "Poor", "red"),
                    ("UNKNOWN", "Unknown", "gray"),
                ),
            ),
            FieldSpec("photoSummary", "Photo summary", "TEXT", "IconPhoto", nullable=True),
            FieldSpec("streetviewAvailable", "Street View available", "BOOLEAN", "IconStreetView", default_value=False),
            FieldSpec("streetviewDate", "Street View date", "TEXT", "IconCalendar", nullable=True),
            FieldSpec("historicalStreetviewDate", "Historical Street View date", "TEXT", "IconHistory", nullable=True),
            FieldSpec("satelliteAvailable", "Satellite image available", "BOOLEAN", "IconSatellite", default_value=False),
            FieldSpec("imageryFetchedAt", "Imagery fetched at", "DATE_TIME", "IconCloudDownload", nullable=True),
            FieldSpec("detectionLabel", "Detection label", "TEXT", "IconRadar", nullable=True),
            FieldSpec("detectionScore", "Detection score", "NUMBER", "IconGauge", nullable=True),
            FieldSpec("detectionDetails", "Detection details", "TEXT", "IconListDetails", nullable=True),
            FieldSpec("reviewFinding", "Review finding", "TEXT", "IconClipboardCheck", nullable=True),
            FieldSpec("manualComplianceOutcome", "Manual outcome", "TEXT", "IconUserCheck", nullable=True),
            FieldSpec("reviewedAt", "Reviewed at", "DATE_TIME", "IconCalendarCheck", nullable=True),
            FieldSpec("regridCondition", "Portal condition", "TEXT", "IconHomeStats", nullable=True),
            FieldSpec("portalSurveyDate", "Portal survey date", "DATE", "IconCalendarSearch", nullable=True),
            FieldSpec("mapDossierUrl", "Map dossier URL", "TEXT", "IconExternalLink", nullable=True),
            FieldSpec("observedAt", "Observed at", "DATE_TIME", "IconCalendar"),
        ),
    ),
    ObjectSpec(
        name_singular="gclbaImageEvidence",
        name_plural="gclbaImageEvidenceItems",
        label_singular="GCLBA Image",
        label_plural="GCLBA Images",
        description="Image rows linked back to Django property imagery.",
        icon="IconPhotoSearch",
        color="blue",
        nav_position=6,
        kanban_field="imageSource",
        fields=(
            FieldSpec("djangoPropertyId", "Django property ID", "NUMBER", "IconDatabase"),
            FieldSpec("djangoPhotoId", "Django photo ID", "NUMBER", "IconPhoto", nullable=True),
            FieldSpec("parcelId", "Parcel ID", "TEXT", "IconMapPin"),
            FieldSpec("propertyAddress", "Address", "TEXT", "IconMap2", nullable=True),
            FieldSpec(
                "imageSource",
                "Image source",
                "SELECT",
                "IconPhotoSearch",
                default_value="'STREET_VIEW'",
                options=_select(
                    ("STREET_VIEW", "Street View", "blue"),
                    ("HISTORICAL_STREET_VIEW", "Historical Street View", "purple"),
                    ("SATELLITE", "Satellite", "green"),
                    ("NAIP_AERIAL", "NAIP aerial", "teal"),
                    ("MAPILLARY", "Mapillary", "orange"),
                    ("SURVEY_ARCHIVE", "Survey archive", "gray"),
                    ("BUYER_SUBMITTED", "Buyer submitted", "red"),
                    ("STAFF_UPLOAD", "Staff upload", "yellow"),
                    ("OTHER", "Other", "gray"),
                ),
            ),
            FieldSpec(
                "imageKind",
                "Image kind",
                "SELECT",
                "IconTags",
                default_value="'EXTERIOR'",
                options=_select(
                    ("EXTERIOR", "Exterior", "blue"),
                    ("HISTORICAL_EXTERIOR", "Historical exterior", "purple"),
                    ("AERIAL", "Aerial", "green"),
                    ("BEFORE", "Before", "yellow"),
                    ("AFTER", "After", "blue"),
                    ("OTHER", "Other", "gray"),
                ),
            ),
            FieldSpec(
                "imageFile",
                "Image",
                "FILES",
                "IconPhoto",
                nullable=True,
                settings={"maxNumberOfValues": 1},
            ),
            FieldSpec("imageUrl", "Image URL", "TEXT", "IconExternalLink"),
            FieldSpec("thumbnailUrl", "Thumbnail URL", "TEXT", "IconPhoto", nullable=True),
            FieldSpec("captureDate", "Capture date", "TEXT", "IconCalendar", nullable=True),
            FieldSpec(
                "captureDatePrecision",
                "Capture date precision",
                "SELECT",
                "IconCalendar",
                nullable=True,
                options=_select(
                    ("DAY", "Day", "blue"),
                    ("MONTH", "Month", "purple"),
                    ("YEAR", "Year", "gray"),
                ),
            ),
            FieldSpec("storageKey", "Storage key", "TEXT", "IconDatabase", nullable=True),
            FieldSpec("sha256", "SHA-256", "TEXT", "IconKey", nullable=True),
            FieldSpec("panoId", "Pano ID", "TEXT", "IconMapPin", nullable=True),
            FieldSpec(
                "sourceLicense",
                "Source license",
                "SELECT",
                "IconLicense",
                nullable=True,
                options=_select(
                    ("PUBLIC_DOMAIN", "Public domain", "green"),
                    ("CC_BY_SA", "CC BY-SA", "blue"),
                    ("ORG_OWNED", "Organization owned", "purple"),
                    ("LICENSED_DISPLAY_ONLY", "Licensed display only", "orange"),
                ),
            ),
            FieldSpec("supersededBy", "Superseded by", "TEXT", "IconArrowRight", nullable=True),
            FieldSpec("footprintMeters", "Footprint meters", "NUMBER", "IconRulerMeasure", nullable=True),
            FieldSpec("headingDegrees", "Heading degrees", "NUMBER", "IconDirection", nullable=True),
            FieldSpec("djangoEvidenceId", "Django evidence ID", "NUMBER", "IconDatabase", nullable=True),
            FieldSpec("attribution", "Attribution", "TEXT", "IconLicense", nullable=True),
            FieldSpec("providerRecordId", "Provider record ID", "TEXT", "IconId", nullable=True),
            FieldSpec(
                "qualityBand",
                "Quality band",
                "SELECT",
                "IconStars",
                default_value="'UNKNOWN'",
                options=_select(
                    ("GOOD", "Good", "blue"),
                    ("FAIR", "Fair", "yellow"),
                    ("POOR", "Poor", "red"),
                    ("UNKNOWN", "Unknown", "gray"),
                ),
            ),
            FieldSpec("detectionLabel", "Detection label", "TEXT", "IconRadar", nullable=True),
            FieldSpec("detectionScore", "Detection score", "NUMBER", "IconGauge", nullable=True),
            FieldSpec(
                "proximityStatus",
                "Proximity",
                "SELECT",
                "IconMapPin",
                default_value="'NOT_APPLICABLE'",
                options=_select(
                    ("NOT_APPLICABLE", "Not applicable", "gray"),
                    ("UNLOCATED", "Unlocated", "gray"),
                    ("NEAR_PROPERTY", "Near property", "blue"),
                    ("NEARBY", "Nearby", "yellow"),
                    ("OUTSIDE_PROPERTY_AREA", "Outside property area", "red"),
                ),
            ),
            FieldSpec("matchDistanceMeters", "Match distance meters", "NUMBER", "IconRulerMeasure", nullable=True),
            FieldSpec("isPrimary", "Primary image", "BOOLEAN", "IconPhotoCheck", default_value=False),
            FieldSpec("mapDossierUrl", "Map dossier URL", "TEXT", "IconExternalLink", nullable=True),
            FieldSpec("observedAt", "Observed at", "DATE_TIME", "IconCalendar"),
        ),
    ),
    ObjectSpec(
        name_singular="gclbaOpportunityZone",
        name_plural="gclbaOpportunityZones",
        label_singular="GCLBA Opportunity Zone",
        label_plural="GCLBA Opportunity Zones",
        description="Opportunity zone membership and source metadata by parcel.",
        icon="IconMapSearch",
        color="green",
        nav_position=7,
        fields=(
            FieldSpec("djangoPropertyId", "Django property ID", "NUMBER", "IconDatabase"),
            FieldSpec("parcelId", "Parcel ID", "TEXT", "IconMapPin"),
            FieldSpec("isInOpportunityZone", "In opportunity zone", "BOOLEAN", "IconMapCheck", default_value=False),
            FieldSpec("zoneId", "Zone ID", "TEXT", "IconMapCog", nullable=True),
            FieldSpec("source", "Source", "TEXT", "IconSourceCode", nullable=True),
        ),
    ),
)


GCLBA_MAP_NAV_NAME = "GCLBA Map"
GCLBA_MAP_NAV_ICON = "IconMap2"
GCLBA_MAP_NAV_COLOR = "blue"
GCLBA_MAP_NAV_POSITION = -1.0


PROPERTY_CRM_VIEW_FIELDS: tuple[str, ...] = (
    "name",
    "buyerName",
    "propertyAddress",
    "saleDate",
    "contactEmail",
    "contactPhone",
    "organization",
    "program",
    "complianceStatus",
    "taxStatus",
    "taxAmountOwed",
    "ownerOfRecord",
    "assessedValue",
    "taxableValue",
    "parcelId",
    "purchaseType",
    "commitment",
    "lastTaxPayment",
    "homeownerExemption",
    "propertyClass",
    "landUse",
    "forfeitureStatus",
    "forfeitureStatusYear",
    "finding",
    "detectionLabel",
    "regridCondition",
    "portalSurveyDate",
    "lastOutreachDate",
    "lastOutreachMethod",
    "outreachAttempts",
    "latitude",
    "longitude",
    "reviewedAt",
    "reviewNotes",
    "crmUrl",
)


HOME_QUALITY_VIEW_FIELDS: tuple[str, ...] = (
    "name",
    "propertyAddress",
    "qualityBand",
    "detectionLabel",
    "detectionScore",
    "streetviewAvailable",
    "streetviewDate",
    "historicalStreetviewDate",
    "satelliteAvailable",
    "imageryFetchedAt",
    "photoSummary",
    "reviewFinding",
    "manualComplianceOutcome",
    "reviewedAt",
    "regridCondition",
    "portalSurveyDate",
    "parcelId",
    "detectionDetails",
    "mapDossierUrl",
    "observedAt",
)


IMAGE_EVIDENCE_VIEW_FIELDS: tuple[str, ...] = (
    "name",
    "imageFile",
    "propertyAddress",
    "imageSource",
    "imageKind",
    "thumbnailUrl",
    "imageUrl",
    "captureDate",
    "qualityBand",
    "detectionLabel",
    "detectionScore",
    "attribution",
    "proximityStatus",
    "matchDistanceMeters",
    "isPrimary",
    "parcelId",
    "mapDossierUrl",
    "observedAt",
)


SAVED_VIEWS: tuple[SavedViewSpec, ...] = (
    SavedViewSpec(
        name="All GCLBA Properties",
        object_name="gclbaProperty",
        icon="IconHomeSearch",
        position=19,
        visible_fields=PROPERTY_CRM_VIEW_FIELDS,
        hide_unrequested_fields=True,
        sort_field="parcelId",
    ),
    SavedViewSpec(
        name="All GCLBA Home Quality Observations",
        object_name="gclbaHomeQualityObservation",
        icon="IconHomeCheck",
        position=19.5,
        visible_fields=HOME_QUALITY_VIEW_FIELDS,
        hide_unrequested_fields=True,
        sort_field="parcelId",
    ),
    SavedViewSpec(
        name="All GCLBA Images",
        object_name="gclbaImageEvidence",
        icon="IconPhotoSearch",
        position=19.75,
        visible_fields=IMAGE_EVIDENCE_VIEW_FIELDS,
        hide_unrequested_fields=True,
        sort_field="parcelId",
    ),
    SavedViewSpec(
        name="Approaching deadline 90 days",
        object_name="gclbaComplianceCase",
        icon="IconCalendarClock",
        position=20,
        filters=(
            {
                "field": "nextReviewAt",
                "operand": "IS_BEFORE",
                "value": (dt.date.today() + dt.timedelta(days=90)).isoformat(),
            },
        ),
        sort_field="nextReviewAt",
    ),
    SavedViewSpec(
        name="Owner mismatch",
        object_name="gclbaSourceConflict",
        icon="IconAlertTriangle",
        position=21,
        filters=({"field": "kind", "operand": "IS", "value": "OWNER_MISMATCH"},),
        sort_field="observedAt",
        sort_direction="DESC",
    ),
    SavedViewSpec(
        name="Needs outreach",
        object_name="gclbaProperty",
        icon="IconMessages",
        position=22,
        filters=({"field": "complianceStatus", "operand": "IS", "value": "NEEDS_REVIEW"},),
        sort_field="parcelId",
    ),
)


NOISE_OBJECT_NAMES = {"company", "opportunity"}


class TwentyMetadataClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        client: httpx.Client | None = None,
    ):
        if not base_url:
            raise ValueError("TWENTY_BASE_URL is required")
        if not api_key:
            raise ValueError("TWENTY_API_KEY is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=30.0)

    @classmethod
    def from_settings(cls) -> "TwentyMetadataClient":
        return cls(
            base_url=settings.TWENTY_BASE_URL or TWENTY_CLOUD_BASE_URL,
            api_key=settings.TWENTY_API_KEY,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def rest_get(self, path: str) -> Any:
        response = self._client.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
        )
        return self._decode(response, f"GET {path}")

    def metadata_graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._client.post(
            f"{self.base_url}/metadata",
            headers=self._headers(),
            json={"query": query, "variables": variables or {}},
        )
        decoded = self._decode(response, "POST /metadata")
        if decoded.get("errors"):
            raise TwentySchemaError(f"Twenty metadata GraphQL error: {decoded['errors']}")
        data = decoded.get("data")
        if not isinstance(data, dict):
            raise TwentySchemaError("Twenty metadata GraphQL response did not include data")
        return data

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _decode(response: httpx.Response, label: str) -> Any:
        if response.status_code >= 400:
            raise TwentySchemaError(
                f"Twenty {label} failed with {response.status_code}: {response.text[:500]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise TwentySchemaError(f"Twenty {label} returned non-JSON") from exc


def bootstrap_twenty_schema(
    *,
    client: TwentyMetadataClient | None = None,
    dry_run: bool = False,
    include_workspace_polish: bool = True,
    hide_default_noise: bool = True,
) -> TwentyBootstrapResult:
    active_client = client or TwentyMetadataClient.from_settings()
    owns_client = client is None
    result = TwentyBootstrapResult()
    try:
        object_catalog = _objects_by_name(active_client)
        object_by_name: dict[str, dict[str, Any]] = {}
        fields_by_object: dict[str, dict[str, dict[str, Any]]] = {}

        for spec in GCLBA_OBJECTS:
            existing = object_catalog.get(spec.name_singular)
            if existing:
                result.objects_existing += 1
                result.add(f"exists object {spec.name_plural}")
                object_by_name[spec.name_singular] = existing
                if _needs_object_update(existing, spec):
                    result.objects_updated += 1
                    result.add(f"update object {spec.name_plural}")
                    if not dry_run:
                        object_by_name[spec.name_singular] = _update_object(
                            active_client,
                            existing,
                            spec,
                        )
            else:
                result.objects_created += 1
                result.add(f"create object {spec.name_plural}")
                if dry_run:
                    object_by_name[spec.name_singular] = {
                        "id": f"dry-run-{spec.name_singular}",
                        "nameSingular": spec.name_singular,
                        "namePlural": spec.name_plural,
                    }
                else:
                    created = _create_object(active_client, spec)
                    object_by_name[spec.name_singular] = created

            object_id = object_by_name[spec.name_singular]["id"]
            fields = _fields_by_name(active_client, object_id) if not dry_run else {}
            fields_by_object[spec.name_singular] = fields
            for field_spec in spec.fields:
                existing_field = fields.get(field_spec.name)
                if existing_field:
                    result.fields_existing += 1
                    result.add(f"exists field {spec.name_plural}.{field_spec.name}")
                    if _needs_field_update(existing_field, field_spec):
                        result.fields_updated += 1
                        result.add(f"update field {spec.name_plural}.{field_spec.name}")
                        if not dry_run:
                            fields[field_spec.name] = _update_field_metadata(
                                active_client,
                                existing_field,
                                field_spec,
                            )
                    if _needs_option_update(existing_field, field_spec):
                        result.fields_updated += 1
                        result.add(f"update field options {spec.name_plural}.{field_spec.name}")
                        if not dry_run:
                            fields[field_spec.name] = _update_field_options(
                                active_client,
                                existing_field,
                                field_spec,
                            )
                    continue
                result.fields_created += 1
                result.add(f"create field {spec.name_plural}.{field_spec.name}")
                if not dry_run:
                    created_field = _create_field(active_client, object_id, field_spec)
                    fields[field_spec.name] = created_field

        if include_workspace_polish:
            _bootstrap_views(
                active_client,
                result,
                object_by_name=object_by_name,
                fields_by_object=fields_by_object,
                dry_run=dry_run,
            )
            _bootstrap_navigation(
                active_client,
                result,
                object_by_name=object_by_name,
                dry_run=dry_run,
                hide_default_noise=hide_default_noise,
            )
            _bootstrap_read_only_role(
                active_client,
                result,
                object_by_name=object_by_name,
                dry_run=dry_run,
            )
    finally:
        if owns_client:
            active_client.close()
    return result


def _objects_by_name(client: TwentyMetadataClient) -> dict[str, dict[str, Any]]:
    payload = client.rest_get("/rest/metadata/objects")
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise TwentySchemaError("Twenty metadata objects response was not a list")
    return {
        row["nameSingular"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("nameSingular"), str)
    }


def _fields_by_name(client: TwentyMetadataClient, object_metadata_id: str) -> dict[str, dict[str, Any]]:
    data = client.metadata_graphql(
        """
        query Fields($paging: CursorPaging!, $filter: FieldFilter!) {
          fields(paging: $paging, filter: $filter) {
            edges {
              node {
                id
                name
                type
                options
                isSystem
                isNullable
                objectMetadataId
              }
            }
          }
        }
        """,
        {
            "paging": {"first": 200},
            "filter": {"objectMetadataId": {"eq": object_metadata_id}},
        },
    )
    edges = data.get("fields", {}).get("edges", [])
    if not isinstance(edges, list):
        raise TwentySchemaError("Twenty metadata fields response was not a list")
    rows = [
        edge.get("node")
        for edge in edges
        if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
    ]
    return {
        row["name"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }


def _create_object(client: TwentyMetadataClient, spec: ObjectSpec) -> dict[str, Any]:
    data = client.metadata_graphql(
        """
        mutation CreateObject($input: CreateOneObjectInput!) {
          createOneObject(input: $input) {
            id
            nameSingular
            namePlural
            labelSingular
            labelPlural
          }
        }
        """,
        {"input": {"object": spec.as_payload()}},
    )
    return data["createOneObject"]


def _needs_object_update(existing: dict[str, Any], spec: ObjectSpec) -> bool:
    return any(
        existing.get(key) != value
        for key, value in {
            "labelSingular": spec.label_singular,
            "labelPlural": spec.label_plural,
            "description": spec.description,
            "icon": spec.icon,
        }.items()
        if key in existing
    )


def _update_object(
    client: TwentyMetadataClient,
    existing: dict[str, Any],
    spec: ObjectSpec,
) -> dict[str, Any]:
    data = client.metadata_graphql(
        """
        mutation UpdateObject($input: UpdateOneObjectInput!) {
          updateOneObject(input: $input) {
            id
            nameSingular
            namePlural
            labelSingular
            labelPlural
          }
        }
        """,
        {
            "input": {
                "id": existing["id"],
                "update": {
                    "labelSingular": spec.label_singular,
                    "labelPlural": spec.label_plural,
                    "description": spec.description,
                    "icon": spec.icon,
                },
            }
        },
    )
    updated = dict(existing)
    updated.update(data["updateOneObject"])
    return updated


def _create_field(
    client: TwentyMetadataClient,
    object_metadata_id: str,
    spec: FieldSpec,
) -> dict[str, Any]:
    data = client.metadata_graphql(
        """
        mutation CreateField($input: CreateOneFieldMetadataInput!) {
          createOneField(input: $input) {
            id
            name
            type
            objectMetadataId
          }
        }
        """,
        {"input": {"field": spec.as_payload(object_metadata_id)}},
    )
    return data["createOneField"]


def _needs_option_update(existing: dict[str, Any], spec: FieldSpec) -> bool:
    if not spec.options:
        return False
    current_values = {
        option.get("value")
        for option in existing.get("options", [])
        if isinstance(option, dict)
    }
    return any(option.value not in current_values for option in spec.options)


def _needs_field_update(existing: dict[str, Any], spec: FieldSpec) -> bool:
    if "isNullable" in existing and bool(existing.get("isNullable")) != spec.nullable:
        return True
    return False


def _update_field_metadata(
    client: TwentyMetadataClient,
    existing: dict[str, Any],
    spec: FieldSpec,
) -> dict[str, Any]:
    data = client.metadata_graphql(
        """
        mutation UpdateField($input: UpdateOneFieldMetadataInput!) {
          updateOneField(input: $input) {
            id
            name
            type
            options
            isNullable
            objectMetadataId
          }
        }
        """,
        {
            "input": {
                "id": existing["id"],
                "update": {
                    "isNullable": spec.nullable,
                },
            }
        },
    )
    return data["updateOneField"]


def _update_field_options(
    client: TwentyMetadataClient,
    existing: dict[str, Any],
    spec: FieldSpec,
) -> dict[str, Any]:
    data = client.metadata_graphql(
        """
        mutation UpdateField($input: UpdateOneFieldMetadataInput!) {
          updateOneField(input: $input) {
            id
            name
            type
            options
            objectMetadataId
          }
        }
        """,
        {
            "input": {
                "id": existing["id"],
                "update": {
                    "options": _merged_options_payload(existing, spec),
                    "defaultValue": spec.default_value,
                },
            }
        },
    )
    return data["updateOneField"]


def _merged_options_payload(existing: dict[str, Any], spec: FieldSpec) -> list[dict[str, Any]]:
    by_value = {
        option.get("value"): dict(option)
        for option in existing.get("options", [])
        if isinstance(option, dict) and option.get("value")
    }
    for option in spec.options:
        current = by_value.get(option.value)
        if current:
            current.update(option.as_payload())
        else:
            by_value[option.value] = option.as_payload()
    ordered = [by_value[option.value] for option in spec.options if option.value in by_value]
    extras = [
        option
        for value, option in by_value.items()
        if value not in {expected.value for expected in spec.options}
    ]
    return ordered + extras


def _bootstrap_views(
    client: TwentyMetadataClient,
    result: TwentyBootstrapResult,
    *,
    object_by_name: dict[str, dict[str, Any]],
    fields_by_object: dict[str, dict[str, dict[str, Any]]],
    dry_run: bool,
) -> None:
    for spec in GCLBA_OBJECTS:
        object_row = object_by_name[spec.name_singular]
        fields = fields_by_object.get(spec.name_singular, {})
        _ensure_view(
            client,
            result,
            object_row=object_row,
            fields=fields,
            name=f"{spec.label_plural} table",
            icon=spec.icon,
            view_type="TABLE",
            position=spec.nav_position * 10,
            dry_run=dry_run,
            visible_field_names=[field.name for field in spec.fields],
        )
        if spec.kanban_field and spec.kanban_field in fields:
            _ensure_view(
                client,
                result,
                object_row=object_row,
                fields=fields,
                name=f"{spec.label_plural} kanban",
                icon=spec.icon,
                view_type="KANBAN",
                position=spec.nav_position * 10 + 1,
                group_field=spec.kanban_field,
                dry_run=dry_run,
                visible_field_names=[field.name for field in spec.fields],
            )

    for view_spec in SAVED_VIEWS:
        object_row = object_by_name[view_spec.object_name]
        fields = fields_by_object.get(view_spec.object_name, {})
        _ensure_view(
            client,
            result,
            object_row=object_row,
            fields=fields,
            name=view_spec.name,
            icon=view_spec.icon,
            view_type="TABLE",
            position=view_spec.position,
            dry_run=dry_run,
            filters=view_spec.filters,
            sort_field=view_spec.sort_field,
            sort_direction=view_spec.sort_direction,
            visible_field_names=view_spec.visible_fields
            or [field["name"] for field in fields.values() if not field.get("isSystem")],
            hide_unrequested_fields=view_spec.hide_unrequested_fields,
        )
    _rename_legacy_image_views(client, result, object_by_name=object_by_name, dry_run=dry_run)


def _rename_legacy_image_views(
    client: TwentyMetadataClient,
    result: TwentyBootstrapResult,
    *,
    object_by_name: dict[str, dict[str, Any]],
    dry_run: bool,
) -> None:
    image_object = object_by_name.get("gclbaImageEvidence")
    if not image_object:
        return
    views = [] if dry_run else _views_for_object(client, image_object["id"])
    for view in views:
        name = view.get("name")
        if not isinstance(name, str) or "GCLBA Image Evidence" not in name:
            continue
        new_name = name.replace("GCLBA Image Evidence", "GCLBA Images")
        result.add(f"rename view {image_object['namePlural']}.{name}")
        if not dry_run:
            _update_view(client, view["id"], {"name": new_name})


def _ensure_view(
    client: TwentyMetadataClient,
    result: TwentyBootstrapResult,
    *,
    object_row: dict[str, Any],
    fields: dict[str, dict[str, Any]],
    name: str,
    icon: str,
    view_type: str,
    position: float,
    dry_run: bool,
    group_field: str | None = None,
    filters: Iterable[dict[str, Any]] = (),
    sort_field: str | None = None,
    sort_direction: str = "ASC",
    visible_field_names: Iterable[str] = (),
    hide_unrequested_fields: bool = False,
) -> None:
    existing_views = [] if dry_run else _views_for_object(client, object_row["id"])
    existing_view = next((view for view in existing_views if view.get("name") == name), None)
    if not existing_view:
        old_name = _legacy_view_name(name)
        legacy_view = next(
            (view for view in existing_views if view.get("name") == old_name),
            None,
        )
        if legacy_view:
            result.views_existing += 1
            result.add(f"rename view {object_row['namePlural']}.{old_name}")
            if not dry_run:
                _update_view(client, legacy_view["id"], {"name": name, "icon": icon})
                legacy_view["name"] = name
                existing_view = legacy_view
    if existing_view:
        result.views_existing += 1
        result.add(f"exists view {object_row['namePlural']}.{name}")
        if not dry_run:
            _ensure_view_fields(
                client,
                result,
                view_id=existing_view["id"],
                view_label=f"{object_row['namePlural']}.{name}",
                fields=fields,
                visible_field_names=visible_field_names,
                hide_unrequested_fields=hide_unrequested_fields,
            )
        return

    result.views_created += 1
    result.add(f"create view {object_row['namePlural']}.{name}")
    if dry_run:
        return

    view_input: dict[str, Any] = {
        "name": name,
        "objectMetadataId": object_row["id"],
        "type": view_type,
        "icon": icon,
        "position": position,
        "isCompact": False,
        "shouldHideEmptyGroups": True,
    }
    if group_field and group_field in fields:
        view_input["mainGroupByFieldMetadataId"] = fields[group_field]["id"]
        view_input["kanbanColumnWidth"] = 280

    view = _create_view(client, view_input)
    view_id = view["id"]
    if group_field and group_field in fields:
        _create_view_groups(client, view_id, fields[group_field])
    for index, filter_spec in enumerate(filters):
        field_name = filter_spec["field"]
        if field_name not in fields:
            continue
        _create_view_filter(client, view_id, fields[field_name]["id"], filter_spec, index)
    if sort_field and sort_field in fields:
        _create_view_sort(client, view_id, fields[sort_field]["id"], sort_direction)
    _ensure_view_fields(
        client,
        result,
        view_id=view_id,
        view_label=f"{object_row['namePlural']}.{name}",
        fields=fields,
        visible_field_names=visible_field_names,
        hide_unrequested_fields=hide_unrequested_fields,
    )


def _views_for_object(client: TwentyMetadataClient, object_metadata_id: str) -> list[dict[str, Any]]:
    data = client.metadata_graphql(
        """
        query Views($objectMetadataId: String!) {
          getViews(objectMetadataId: $objectMetadataId) {
            id
            name
            type
          }
        }
        """,
        {"objectMetadataId": object_metadata_id},
    )
    views = data.get("getViews", [])
    if not isinstance(views, list):
        return []
    return [view for view in views if isinstance(view, dict)]


def _create_view(client: TwentyMetadataClient, view_input: dict[str, Any]) -> dict[str, Any]:
    data = client.metadata_graphql(
        """
        mutation CreateView($input: CreateViewInput!) {
          createView(input: $input) {
            id
            name
          }
        }
        """,
        {"input": view_input},
    )
    return data["createView"]


def _legacy_view_name(name: str) -> str:
    return name.replace("GCLBA Images", "GCLBA Image Evidence")


def _update_view(
    client: TwentyMetadataClient,
    view_id: str,
    update: dict[str, Any],
) -> None:
    client.metadata_graphql(
        """
        mutation UpdateView($id: String!, $input: UpdateViewInput!) {
          updateView(id: $id, input: $input) { id }
        }
        """,
        {
            "id": view_id,
            "input": {
                "id": view_id,
                **update,
            },
        },
    )


def _create_view_fields(
    client: TwentyMetadataClient,
    view_id: str,
    fields: dict[str, dict[str, Any]],
    visible_field_names: Iterable[str],
    *,
    start_position: int = 1,
) -> None:
    for position, field_name in enumerate(visible_field_names):
        field = fields.get(field_name)
        if not field:
            continue
        client.metadata_graphql(
            """
            mutation CreateViewField($input: CreateViewFieldInput!) {
              createViewField(input: $input) { id }
            }
            """,
            {
                "input": {
                    "viewId": view_id,
                    "fieldMetadataId": field["id"],
                    "isVisible": True,
                    "position": start_position + position,
                    "size": 160,
                }
            },
        )


def _ensure_view_fields(
    client: TwentyMetadataClient,
    result: TwentyBootstrapResult,
    *,
    view_id: str,
    view_label: str,
    fields: dict[str, dict[str, Any]],
    visible_field_names: Iterable[str],
    hide_unrequested_fields: bool = False,
) -> None:
    requested_field_names = list(dict.fromkeys(visible_field_names))
    if "name" in fields:
        requested_field_names = [
            "name",
            *[field_name for field_name in requested_field_names if field_name != "name"],
        ]
    if not requested_field_names:
        return
    requested_positions = {
        field_name: position
        for position, field_name in enumerate(requested_field_names)
    }
    existing_fields = _view_fields_for_view(client, view_id)
    existing_by_field_id = {
        row["fieldMetadataId"]: row
        for row in existing_fields
        if isinstance(row.get("fieldMetadataId"), str)
    }
    existing_field_ids = set(existing_by_field_id)
    for field_name in requested_field_names:
        field = fields.get(field_name)
        if not field:
            continue
        existing = existing_by_field_id.get(field["id"])
        if not existing:
            continue
        update: dict[str, Any] = {}
        if not existing.get("isVisible"):
            update["isVisible"] = True
        expected_position = requested_positions[field_name]
        if existing.get("position") != expected_position:
            update["position"] = expected_position
        if update:
            result.add(f"update view field {view_label}.{field_name}")
            _update_view_field(client, existing["id"], update)
    if hide_unrequested_fields:
        requested_field_ids = {
            fields[field_name]["id"]
            for field_name in requested_field_names
            if field_name in fields
        }
        for existing in existing_fields:
            if (
                existing.get("fieldMetadataId") not in requested_field_ids
                and existing.get("isVisible")
            ):
                result.add(f"hide view field {view_label}.{existing.get('fieldMetadataId')}")
                _update_view_field(client, existing["id"], {"isVisible": False})
    missing_field_names = [
        field_name
        for field_name in requested_field_names
        if fields.get(field_name) and fields[field_name]["id"] not in existing_field_ids
    ]
    for field_name in missing_field_names:
        result.add(f"add view field {view_label}.{field_name}")
        _create_view_fields(
            client,
            view_id,
            fields,
            [field_name],
            start_position=requested_positions[field_name],
        )


def _view_fields_for_view(client: TwentyMetadataClient, view_id: str) -> list[dict[str, Any]]:
    data = client.metadata_graphql(
        """
        query GetViewFields($viewId: String!) {
          getViewFields(viewId: $viewId) {
            id
            fieldMetadataId
            isVisible
            position
          }
        }
        """,
        {"viewId": view_id},
    )
    rows = data.get("getViewFields", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _update_view_field(
    client: TwentyMetadataClient,
    view_field_id: str,
    update: dict[str, Any],
) -> None:
    client.metadata_graphql(
        """
        mutation UpdateViewField($input: UpdateViewFieldInput!) {
          updateViewField(input: $input) { id }
        }
        """,
        {
            "input": {
                "id": view_field_id,
                "update": update,
            }
        },
    )


def _create_view_groups(client: TwentyMetadataClient, view_id: str, field: dict[str, Any]) -> None:
    options = field.get("options") if isinstance(field.get("options"), list) else []
    for option in options:
        value = option.get("value")
        if not value:
            continue
        client.metadata_graphql(
            """
            mutation CreateViewGroup($input: CreateViewGroupInput!) {
              createViewGroup(input: $input) { id }
            }
            """,
            {
                "input": {
                    "viewId": view_id,
                    "fieldValue": value,
                    "position": option.get("position", 0),
                    "isVisible": True,
                }
            },
        )


def _create_view_filter(
    client: TwentyMetadataClient,
    view_id: str,
    field_metadata_id: str,
    spec: dict[str, Any],
    position: int,
) -> None:
    client.metadata_graphql(
        """
        mutation CreateViewFilter($input: CreateViewFilterInput!) {
          createViewFilter(input: $input) { id }
        }
        """,
        {
            "input": {
                "viewId": view_id,
                "fieldMetadataId": field_metadata_id,
                "operand": spec["operand"],
                "value": spec["value"],
                "positionInViewFilterGroup": position,
            }
        },
    )


def _create_view_sort(
    client: TwentyMetadataClient,
    view_id: str,
    field_metadata_id: str,
    direction: str,
) -> None:
    client.metadata_graphql(
        """
        mutation CreateViewSort($input: CreateViewSortInput!) {
          createViewSort(input: $input) { id }
        }
        """,
        {
            "input": {
                "viewId": view_id,
                "fieldMetadataId": field_metadata_id,
                "direction": direction,
            }
        },
    )


def _bootstrap_navigation(
    client: TwentyMetadataClient,
    result: TwentyBootstrapResult,
    *,
    object_by_name: dict[str, dict[str, Any]],
    dry_run: bool,
    hide_default_noise: bool,
) -> None:
    nav_items = [] if dry_run else _navigation_items(client)
    existing_by_target = {
        item.get("targetObjectMetadataId"): item
        for item in nav_items
        if item.get("targetObjectMetadataId")
    }
    map_url = _gclba_map_url()
    map_nav_exists = any(
        item.get("type") == "LINK"
        and (
            item.get("name") == GCLBA_MAP_NAV_NAME
            or item.get("link") == map_url
        )
        for item in nav_items
    )

    if map_url:
        if map_nav_exists:
            result.navigation_existing += 1
            result.add(f"exists nav {GCLBA_MAP_NAV_NAME}")
        else:
            result.navigation_created += 1
            result.add(f"create nav {GCLBA_MAP_NAV_NAME}")
            if not dry_run:
                client.metadata_graphql(
                    """
                    mutation CreateNavigationMenuItem($input: CreateNavigationMenuItemInput!) {
                      createNavigationMenuItem(input: $input) { id }
                    }
                    """,
                    {
                        "input": {
                            "type": "LINK",
                            "name": GCLBA_MAP_NAV_NAME,
                            "link": map_url,
                            "icon": GCLBA_MAP_NAV_ICON,
                            "color": GCLBA_MAP_NAV_COLOR,
                            "position": GCLBA_MAP_NAV_POSITION,
                        }
                    },
                )

    for spec in GCLBA_OBJECTS:
        object_row = object_by_name[spec.name_singular]
        existing_nav = existing_by_target.get(object_row["id"])
        if existing_nav:
            if existing_nav.get("name") != spec.label_plural:
                result.add(f"rename nav {spec.name_plural}")
                if not dry_run:
                    _update_navigation_item(
                        client,
                        existing_nav["id"],
                        {
                            "name": spec.label_plural,
                            "icon": spec.icon,
                            "color": spec.color,
                            "position": spec.nav_position,
                        },
                    )
            result.navigation_existing += 1
            result.add(f"exists nav {spec.name_plural}")
            continue
        result.navigation_created += 1
        result.add(f"create nav {spec.name_plural}")
        if not dry_run:
            client.metadata_graphql(
                """
                mutation CreateNavigationMenuItem($input: CreateNavigationMenuItemInput!) {
                  createNavigationMenuItem(input: $input) { id }
                }
                """,
                {
                    "input": {
                        "type": "OBJECT",
                        "name": spec.label_plural,
                        "targetObjectMetadataId": object_row["id"],
                        "icon": spec.icon,
                        "color": spec.color,
                        "position": spec.nav_position,
                    }
                },
            )

    if not hide_default_noise:
        return

    object_by_id = {row["id"]: row for row in _objects_by_name(client).values()} if not dry_run else {}
    for item in nav_items:
        object_row = object_by_id.get(item.get("targetObjectMetadataId"))
        if not object_row or object_row.get("nameSingular") not in NOISE_OBJECT_NAMES:
            continue
        result.navigation_hidden += 1
        result.add(f"hide nav {object_row['namePlural']}")
        if not dry_run:
            client.metadata_graphql(
                """
                mutation DeleteNavigationMenuItem($id: UUID!) {
                  deleteNavigationMenuItem(id: $id) {
                    id
                  }
                }
                """,
                {"id": item["id"]},
            )


def _update_navigation_item(
    client: TwentyMetadataClient,
    navigation_item_id: str,
    update: dict[str, Any],
) -> None:
    client.metadata_graphql(
        """
        mutation UpdateNavigationMenuItem($input: UpdateOneNavigationMenuItemInput!) {
          updateNavigationMenuItem(input: $input) { id }
        }
        """,
        {
            "input": {
                "id": navigation_item_id,
                "update": update,
            }
        },
    )


def _navigation_items(client: TwentyMetadataClient) -> list[dict[str, Any]]:
    data = client.metadata_graphql(
        """
        query NavigationItems {
          navigationMenuItems {
            id
            name
            type
            link
            targetObjectMetadataId
          }
        }
        """,
    )
    rows = data.get("navigationMenuItems", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _gclba_map_url() -> str:
    return getattr(settings, "GCLBA_MAP_URL", "").strip().rstrip("/")


def _bootstrap_read_only_role(
    client: TwentyMetadataClient,
    result: TwentyBootstrapResult,
    *,
    object_by_name: dict[str, dict[str, Any]],
    dry_run: bool,
) -> None:
    role_label = "GCLBA Sales Read Only"
    existing = None if dry_run else _find_role_by_label(client, role_label)
    if existing:
        result.roles_existing += 1
        result.add(f"exists role {role_label}")
        return

    result.roles_created += 1
    result.add(f"create role {role_label}")
    if dry_run:
        return
    role = client.metadata_graphql(
        """
        mutation CreateRole($input: CreateRoleInput!) {
          createOneRole(createRoleInput: $input) {
            id
            label
          }
        }
        """,
        {
            "input": {
                "label": role_label,
                "description": "Read-only access to GCLBA CRM objects.",
                "icon": "IconEye",
                "canUpdateAllSettings": False,
                "canAccessAllTools": False,
                "canReadAllObjectRecords": False,
                "canUpdateAllObjectRecords": False,
                "canSoftDeleteAllObjectRecords": False,
                "canDestroyAllObjectRecords": False,
                "canBeAssignedToUsers": True,
                "canBeAssignedToAgents": False,
                "canBeAssignedToApiKeys": True,
            }
        },
    )["createOneRole"]
    client.metadata_graphql(
        """
        mutation UpsertObjectPermissions($input: UpsertObjectPermissionsInput!) {
          upsertObjectPermissions(upsertObjectPermissionsInput: $input) {
            objectMetadataId
          }
        }
        """,
        {
            "input": {
                "roleId": role["id"],
                "objectPermissions": [
                    {
                        "objectMetadataId": object_row["id"],
                        "canReadObjectRecords": True,
                        "canUpdateObjectRecords": False,
                        "canSoftDeleteObjectRecords": False,
                        "canDestroyObjectRecords": False,
                    }
                    for object_row in object_by_name.values()
                ],
            }
        },
    )


def _find_role_by_label(client: TwentyMetadataClient, label: str) -> dict[str, Any] | None:
    data = client.metadata_graphql(
        """
        query Roles {
          getRoles {
            id
            label
          }
        }
        """,
    )
    rows = data.get("getRoles", [])
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("label") == label:
            return row
    return None
