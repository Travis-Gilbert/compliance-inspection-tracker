import datetime as dt

from django.test import TestCase

from tracker.models import CandidateProperty, Property, SourceConflict
from tracker.services.compliance import report as weekly_report
from tracker.services.property_intelligence import (
    intelligence_report_snapshot,
    render_share_package_html,
    render_share_package_pdf,
    render_share_package_text,
)


class PropertyIntelligenceReportingTests(TestCase):
    def test_report_snapshot_counts_coverage_and_discoveries(self):
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            program="Featured Homes",
            sources=[
                {
                    "sourceId": "site_control_export",
                    "sourceRecordId": "portal-1",
                    "observedAt": "2026-07-08",
                    "facts": [{"label": "Condition", "value": "Good"}],
                },
                {
                    "sourceId": "county_arcgis",
                    "sourceRecordId": "county-1",
                    "observedAt": "2026-07-08",
                    "facts": [{"label": "Owner", "value": "GCLBA"}],
                },
            ],
        )
        conflict = SourceConflict.objects.create(
            property=prop,
            parcel_id=prop.parcel_id,
            kind="owner_mismatch",
            severity="high",
            title="County owner does not match portal",
            plain_language="Likely missing from the compliance list.",
            evidence=["County says private owner."],
            observed_at=dt.date(2026, 7, 8),
        )
        CandidateProperty.objects.create(
            property=prop,
            source_conflict=conflict,
            parcel_id=prop.parcel_id,
            address=prop.address,
            reason="Portal says GCLBA-owned, county says private party.",
            evidence="County says private owner.",
        )

        snapshot = intelligence_report_snapshot(
            start=dt.date(2026, 7, 6),
            end=dt.date(2026, 7, 12),
        )

        self.assertEqual(snapshot.tracked_property_count, 1)
        self.assertEqual(snapshot.parcels_indexed, 1)
        self.assertEqual(snapshot.source_count, 2)
        self.assertEqual(snapshot.candidate_count, 1)
        self.assertIn("covers 1 parcels across 2 sources", snapshot.coverage_line)
        self.assertIn("1 candidate properties are queued", snapshot.discoveries_line)

    def test_weekly_report_includes_property_intelligence_lines(self):
        Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            program="Featured Homes",
        )

        result = weekly_report.build_report(dt.date(2026, 7, 8))

        self.assertIn("Coverage:", result["text"])
        self.assertIn("Discoveries:", result["text"])
        self.assertNotIn("—", result["text"])
        self.assertNotIn("&mdash;", result["html"])

    def test_share_package_renders_text_html_and_pdf_from_snapshot(self):
        Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            program="Featured Homes",
        )
        snapshot = intelligence_report_snapshot(prepared_on=dt.date(2026, 7, 8))

        text = render_share_package_text(snapshot)
        html = render_share_package_html(snapshot)
        pdf = render_share_package_pdf(snapshot)

        self.assertIn("GCLBA Property Intelligence Share Package", text)
        self.assertIn("Headline count", text)
        self.assertIn("Example discoveries", text)
        self.assertIn("GCLBA Property Intelligence Share Package", html)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertNotIn("—", text)
        self.assertNotIn("—", html)
        self.assertNotIn("&mdash;", html)
