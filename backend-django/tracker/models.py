import builtins

from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q


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
