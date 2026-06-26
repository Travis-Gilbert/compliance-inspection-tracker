import datetime as dt
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from tracker.models import ActionItem, ComplianceCase, Property, TwentySyncRecord
from tracker.services.twenty_sync import (
    build_twenty_sync_candidates,
    sync_twenty_projection,
)


class TwentySyncTests(TestCase):
    def test_build_candidates_maps_property_workflow_and_quality_records(self):
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
            finding="partial_progress",
            compliance_status="in_progress",
            tax_status="delinquent",
            assessed_value=42000,
            taxable_value=21000,
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

        candidates = build_twenty_sync_candidates(as_of=dt.date(2026, 3, 5), limit=1)
        by_key = {candidate.external_key: candidate for candidate in candidates}

        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["complianceStatus"],
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            by_key[f"property:{prop.id}"].payload["taxStatus"],
            "DELINQUENT",
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
        case_candidate = next(
            candidate for candidate in candidates if candidate.object_name == "compliance_case"
        )
        self.assertEqual(case_candidate.payload["caseStatus"], "WARNING")

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
