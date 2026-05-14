from django.contrib import admin
from tracker.models import (
    ActionItem,
    Buyer,
    Communication,
    Document,
    EmailTemplate,
    ImportBatch,
    Note,
    Program,
    Property,
    PropertyPhoto,
    TaxSnapshot,
)


@admin.register(Buyer)
class BuyerAdmin(admin.ModelAdmin):
    list_display = ["full_name", "organization", "email", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["full_name", "organization", "email", "phone"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ["label", "key", "cadence", "grace_days", "is_active"]
    list_filter = ["cadence", "is_active"]
    search_fields = ["key", "label"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "status", "is_active", "updated_at"]
    list_filter = ["status", "is_active"]
    search_fields = ["name", "slug"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = [
        "address", "parcel_id", "buyer_name", "program",
        "finding", "detection_label", "compliance_status",
    ]
    list_filter = ["program", "finding", "detection_label", "compliance_status", "tax_status"]
    search_fields = ["address", "parcel_id", "buyer_name", "organization", "email"]
    readonly_fields = ["created_at", "updated_at", "address_key"]


@admin.register(PropertyPhoto)
class PropertyPhotoAdmin(admin.ModelAdmin):
    list_display = [
        "property", "side", "is_primary", "proximity_status", "uploaded_at",
    ]
    list_filter = ["side", "is_primary", "proximity_status"]
    search_fields = ["property__address", "property__parcel_id", "original_filename"]
    readonly_fields = ["uploaded_at", "updated_at", "distance_from_property_meters"]


@admin.register(Communication)
class CommunicationAdmin(admin.ModelAdmin):
    list_display = ["property", "method", "action", "status", "date_sent", "response_received"]
    list_filter = ["method", "direction", "action", "status", "response_received"]
    search_fields = ["property__address", "property__parcel_id", "recipient_email", "subject"]


@admin.register(ActionItem)
class ActionItemAdmin(admin.ModelAdmin):
    list_display = ["property", "action", "status", "due_date", "days_overdue", "priority"]
    list_filter = ["action", "status", "source"]
    search_fields = ["property__address", "property__parcel_id", "property__buyer_name"]


@admin.register(TaxSnapshot)
class TaxSnapshotAdmin(admin.ModelAdmin):
    list_display = ["property", "status", "amount_owed", "tax_year", "checked_at", "source"]
    list_filter = ["status", "source", "tax_year"]
    search_fields = ["property__address", "property__parcel_id"]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["filename", "property", "category", "slot", "size_bytes", "created_at"]
    list_filter = ["category", "mime_type"]
    search_fields = ["filename", "property__address", "property__parcel_id", "storage_key"]


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ["property", "category", "author", "created_at"]
    list_filter = ["category", "author"]
    search_fields = ["property__address", "property__parcel_id", "body"]


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ["batch_id", "filename", "row_count", "imported_at"]
