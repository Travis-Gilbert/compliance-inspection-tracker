from django.contrib import admin
from tracker.models import Property, PropertyPhoto, Communication, ImportBatch


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
    list_display = ["property", "method", "direction", "date_sent", "response_received"]
    list_filter = ["method", "direction", "response_received"]


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ["batch_id", "filename", "row_count", "imported_at"]
