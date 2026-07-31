import builtins

from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


def property_photo_upload_to(instance, filename):
    side = instance.side or "evidence"
    return f"property_photos/{instance.property_id}/{side}/{filename}"


class Buyer(models.Model):
    """Normalized buyer record linked gradually from imported property rollups."""

    full_name = models.CharField(max_length=255, default="", db_index=True)
    email = models.EmailField(default="", blank=True, db_index=True)
    phone = models.CharField(max_length=50, default="", blank=True)
    organization = models.CharField(max_length=255, default="", blank=True, db_index=True)
    status = models.CharField(max_length=30, default="unknown", db_index=True)
    flags = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "organization", "id"]
        indexes = [
            models.Index(fields=["full_name", "organization"]),
        ]

    def __str__(self):
        return self.full_name or self.organization or f"Buyer {self.pk}"


class Program(models.Model):
    """Program rules for compliance timing and required evidence."""

    key = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    cadence = models.CharField(max_length=50, default="", blank=True)
    schedule = models.JSONField(default=list, blank=True)
    grace_days = models.PositiveIntegerField(default=0)
    required_uploads = models.JSONField(default=list, blank=True)
    required_docs = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label


class EmailTemplate(models.Model):
    """Draft or active template variants keyed by workflow action."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("retired", "Retired"),
    ]

    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    program_keys = models.JSONField(default=list, blank=True)
    variants = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", db_index=True)
    is_active = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Property(models.Model):
    """
    Core model replacing the raw SQL `properties` table.

    Single concrete model (no inheritance). All properties share the same
    fields regardless of program type.
    """

    # Identity
    address = models.TextField()
    address_key = models.CharField(max_length=255, default="", db_index=True)
    parcel_id = models.CharField(max_length=20, default="", db_index=True)

    # Buyer info
    buyer = models.ForeignKey(
        Buyer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="properties",
    )
    buyer_name = models.CharField(max_length=255, default="")
    email = models.EmailField(default="", blank=True)
    organization = models.CharField(max_length=255, default="", blank=True)

    # Sale details
    program_record = models.ForeignKey(
        Program,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="properties",
    )
    program = models.CharField(max_length=50, default="", db_index=True)
    closing_date = models.CharField(max_length=20, default="")
    commitment = models.TextField(default="")
    purchase_type = models.CharField(max_length=50, default="", blank=True)

    # Legacy compliance contact fields (from FileMaker CSV)
    compliance_1st_attempt = models.CharField(max_length=50, default="", blank=True)
    compliance_2nd_attempt = models.CharField(max_length=50, default="", blank=True)

    # Geocoding
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    formatted_address = models.TextField(default="")
    geocoded_at = models.DateTimeField(null=True, blank=True)

    # Street View imagery
    streetview_path = models.CharField(max_length=500, default="")
    streetview_date = models.CharField(max_length=20, default="")
    streetview_available = models.BooleanField(default=False)
    streetview_historical_path = models.CharField(max_length=500, default="")
    streetview_historical_date = models.CharField(max_length=20, default="")
    historical_imagery_checked_at = models.DateTimeField(null=True, blank=True)
    satellite_path = models.CharField(max_length=500, default="")
    imagery_fetched_at = models.DateTimeField(null=True, blank=True)

    # Detection (heuristic vacancy/demolition triage)
    detection_score = models.FloatField(null=True, blank=True)
    detection_label = models.CharField(max_length=30, default="", db_index=True)
    detection_details = models.JSONField(default=dict, blank=True)
    detection_ran_at = models.DateTimeField(null=True, blank=True)

    # Staff review (desk research finding)
    finding = models.CharField(max_length=30, default="", db_index=True)
    notes = models.TextField(default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=100, default="staff")

    # Compliance status (Christina's fields)
    COMPLIANCE_CHOICES = [
        ("compliant", "Compliant"),
        ("in_progress", "In Progress"),
        ("needs_outreach", "Needs Outreach"),
        ("non_compliant", "Non-Compliant"),
        ("unknown", "Unknown"),
    ]
    compliance_status = models.CharField(
        max_length=20, choices=COMPLIANCE_CHOICES, default="unknown", db_index=True
    )

    # Tax data (from BSA import)
    TAX_STATUS_CHOICES = [
        ("current", "Current"),
        ("delinquent", "Delinquent"),
        ("payment_plan", "Payment Plan"),
        ("unknown", "Unknown"),
    ]
    tax_status = models.CharField(
        max_length=20, choices=TAX_STATUS_CHOICES, default="unknown"
    )
    last_tax_payment = models.DateField(null=True, blank=True)
    tax_amount_owed = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    homeowner_exemption = models.BooleanField(default=False)

    # Outreach tracking
    outreach_attempts = models.PositiveIntegerField(default=0)
    last_outreach_date = models.DateField(null=True, blank=True)
    last_outreach_method = models.CharField(max_length=20, default="", blank=True)

    # Portal/Regrid cross-reference
    regrid_condition = models.CharField(max_length=100, default="", blank=True)
    portal_survey_date = models.DateField(null=True, blank=True)

    # County assessor / ingest (County ArcGIS spine). Nullable so a layer missing an
    # attribute does not break the sync. assessed/taxable values have no open County
    # source yet (see MASTER-PLAN-AND-LANES findings); they stay null until one exists.
    assessed_value = models.FloatField(null=True, blank=True)
    taxable_value = models.FloatField(null=True, blank=True)
    owner_of_record = models.CharField(max_length=255, default="", blank=True)
    property_class = models.CharField(max_length=60, default="", blank=True)
    land_use = models.CharField(max_length=120, default="", blank=True)
    # Tax-distress signal from CountyRealProperty.Status (forfeiture/foreclosure codes).
    forfeiture_status = models.CharField(max_length=20, default="", blank=True, db_index=True)
    forfeiture_status_year = models.CharField(max_length=8, default="", blank=True)
    # Parcel polygon as GeoJSON (no PostGIS column; geopandas rebuilds geometry from this).
    boundary_geojson = models.JSONField(null=True, blank=True)

    # Source-record dossier from the private property-intelligence index.
    # This is deliberately scrubbed of buyer/contact/private notes before import.
    sources = models.JSONField(default=list, blank=True)

    # Import tracking
    import_batch = models.CharField(max_length=100, default="")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["finding", "detection_label"]),
            models.Index(fields=["compliance_status"]),
            models.Index(fields=["buyer_name"]),
        ]

    def __str__(self):
        return f"{self.address} ({self.parcel_id})"

    def save(self, *args, **kwargs):
        # Auto-set address_key for dedup matching
        if self.address and not self.address_key:
            from tracker.utils.address import build_address_key
            self.address_key = build_address_key(self.address)
        super().save(*args, **kwargs)

    @property
    def is_reviewed(self):
        return bool(self.finding)

    @property
    def is_resolved(self):
        return self.finding in {
            "visibly_renovated", "occupied_maintained",
            "partial_progress", "appears_vacant", "structure_gone",
        }

    @property
    def manual_compliance_outcome(self):
        if not self.finding:
            return "pending"

        program = (self.program or "").strip().lower()

        if self.finding == "inconclusive":
            return "needs_inspection"

        if program == "demolition":
            return "compliant" if self.finding == "structure_gone" else "non_compliant"

        if self.finding == "structure_gone":
            return "non_compliant"
        if self.finding in {"visibly_renovated", "occupied_maintained"}:
            return "compliant"
        if self.finding == "partial_progress":
            return "in_progress"
        if self.finding == "appears_vacant":
            return "non_compliant"

        return "unknown"


class PropertyPhoto(models.Model):
    """Uploaded before and after evidence for a property."""

    SIDE_CHOICES = [
        ("before", "Before"),
        ("after", "After"),
    ]
    PROXIMITY_CHOICES = [
        ("unlocated", "Unlocated"),
        ("near_property", "Near Property"),
        ("nearby", "Nearby"),
        ("outside_property_area", "Outside Property Area"),
    ]

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    side = models.CharField(max_length=10, choices=SIDE_CHOICES, db_index=True)
    image = models.ImageField(
        upload_to=property_photo_upload_to,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    original_filename = models.CharField(max_length=255, default="", blank=True)
    caption = models.CharField(max_length=255, default="", blank=True)
    source = models.CharField(max_length=50, default="manual_upload", blank=True)
    is_primary = models.BooleanField(default=False, db_index=True)
    photo_date = models.DateField(null=True, blank=True)
    photo_latitude = models.FloatField(null=True, blank=True)
    photo_longitude = models.FloatField(null=True, blank=True)
    distance_from_property_meters = models.FloatField(null=True, blank=True)
    proximity_status = models.CharField(
        max_length=30,
        choices=PROXIMITY_CHOICES,
        default="unlocated",
        db_index=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["side", "-is_primary", "-uploaded_at"]
        indexes = [
            models.Index(fields=["property", "side", "is_primary"]),
            models.Index(fields=["proximity_status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "side"],
                condition=Q(is_primary=True),
                name="one_primary_photo_per_property_side",
            ),
        ]

    def __str__(self):
        return f"{self.get_side_display()} photo for {self.property.address}"

    @builtins.property
    def public_url(self):
        if not self.image:
            return ""
        return self.image.url


class PropertyImageEvidence(models.Model):
    """Canonical dated visual evidence for a property (photo intake pipeline).

    Owned sources (NAIP, staff, etc.) store pixels via storage_key/sha256.
    Licensed sources (Google Street View) store pointers only (pano_id + pose).
    Capture dates are provider-supplied; never invent them.
    """

    SOURCE_CHOICES = [
        ("STREET_VIEW", "Street View"),
        ("HISTORICAL_STREET_VIEW", "Historical Street View"),
        ("SATELLITE", "Satellite"),
        ("NAIP_AERIAL", "NAIP aerial"),
        ("MAPILLARY", "Mapillary"),
        ("SURVEY_ARCHIVE", "Survey archive"),
        ("BUYER_SUBMITTED", "Buyer submitted"),
        ("STAFF_UPLOAD", "Staff upload"),
        ("OTHER", "Other"),
    ]
    KIND_CHOICES = [
        ("EXTERIOR", "Exterior"),
        ("HISTORICAL_EXTERIOR", "Historical exterior"),
        ("AERIAL", "Aerial"),
        ("BEFORE", "Before"),
        ("AFTER", "After"),
        ("OTHER", "Other"),
    ]
    PRECISION_CHOICES = [
        ("DAY", "Day"),
        ("MONTH", "Month"),
        ("YEAR", "Year"),
    ]
    LICENSE_CHOICES = [
        ("PUBLIC_DOMAIN", "Public domain"),
        ("CC_BY_SA", "CC BY-SA"),
        ("ORG_OWNED", "Organization owned"),
        ("LICENSED_DISPLAY_ONLY", "Licensed display only"),
    ]

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="image_evidence",
    )
    image_source = models.CharField(max_length=40, choices=SOURCE_CHOICES, db_index=True)
    image_kind = models.CharField(
        max_length=30, choices=KIND_CHOICES, default="OTHER", db_index=True
    )
    capture_date = models.CharField(max_length=32, default="", blank=True, db_index=True)
    capture_date_precision = models.CharField(
        max_length=10, choices=PRECISION_CHOICES, default="", blank=True
    )
    storage_key = models.CharField(max_length=500, default="", blank=True, db_index=True)
    sha256 = models.CharField(max_length=64, default="", blank=True, db_index=True)
    pano_id = models.CharField(max_length=120, default="", blank=True, db_index=True)
    source_license = models.CharField(
        max_length=40, choices=LICENSE_CHOICES, default="", blank=True
    )
    footprint_meters = models.FloatField(null=True, blank=True)
    heading_degrees = models.FloatField(null=True, blank=True)
    pitch_degrees = models.FloatField(null=True, blank=True)
    field_of_view = models.FloatField(null=True, blank=True)
    image_url = models.TextField(default="", blank=True)
    thumbnail_url = models.TextField(default="", blank=True)
    attribution = models.CharField(max_length=255, default="", blank=True)
    provider_record_id = models.CharField(max_length=255, default="", blank=True)
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
    )
    metadata = models.JSONField(default=dict, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["property_id", "capture_date", "id"]
        indexes = [
            models.Index(fields=["property", "image_source", "capture_date"]),
            models.Index(fields=["property", "pano_id"]),
            models.Index(fields=["sha256"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "image_source", "capture_date"],
                condition=Q(capture_date__gt="") & ~Q(image_source="HISTORICAL_STREET_VIEW"),
                name="unique_owned_image_evidence_by_date",
            ),
            models.UniqueConstraint(
                fields=["property", "image_source", "pano_id"],
                condition=Q(pano_id__gt="")
                & Q(image_source__in=["STREET_VIEW", "HISTORICAL_STREET_VIEW"]),
                name="unique_licensed_image_evidence_by_pano",
            ),
        ]

    def __str__(self):
        label = self.capture_date or self.pano_id or self.sha256[:12] or "undated"
        return f"{self.image_source} {label} for property {self.property_id}"


class Communication(models.Model):
    """Communication log entries for a property."""

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="communications",
    )
    buyer = models.ForeignKey(
        Buyer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="communications",
    )
    template = models.ForeignKey(
        EmailTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="communications",
    )
    METHOD_CHOICES = [
        ("email", "Email"),
        ("phone", "Phone"),
        ("mail", "Mail"),
        ("site_visit", "Site Visit"),
        ("text", "Text"),
    ]
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    direction = models.CharField(max_length=20, default="outbound")
    action = models.CharField(max_length=40, default="", blank=True, db_index=True)
    template_name = models.CharField(max_length=255, default="", blank=True)
    STATUS_CHOICES = [
        ("logged", "Logged"),
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("bounced", "Bounced"),
        ("failed", "Failed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="logged", db_index=True)
    recipient_email = models.EmailField(default="", blank=True)
    date_sent = models.DateField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=255, default="", blank=True)
    subject = models.CharField(max_length=255, default="")
    body = models.TextField(default="")
    body_hash = models.CharField(max_length=64, default="", blank=True)
    response_received = models.BooleanField(default=False)
    response_date = models.DateField(null=True, blank=True)
    response_notes = models.TextField(default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.method} to {self.property.address} ({self.date_sent})"


class ActionItem(models.Model):
    """Workflow queue item generated by timing rules or staff review."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("dismissed", "Dismissed"),
    ]
    ACTION_CHOICES = [
        ("NOT_DUE_YET", "Not Due Yet"),
        ("ATTEMPT_1", "First Attempt"),
        ("ATTEMPT_2", "Second Attempt"),
        ("WARNING", "Warning"),
        ("DEFAULT_NOTICE", "Default Notice"),
        ("TAX_VERIFICATION", "Tax Verification"),
        ("MISSING_EMAIL", "Missing Email"),
        ("NEEDS_INSPECTION", "Needs Inspection"),
        ("MANUAL_REVIEW", "Manual Review"),
    ]

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="action_items",
    )
    buyer = models.ForeignKey(
        Buyer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="action_items",
    )
    program = models.ForeignKey(
        Program,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="action_items",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open", db_index=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    days_overdue = models.IntegerField(default=0)
    enforcement_level = models.PositiveSmallIntegerField(default=0)
    priority = models.IntegerField(default=0, db_index=True)
    reasons = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=50, default="system", blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-priority", "due_date", "id"]
        indexes = [
            models.Index(fields=["status", "action", "due_date"]),
            models.Index(fields=["property", "status"]),
        ]

    def __str__(self):
        return f"{self.action} for {self.property.address}"


class TaxSnapshot(models.Model):
    """Historical tax status check for a property."""

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="tax_snapshots",
    )
    status = models.CharField(max_length=20, choices=Property.TAX_STATUS_CHOICES, default="unknown")
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.CharField(max_length=50, default="manual", blank=True)
    tax_year = models.CharField(max_length=20, default="", blank=True)
    amount_owed = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    last_payment_date = models.DateField(null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["property", "-checked_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        checked = self.checked_at.date() if self.checked_at else "unsaved"
        return f"{self.property.parcel_id}: {self.status} ({checked})"


class Document(models.Model):
    """S3-ready document or photo metadata."""

    property = models.ForeignKey(
        Property,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )
    communication = models.ForeignKey(
        Communication,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )
    filename = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=500, default="", blank=True)
    storage_url = models.URLField(default="", blank=True)
    mime_type = models.CharField(max_length=120, default="", blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    category = models.CharField(max_length=50, default="document", db_index=True)
    slot = models.CharField(max_length=100, default="", blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["property", "category"]),
        ]

    def __str__(self):
        return self.filename


class Note(models.Model):
    """Append-only internal activity note."""

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="activity_notes",
    )
    buyer = models.ForeignKey(
        Buyer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_notes",
    )
    author = models.CharField(max_length=100, default="staff", blank=True)
    category = models.CharField(max_length=50, default="general", db_index=True)
    body = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["property", "-created_at"]),
        ]

    def __str__(self):
        created = self.created_at.date() if self.created_at else "unsaved"
        return f"Note for {self.property.address} ({created})"


class ImportBatch(models.Model):
    """Tracks CSV import batches for auditing."""

    batch_id = models.CharField(max_length=100, primary_key=True)
    filename = models.CharField(max_length=255, default="")
    row_count = models.IntegerField(default=0)
    imported_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(default="")

    def __str__(self):
        return f"{self.batch_id}: {self.filename} ({self.row_count} rows)"


class DataSource(models.Model):
    """External ingest source registry plus sync cursor.

    Seeded from tracker/services/ingest/sources.py. The field_map and config live
    here (DB-authoritative) so the County can rename a layer field without a code
    change. last_cursor is the OBJECTID high-water (or edit-date) of the last
    committed sync, written only after rows persist so a failed run re-pulls.
    """

    key = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=120, default="")
    kind = models.CharField(max_length=30, default="arcgis")  # arcgis | http | attended_browser
    base_url = models.URLField(default="", blank=True)
    layer_id = models.CharField(max_length=20, default="", blank=True)
    field_map = models.JSONField(default=dict, blank=True)  # source field -> model field
    edit_date_field = models.CharField(max_length=80, default="", blank=True)
    object_id_field = models.CharField(max_length=80, default="OBJECTID", blank=True)
    config = models.JSONField(default=dict, blank=True)  # rest of the seed (max_record_count, address parts, status fields)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_cursor = models.CharField(max_length=120, default="", blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} ({self.kind})"


class SyncRun(models.Model):
    """Per-run audit row for a DataSource sync, so a sync is never silently partial."""

    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="runs")
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="running")  # running | ok | partial | failed
    fetched = models.PositiveIntegerField(default=0)
    matched = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    unmatched = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True)  # errors, skipped parcels, notes

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["source", "-started_at"])]

    def __str__(self):
        when = self.started_at.strftime("%Y-%m-%d %H:%M") if self.started_at else "unsaved"
        return f"{self.source.key} {self.status} @ {when}"


class ParcelValueSnapshot(models.Model):
    """Per-parcel value/status history for the context-layer trajectory variant.

    The County layer carries no assessed/taxable value today, so the actually-
    populated signal here is forfeiture_status; assessed/taxable columns are kept
    for when a value source exists. property is nullable so unmatched county
    parcels can still record history.
    """

    property = models.ForeignKey(
        Property,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="value_snapshots",
    )
    parcel_id = models.CharField(max_length=20, db_index=True)
    assessed_value = models.FloatField(null=True, blank=True)
    taxable_value = models.FloatField(null=True, blank=True)
    forfeiture_status = models.CharField(max_length=20, default="", blank=True)
    source = models.CharField(max_length=40, default="county_arcgis")
    observed_at = models.DateField()
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-observed_at"]
        unique_together = [("parcel_id", "observed_at", "source")]
        indexes = [models.Index(fields=["parcel_id", "observed_at"])]

    def __str__(self):
        return f"{self.parcel_id} @ {self.observed_at} ({self.source})"


class ServiceLineRecord(models.Model):
    """Public service-line dataset (flintpipemap / BlueConduit) per parcel/address.

    Lowest-priority feed; the sync (serviceline.py) is wired in the Phase 1 tail
    once the published access form is confirmed.
    """

    property = models.ForeignKey(
        Property,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_lines",
    )
    parcel_id = models.CharField(max_length=20, default="", db_index=True)
    address = models.TextField(default="")
    material = models.CharField(max_length=60, default="", blank=True)  # copper | lead | galvanized | unknown
    verified_date = models.DateField(null=True, blank=True)
    replacement_status = models.CharField(max_length=60, default="", blank=True)
    source = models.CharField(max_length=50, default="flintpipemap")
    raw = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["parcel_id"])]

    def __str__(self):
        return f"{self.parcel_id}: {self.material or 'unknown'}"


class NeighborhoodContextScore(models.Model):
    """Per-parcel condition scored relative to its local spatial neighborhood (LISA).

    First-class and persisted (not computed at view time). One row per
    (parcel_id, neighborhood_def, signal). neighbor_parcel_ids stores the exact
    reference set so the frontend can highlight it without recomputing.
    """

    property = models.ForeignKey(
        Property,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="context_scores",
    )
    parcel_id = models.CharField(max_length=20, db_index=True)
    neighborhood_def = models.CharField(max_length=20)  # knn8 | queen | rook | faceblock | blockgroup
    signal = models.CharField(max_length=40)  # tax_distress | sale_recency | compliance | assessed_value | composite
    parcel_value = models.FloatField(null=True, blank=True)
    local_mean = models.FloatField(null=True, blank=True)
    local_std = models.FloatField(null=True, blank=True)
    z_score = models.FloatField(null=True, blank=True)
    spatial_lag = models.FloatField(null=True, blank=True)
    moran_cluster = models.CharField(max_length=2, default="NS")  # HH | LL | HL | LH | NS
    moran_p = models.FloatField(null=True, blank=True)
    gi_star = models.FloatField(null=True, blank=True)
    neighbor_parcel_ids = models.JSONField(default=list, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["parcel_id", "neighborhood_def", "signal"])]
        unique_together = [("parcel_id", "neighborhood_def", "signal")]

    def __str__(self):
        return f"{self.parcel_id} {self.signal}/{self.neighborhood_def}: {self.moran_cluster}"


SOURCE_CONFLICT_KIND_CHOICES = [
    ("owner_mismatch", "Owner mismatch"),
    ("reverse_mismatch", "Reverse mismatch"),
    ("pid_orphan", "Parcel orphan"),
    ("condition_regression", "Condition regression"),
    ("value_disagreement", "Value disagreement"),
]

SOURCE_CONFLICT_SEVERITY_CHOICES = [
    ("watch", "Watch"),
    ("review", "Review"),
    ("high", "High"),
]


class SourceConflict(models.Model):
    """A cross-source property disagreement produced by the private index."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("resolved", "Resolved"),
        ("dismissed", "Dismissed"),
    ]

    property = models.ForeignKey(
        Property,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_conflicts",
    )
    parcel_id = models.CharField(max_length=20, db_index=True)
    external_key = models.CharField(max_length=160, default="", blank=True, db_index=True)
    source = models.CharField(max_length=80, default="gclba-index", db_index=True)
    kind = models.CharField(max_length=40, choices=SOURCE_CONFLICT_KIND_CHOICES, db_index=True)
    severity = models.CharField(max_length=20, choices=SOURCE_CONFLICT_SEVERITY_CHOICES, default="review", db_index=True)
    title = models.CharField(max_length=240)
    plain_language = models.TextField(default="", blank=True)
    evidence = models.JSONField(default=list, blank=True)
    observed_at = models.DateField(default=timezone.localdate, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-observed_at", "parcel_id", "kind"]
        indexes = [
            models.Index(fields=["status", "kind"]),
            models.Index(fields=["source", "external_key"]),
        ]

    def __str__(self):
        return f"{self.kind} {self.parcel_id} ({self.status})"


class CandidateProperty(models.Model):
    """A parcel/home candidate that should enter the compliance work queue."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("imported", "Imported"),
        ("dismissed", "Dismissed"),
    ]

    property = models.ForeignKey(
        Property,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidate_properties",
    )
    source_conflict = models.ForeignKey(
        SourceConflict,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidate_properties",
    )
    parcel_id = models.CharField(max_length=20, db_index=True)
    external_key = models.CharField(max_length=160, default="", blank=True, db_index=True)
    address = models.TextField(default="", blank=True)
    reason = models.TextField()
    evidence = models.TextField(default="", blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "parcel_id", "id"]
        indexes = [
            models.Index(fields=["status", "parcel_id"]),
            models.Index(fields=["external_key"]),
        ]

    def __str__(self):
        return f"{self.parcel_id} ({self.status})"


# Five-category activity tagging (Freeman's duty areas). The percentages are the
# weekly-report denominators, not a constraint on logging. category_tag on every
# CaseEvent / ComplianceObservation is what makes the report write itself.
CATEGORY_TAG_CHOICES = [
    ("oversight_enforcement", "Compliance Oversight & Enforcement"),
    ("data_governance", "Project Tracking & Data Governance"),
    ("tech_infrastructure", "Technology & Sales Infrastructure Support"),
    ("stakeholder_coordination", "Stakeholder & Interdepartmental Coordination"),
    ("operational_support", "Operational Support & Continuity"),
]
CATEGORY_TARGET_PCT = {
    "oversight_enforcement": 40,
    "data_governance": 35,
    "tech_infrastructure": 10,
    "stakeholder_coordination": 10,
    "operational_support": 5,
}


class ComplianceCase(models.Model):
    """One per disposed property; lifecycle state distinct from the ActionItem queue.

    Anchored to a parcel via Property (spatial truth not duplicated). status is the
    lifecycle axis; it is a different axis from ActionItem (the actionable queue
    row). The deadline engine maps compliance_timing -> this status and never
    creates or closes ActionItem rows.
    """

    PROGRAM_CHOICES = [
        ("featured_homes", "Featured Homes"),
        ("vip", "VIP"),
        ("demolition", "Demolition"),
        ("ready_for_rehab", "Ready for Rehab"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("on_track", "On Track"),
        ("at_risk", "At Risk"),
        ("non_compliant", "Non-Compliant"),
        ("escalated", "Escalated"),
        ("closed", "Closed"),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="compliance_cases")
    parcel_id = models.CharField(max_length=20, db_index=True)
    program = models.CharField(max_length=30, choices=PROGRAM_CHOICES, default="", db_index=True)
    buyer = models.ForeignKey(
        Buyer, null=True, blank=True, on_delete=models.SET_NULL, related_name="compliance_cases"
    )
    sale_date = models.DateField(null=True, blank=True)
    rehab_deadline = models.DateField(null=True, blank=True)  # sale_date + 12 months
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", db_index=True)
    current_confidence = models.FloatField(null=True, blank=True)
    source_links = models.JSONField(default=dict, blank=True)  # {filemaker_id, regrid_id, gis_feature_id}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "program"]),
            models.Index(fields=["parcel_id"]),
        ]

    def __str__(self):
        return f"Case {self.parcel_id} [{self.program}] {self.status}"


class DeedRestriction(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("satisfied", "Satisfied"),
        ("breached", "Breached"),
        ("expired", "Expired"),
    ]

    case = models.ForeignKey(ComplianceCase, on_delete=models.CASCADE, related_name="deed_restrictions")
    kind = models.CharField(max_length=80, default="")  # owner_occupancy, no_resale_window, use_restriction, ...
    term_start = models.DateField(null=True, blank=True)
    term_end = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", db_index=True)

    def __str__(self):
        return f"{self.kind} ({self.status})"


class Benchmark(models.Model):
    """An enforceable rehab milestone with a due date and evidence."""

    case = models.ForeignKey(ComplianceCase, on_delete=models.CASCADE, related_name="benchmarks")
    label = models.CharField(max_length=120)  # e.g. "exterior weatherproofing", "occupancy"
    due_date = models.DateField(null=True, blank=True)
    met = models.BooleanField(default=False)
    met_on = models.DateField(null=True, blank=True)
    evidence_refs = models.JSONField(default=list, blank=True)  # ComplianceObservation ids

    class Meta:
        ordering = ["due_date", "id"]

    def __str__(self):
        return f"{self.label} ({'met' if self.met else 'open'})"


class ComplianceObservation(models.Model):
    """A piece of compliance evidence; mirrors the Lost Flint observation pattern."""

    KIND_CHOICES = [
        ("photo", "Photo"),
        ("permit", "Permit"),
        ("aerial_change", "Aerial Change"),
        ("assessment_change", "Assessment Change"),
        ("deed_milestone", "Deed Milestone"),
        ("inspection_note", "Inspection Note"),
        ("correspondence", "Correspondence"),
    ]
    SOURCE_CHOICES = [
        ("buyer_submission", "Buyer Submission"),
        ("city_permits", "City Permits"),
        ("regrid", "Regrid"),
        ("ortho_imagery", "Ortho Imagery"),
        ("mapillary", "Mapillary"),
        ("manual", "Manual"),
    ]

    case = models.ForeignKey(ComplianceCase, on_delete=models.CASCADE, related_name="observations")
    observed_at = models.DateTimeField(default=timezone.now, db_index=True)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES, db_index=True)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default="manual")
    geo = models.JSONField(null=True, blank=True)  # {"lat":..,"lon":..}; no PostGIS point on this model
    exif = models.JSONField(null=True, blank=True)  # capture_time, gps, device (preserved for photos)
    artifact_ref = models.CharField(max_length=500, default="", blank=True)  # S3 key of the archived artifact
    document = models.ForeignKey(
        Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="compliance_observations"
    )
    confidence = models.FloatField(null=True, blank=True)
    category_tag = models.CharField(max_length=30, choices=CATEGORY_TAG_CHOICES, default="oversight_enforcement", db_index=True)
    created_by = models.CharField(max_length=100, default="staff")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at"]
        indexes = [
            models.Index(fields=["case", "-observed_at"]),
            models.Index(fields=["category_tag", "-observed_at"]),
        ]

    def __str__(self):
        return f"{self.kind} via {self.source} ({self.observed_at:%Y-%m-%d})"


class CaseEvent(models.Model):
    """Audit trail: every status change / action, with the category_tag the weekly
    report groups by. Factual only (the schema has no field for motive or strategy)."""

    case = models.ForeignKey(ComplianceCase, on_delete=models.CASCADE, related_name="events")
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    transition = models.CharField(max_length=120, default="")  # the state change or action taken
    actor = models.CharField(max_length=100, default="staff")
    evidence_refs = models.JSONField(default=list, blank=True)  # ComplianceObservation ids
    category_tag = models.CharField(max_length=30, choices=CATEGORY_TAG_CHOICES, default="oversight_enforcement", db_index=True)
    note = models.TextField(default="", blank=True)  # factual only
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["case", "-occurred_at"]),
            models.Index(fields=["category_tag", "-occurred_at"]),
        ]

    def __str__(self):
        return f"{self.transition or 'event'} [{self.category_tag}] ({self.occurred_at:%Y-%m-%d})"


class TwentySyncRecord(models.Model):
    """Local projection state for records mirrored into Twenty.

    Django/PostGIS remains canonical. This table only remembers the external
    Twenty record created for a Django-backed object so future syncs can update
    instead of duplicating records.
    """

    tenant_id = models.CharField(max_length=50, default="gclba", db_index=True)
    object_name = models.CharField(max_length=80, db_index=True)
    external_key = models.CharField(max_length=160, db_index=True)
    twenty_record_id = models.CharField(max_length=120, default="", blank=True, db_index=True)
    twenty_url = models.URLField(default="", blank=True)
    property = models.ForeignKey(
        Property,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="twenty_sync_records",
    )
    communication = models.ForeignKey(
        Communication,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="twenty_sync_records",
    )
    action_item = models.ForeignKey(
        ActionItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="twenty_sync_records",
    )
    payload_hash = models.CharField(max_length=64, default="", blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_webhook_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(default="", blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["object_name", "external_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "object_name", "external_key"],
                name="unique_twenty_sync_record",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "object_name"], name="tracker_twe_tenant__f9fb20_idx"),
            models.Index(fields=["twenty_record_id"], name="tracker_twe_twenty__42c188_idx"),
        ]

    def __str__(self):
        return f"{self.object_name}:{self.external_key}"


class TwentyWebhookEvent(models.Model):
    """Audited inbound webhook from Twenty.

    The first operational slice records events and associates them to sync
    records. Canonical Django writes from Twenty should stay explicit and
    field-scoped as follow-up work.
    """

    event = models.CharField(max_length=120, db_index=True)
    object_name = models.CharField(max_length=80, default="", blank=True, db_index=True)
    twenty_record_id = models.CharField(max_length=120, default="", blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False, db_index=True)
    error = models.TextField(default="", blank=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["event", "-received_at"], name="tracker_twe_event_beb689_idx"),
            models.Index(fields=["object_name", "twenty_record_id"], name="tracker_twe_object__498d68_idx"),
        ]

    def __str__(self):
        return f"{self.event} {self.twenty_record_id or 'unknown'}"
