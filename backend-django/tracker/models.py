from django.db import models


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
    buyer_name = models.CharField(max_length=255, default="")
    email = models.EmailField(default="", blank=True)
    organization = models.CharField(max_length=255, default="", blank=True)

    # Sale details
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


class Communication(models.Model):
    """Communication log entries for a property."""

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
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
    date_sent = models.DateField(null=True, blank=True)
    subject = models.CharField(max_length=255, default="")
    body = models.TextField(default="")
    response_received = models.BooleanField(default=False)
    response_date = models.DateField(null=True, blank=True)
    response_notes = models.TextField(default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.method} to {self.property.address} ({self.date_sent})"


class ImportBatch(models.Model):
    """Tracks CSV import batches for auditing."""

    batch_id = models.CharField(max_length=100, primary_key=True)
    filename = models.CharField(max_length=255, default="")
    row_count = models.IntegerField(default=0)
    imported_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(default="")

    def __str__(self):
        return f"{self.batch_id}: {self.filename} ({self.row_count} rows)"
