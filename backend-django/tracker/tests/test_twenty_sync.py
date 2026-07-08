import datetime as dt
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from tracker.models import (
    ActionItem,
    Buyer,
    ComplianceCase,
    Property,
    PropertyPhoto,
    SourceConflict,
    TwentySyncRecord,
)
from tracker.services.twenty_sync import (
    TwentyDeliveryResult,
    build_twenty_sync_candidates,
    sync_twenty_projection,
)


class FakeTwentyClient:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def upsert_record(self, candidate, *, existing_record_id: str = ""):
        self.calls.append((candidate, existing_record_id))
        if self.fail:
            raise RuntimeError("Twenty rejected the record")
        return TwentyDeliveryResult(
            record_id=f"twenty-{candidate.external_key.replace(':', '-')}",
            record_url=f"https://twenty.test/object/{candidate.object_api_name}/record",
        )


class TwentySyncTests(TestCase):
    @override_settings(
        GCLBA_MAP_URL="https://maps.test/gclba/context",
        GCLBA_BACKEND_PUBLIC_URL="https://backend.test",
    )
    def test_build_candidates_maps_property_workflow_and_quality_records(self):
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            organization="Santos Renovations",
            program="Featured Homes",
            closing_date="2026-01-01",
            commitment="$45,000 rehab",
            purchase_type="cash",
            finding="partial_progress",
            compliance_status="in_progress",
            tax_status="payment_plan",
            tax_amount_owed=Decimal("1234.56"),
            last_tax_payment=dt.date(2026, 2, 1),
            assessed_value=42000,
            taxable_value=21000,
            owner_of_record="Maria Santos",
            property_class="401 Residential",
            land_use="Single family",
            regrid_condition="Fair",
            portal_survey_date=dt.date(2026, 2, 5),
            last_outreach_date=dt.date(2026, 2, 10),
            last_outreach_method="email",
            outreach_attempts=2,
            latitude=43.0123,
            longitude=-83.6789,
            streetview_available=True,
            streetview_path="streetview/41-11-234-012.jpg",
            streetview_date="2025-08",
            streetview_historical_path="historical/41-11-234-012.jpg",
            streetview_historical_date="2019-06",
            satellite_path="satellite/41-11-234-012.jpg",
            imagery_fetched_at=dt.datetime(2026, 2, 12, 15, 30, tzinfo=dt.timezone.utc),
            detection_label="likely_vacant",
            detection_score=0.72,
            detection_details={"signals": {"edge_density": 0.8, "green_coverage": 0.4}},
            reviewed_at=dt.datetime(2026, 2, 13, 16, 45, tzinfo=dt.timezone.utc),
        )
        ActionItem.objects.create(
            property=prop,
            action="WARNING",
            status="open",
            due_date=dt.date(2026, 3, 1),
            days_overdue=4,
            enforcement_level=2,
            priority=90,
            reasons=["Staff warning is due."],
            source="staff",
        )
        ComplianceCase.objects.create(
            property=prop,
            parcel_id=prop.parcel_id,
            program="featured_homes",
            status="at_risk",
            rehab_deadline=dt.date(2026, 6, 1),
        )
        SourceConflict.objects.create(
            property=prop,
            parcel_id=prop.parcel_id,
            kind="owner_mismatch",
            severity="high",
            title="Portal says land bank owned, county says private owner",
            plain_language="Likely missing from the compliance list.",
            evidence=["County owner field no longer matches."],
            observed_at=dt.date(2026, 7, 7),
        )

        candidates = build_twenty_sync_candidates(as_of=dt.date(2026, 3, 5), limit=1)
        by_key = {candidate.external_key: candidate for candidate in candidates}

        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["name"],
            "Maria Santos",
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["propertyAddress"],
            "1234 W Court St",
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["complianceStatus"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["taxStatus"],
            "PAYMENT_PLAN",
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["contactEmail"],
            "maria@example.com",
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["saleDate"],
            "2026-01-01",
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["taxAmountOwed"],
            1234.56,
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["lastTaxPayment"],
            "2026-02-01",
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["assessedValue"],
            42000,
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["crmUrl"],
            f"https://maps.test/gclba/context?property={prop.id}",
        )
        self.assertEqual(
            by_key[f"outreach:{prop.id}:WARNING"].payload["status"],
            "LOGGED",
        )
        self.assertEqual(
            by_key[f"valuation_snapshot:{prop.id}:current"].payload["assessedValue"],
            42000,
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["qualityBand"],
            "FAIR",
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["propertyAddress"],
            "1234 W Court St",
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["streetviewAvailable"],
            True,
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["streetviewDate"],
            "2025-08",
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["historicalStreetviewDate"],
            "2019-06",
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["satelliteAvailable"],
            True,
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["detectionLabel"],
            "likely_vacant",
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["detectionScore"],
            0.72,
        )
        self.assertIn(
            "edge_density: 0.8",
            by_key[f"home_quality:{prop.id}:current"].payload["detectionDetails"],
        )
        self.assertIn(
            "Street View available",
            by_key[f"home_quality:{prop.id}:current"].payload["photoSummary"],
        )
        self.assertEqual(
            by_key[f"home_quality:{prop.id}:current"].payload["mapDossierUrl"],
            f"https://maps.test/gclba/context?property={prop.id}",
        )
        case_candidate = next(
            candidate for candidate in candidates if candidate.object_name == "compliance_case"
        )
        self.assertEqual(case_candidate.payload["caseStatus"], "WARNING")
        conflict_candidate = next(
            candidate for candidate in candidates if candidate.object_name == "source_conflict"
        )
        self.assertEqual(conflict_candidate.payload["kind"], "OWNER_MISMATCH")
        self.assertEqual(conflict_candidate.object_api_name, "gclbaSourceConflicts")
        streetview_image = by_key[f"image_evidence:{prop.id}:streetview"].payload
        self.assertEqual(streetview_image["imageSource"], "STREET_VIEW")
        self.assertEqual(streetview_image["imageKind"], "EXTERIOR")
        self.assertEqual(
            streetview_image["imageUrl"],
            "https://backend.test/images/streetview/41-11-234-012.jpg",
        )
        self.assertEqual(streetview_image["captureDate"], "2025-08")
        self.assertEqual(streetview_image["qualityBand"], "FAIR")
        historical_image = by_key[f"image_evidence:{prop.id}:streetview_historical"].payload
        self.assertEqual(historical_image["imageSource"], "HISTORICAL_STREET_VIEW")
        self.assertEqual(historical_image["captureDate"], "2019-06")
        satellite_image = by_key[f"image_evidence:{prop.id}:satellite"].payload
        self.assertEqual(satellite_image["imageSource"], "SATELLITE")
        self.assertEqual(
            satellite_image["imageUrl"],
            "https://backend.test/images/satellite/41-11-234-012.jpg",
        )

    def test_build_candidates_projects_image_evidence_for_absolute_paths_and_uploads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir)
            current_image = media_root / "current streetview.jpg"
            current_image.write_bytes(b"image")
            with self.settings(
                MEDIA_ROOT=media_root,
                IMAGE_CACHE_DIR=media_root,
                MEDIA_URL="/images/",
                GCLBA_BACKEND_PUBLIC_URL="https://backend.test",
            ):
                prop = Property.objects.create(
                    address="909 E Second St",
                    parcel_id="40-10-227-044",
                    streetview_available=True,
                    streetview_path=str(current_image),
                    streetview_date="2024-05",
                    detection_label="occupied_maintained",
                    detection_score=0.21,
                )
                photo = PropertyPhoto.objects.create(
                    property=prop,
                    side="before",
                    image="property_photos/1/before/front porch.jpg",
                    original_filename="front porch.jpg",
                    caption="Front elevation",
                    source="staff_upload",
                    is_primary=True,
                    photo_date=dt.date(2026, 3, 1),
                    distance_from_property_meters=8.5,
                    proximity_status="near_property",
                )

                candidates = build_twenty_sync_candidates(
                    objects=("image_evidence",),
                    limit=1,
                )

        by_key = {candidate.external_key: candidate for candidate in candidates}
        cached = by_key[f"image_evidence:{prop.id}:streetview"].payload
        self.assertEqual(
            cached["imageUrl"],
            "https://backend.test/images/current%20streetview.jpg",
        )
        upload = by_key[f"image_evidence:{prop.id}:photo:{photo.id}"].payload
        self.assertEqual(upload["imageSource"], "STAFF_UPLOAD")
        self.assertEqual(upload["imageKind"], "BEFORE")
        self.assertEqual(upload["djangoPhotoId"], photo.id)
        self.assertEqual(upload["captureDate"], "2026-03-01")
        self.assertEqual(upload["proximityStatus"], "NEAR_PROPERTY")
        self.assertEqual(upload["matchDistanceMeters"], 8.5)
        self.assertEqual(upload["isPrimary"], True)
        self.assertIn(
            "/images/property_photos/",
            upload["imageUrl"],
        )

    def test_build_candidates_uses_related_buyer_contact_when_property_contact_is_empty(self):
        buyer = Buyer.objects.create(
            full_name="Alicia Green",
            email="alicia@example.com",
            phone="810-555-0101",
            organization="Green Homes LLC",
        )
        prop = Property.objects.create(
            address="234 E Second St",
            parcel_id="41-06-100-002",
            buyer=buyer,
            program="Ready for Rehab",
            closing_date="02/03/2026",
        )

        candidates = build_twenty_sync_candidates(objects=("property",), limit=1)
        payload = candidates[0].payload

        self.assertEqual(payload["buyerName"], "Alicia Green")
        self.assertEqual(payload["contactEmail"], "alicia@example.com")
        self.assertEqual(payload["contactPhone"], "810-555-0101")
        self.assertEqual(payload["organization"], "Green Homes LLC")
        self.assertEqual(payload["saleDate"], "2026-02-03")
        self.assertEqual(payload["name"], "Alicia Green")

    def test_build_candidates_uses_organization_as_buyer_and_label_when_name_missing(self):
        prop = Property.objects.create(
            address="1043 Lask St",
            parcel_id="07-15-503-002",
            email="mtalle01@gmail.com",
            organization="Jewel Capital Investments",
            program="Featured Homes",
        )

        candidates = build_twenty_sync_candidates(objects=("property",), limit=1)
        payload = candidates[0].payload

        self.assertEqual(payload["name"], "Jewel Capital Investments")
        self.assertEqual(payload["buyerName"], "Jewel Capital Investments")
        self.assertEqual(payload["contactEmail"], "mtalle01@gmail.com")

    def test_build_candidates_uses_non_empty_address_placeholder(self):
        prop = Property.objects.create(
            address="",
            parcel_id="41-99-000-001",
            buyer_name="No Address Buyer",
            program="Featured Homes",
        )

        candidates = build_twenty_sync_candidates(objects=("property",), limit=1)
        property_candidate = candidates[0]

        self.assertEqual(
            property_candidate.payload["propertyAddress"],
            "Address unavailable for parcel 41-99-000-001",
        )

    def test_sync_projection_upserts_sync_records(self):
        prop = Property.objects.create(
            address="456 E Kearsley St",
            parcel_id="41-06-102-008",
            buyer_name="James Wilson",
            program="Featured Homes",
            compliance_status="compliant",
        )

        first = sync_twenty_projection(objects=("property", "home_quality"), limit=1)
        second = sync_twenty_projection(objects=("property", "home_quality"), limit=1)

        self.assertEqual(first.created, 2)
        self.assertEqual(second.unchanged, 2)
        record = TwentySyncRecord.objects.get(
            tenant_id="gclba",
            object_name="property",
            external_key=f"property:{prop.id}",
        )
        self.assertEqual(record.property_id, prop.id)
        self.assertEqual(record.metadata["payload"]["djangoPropertyId"], prop.id)

    def test_sync_projection_pushes_changed_records_to_twenty_once(self):
        prop = Property.objects.create(
            address="456 E Kearsley St",
            parcel_id="41-06-102-008",
            buyer_name="James Wilson",
            program="Featured Homes",
            compliance_status="compliant",
        )
        client = FakeTwentyClient()

        first = sync_twenty_projection(
            objects=("property",),
            limit=1,
            push=True,
            client=client,
        )
        second = sync_twenty_projection(
            objects=("property",),
            limit=1,
            push=True,
            client=client,
        )

        self.assertEqual(first.delivered, 1)
        self.assertEqual(first.failed, 0)
        self.assertEqual(second.unchanged, 1)
        self.assertEqual(second.delivered, 0)
        self.assertEqual(len(client.calls), 1)
        record = TwentySyncRecord.objects.get(
            tenant_id="gclba",
            object_name="property",
            external_key=f"property:{prop.id}",
        )
        self.assertEqual(record.twenty_record_id, f"twenty-property-{prop.id}")
        self.assertEqual(record.last_error, "")
        self.assertIsNotNone(record.last_synced_at)

    def test_sync_projection_force_pushes_unchanged_records(self):
        prop = Property.objects.create(
            address="456 E Kearsley St",
            parcel_id="41-06-102-008",
            buyer_name="James Wilson",
            program="Featured Homes",
            compliance_status="compliant",
        )
        client = FakeTwentyClient()

        sync_twenty_projection(
            objects=("property",),
            limit=1,
            push=True,
            client=client,
        )
        forced = sync_twenty_projection(
            objects=("property",),
            limit=1,
            push=True,
            force=True,
            client=client,
        )

        self.assertEqual(forced.unchanged, 1)
        self.assertEqual(forced.delivered, 1)
        self.assertEqual(len(client.calls), 2)

    def test_sync_projection_push_captures_twenty_errors_on_sync_record(self):
        prop = Property.objects.create(
            address="456 E Kearsley St",
            parcel_id="41-06-102-008",
            buyer_name="James Wilson",
            program="Featured Homes",
        )

        result = sync_twenty_projection(
            objects=("property",),
            limit=1,
            push=True,
            client=FakeTwentyClient(fail=True),
        )

        self.assertEqual(result.delivered, 0)
        self.assertEqual(result.failed, 1)
        record = TwentySyncRecord.objects.get(
            tenant_id="gclba",
            object_name="property",
            external_key=f"property:{prop.id}",
        )
        self.assertEqual(record.twenty_record_id, "")
        self.assertIn("Twenty rejected the record", record.last_error)

    def test_sync_command_dry_run_does_not_write_projection_rows(self):
        Property.objects.create(
            address="789 Saginaw St",
            parcel_id="41-06-441-015",
            buyer_name="Keisha Thompson",
            program="Featured Homes",
        )
        out = StringIO()

        call_command("sync_twenty_crm", "--dry-run", "--limit", "1", stdout=out)

        self.assertIn("dry-run twenty sync", out.getvalue())
        self.assertEqual(TwentySyncRecord.objects.count(), 0)
