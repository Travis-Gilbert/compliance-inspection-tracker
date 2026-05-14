import json
from datetime import date
from io import StringIO
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.test import TestCase

from tracker.models import ActionItem, Communication, Document, EmailTemplate, Property
from tracker.services.compliance_timing import ACTION_ATTEMPT_1, ACTION_ATTEMPT_2


class WorkflowApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workflow_defaults", stdout=StringIO())

    def test_property_timing_endpoint_returns_backend_timing(self):
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        response = self.client.get(
            f"/api/workflow/properties/{prop.id}/timing",
            {"as_of": "2026-03-05"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["programType"], "FeaturedHomes")
        self.assertEqual(payload["currentAction"], ACTION_ATTEMPT_2)
        self.assertEqual(payload["dueDate"], "2026-03-02")
        self.assertTrue(payload["isDueNow"])

    def test_property_timing_endpoint_returns_manual_review_payload_for_timing_error(self):
        prop = Property.objects.create(
            address="999 Missing Program Rd",
            parcel_id="41-00-000-001",
            buyer_name="No Program",
            email="noprog@example.com",
            program="",
            closing_date="",
        )

        response = self.client.get(f"/api/workflow/properties/{prop.id}/timing")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["currentAction"], "MANUAL_REVIEW")
        self.assertTrue(payload["error"])
        self.assertIn(payload["error"], payload["reasons"])

    def test_action_queue_groups_due_and_manual_work_items(self):
        due_with_email = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )
        due_without_email = Property.objects.create(
            address="456 E Kearsley St",
            parcel_id="41-06-102-008",
            buyer_name="James Wilson",
            email="",
            program="Featured Homes",
            closing_date="2026-01-01",
        )
        inconclusive = Property.objects.create(
            address="789 Saginaw St",
            parcel_id="41-06-441-015",
            buyer_name="Keisha Thompson",
            email="keisha@example.com",
            program="VIP",
            closing_date="2026-01-01",
            finding="inconclusive",
        )
        ActionItem.objects.create(
            property=inconclusive,
            action="TAX_VERIFICATION",
            status="open",
            due_date=date(2026, 3, 1),
            priority=90,
            reasons=["Tax status needs verification before next outreach."],
        )

        response = self.client.get("/api/workflow/action-queue", {"as_of": "2026-03-05"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        groups = {group["action"]: group for group in payload["groups"]}

        self.assertEqual(groups[ACTION_ATTEMPT_2]["count"], 1)
        self.assertEqual(groups["MISSING_EMAIL"]["count"], 1)
        self.assertEqual(groups["NEEDS_INSPECTION"]["count"], 1)
        self.assertEqual(groups["TAX_VERIFICATION"]["count"], 1)

        due_item = groups[ACTION_ATTEMPT_2]["items"][0]
        self.assertEqual(due_item["propertyId"], due_with_email.id)
        self.assertEqual(groups["MISSING_EMAIL"]["items"][0]["propertyId"], due_without_email.id)

    def test_action_queue_skips_timing_actions_for_resolved_properties(self):
        resolved = Property.objects.create(
            address="77 Resolved Ave",
            parcel_id="41-22-333-444",
            buyer_name="Resolved Buyer",
            email="resolved@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
            finding="occupied_maintained",
        )

        response = self.client.get("/api/workflow/action-queue", {"as_of": "2026-03-05"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        queued_ids = {
            item["propertyId"]
            for group in payload["groups"]
            for item in group["items"]
        }
        self.assertNotIn(resolved.id, queued_ids)

    def test_action_queue_prefers_persisted_action_item_over_timing_duplicate(self):
        prop = Property.objects.create(
            address="88 Managed Workflow St",
            parcel_id="41-22-333-555",
            buyer_name="Managed Buyer",
            email="managed@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )
        ActionItem.objects.create(
            property=prop,
            action=ACTION_ATTEMPT_2,
            status="in_progress",
            due_date=date(2026, 3, 1),
            days_overdue=4,
            enforcement_level=4,
            priority=99,
            reasons=["Staff follow-up already in progress."],
            source="staff",
        )

        response = self.client.get("/api/workflow/action-queue", {"as_of": "2026-03-05"})

        self.assertEqual(response.status_code, 200)
        groups = {group["action"]: group for group in response.json()["groups"]}
        group = groups[ACTION_ATTEMPT_2]
        self.assertEqual(len(group["items"]), 1)
        item = group["items"][0]
        self.assertEqual(item["propertyId"], prop.id)
        self.assertEqual(item["status"], "in_progress")
        self.assertEqual(item["priority"], 99)
        self.assertEqual(item["reasons"], ["Staff follow-up already in progress."])
        self.assertEqual(item["source"], "staff")

    def test_template_preview_renders_seeded_variant(self):
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        response = self.client.get(
            f"/api/workflow/properties/{prop.id}/template-preview",
            {
                "action": ACTION_ATTEMPT_2,
                "template_slug": "monthly-compliance",
                "as_of": "2026-03-05",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["template"]["slug"], "monthly-compliance")
        self.assertEqual(payload["recipientEmail"], "maria@example.com")
        self.assertIn("Second request", payload["subject"])
        self.assertEqual(payload["timing"]["currentAction"], ACTION_ATTEMPT_2)

    def test_workflow_communication_rejects_inactive_template(self):
        EmailTemplate.objects.filter(slug="monthly-compliance").update(status="draft", is_active=False)
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        response = self.client.post(
            f"/api/workflow/properties/{prop.id}/communications",
            data=json.dumps(
                {
                    "method": "email",
                    "action": ACTION_ATTEMPT_1,
                    "status": "sent",
                    "template_slug": "monthly-compliance",
                    "date_sent": "2026-02-05",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("No email template found", response.json()["detail"])
        self.assertEqual(Communication.objects.count(), 0)

    def test_workflow_communication_logging_updates_property_rollups(self):
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        response = self.client.post(
            f"/api/workflow/properties/{prop.id}/communications",
            data=json.dumps(
                {
                    "method": "email",
                    "action": ACTION_ATTEMPT_1,
                    "status": "sent",
                    "template_slug": "monthly-compliance",
                    "date_sent": "2026-02-05",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["action"], ACTION_ATTEMPT_1)
        self.assertEqual(payload["status"], "sent")
        self.assertEqual(payload["template_slug"], "monthly-compliance")
        self.assertEqual(payload["date_sent"], "2026-02-05")
        self.assertTrue(payload["subject"])
        self.assertTrue(payload["body"])

        prop.refresh_from_db()
        self.assertEqual(prop.compliance_1st_attempt, "2026-02-05")
        self.assertEqual(prop.last_outreach_date, date(2026, 2, 5))
        self.assertEqual(prop.last_outreach_method, "email")
        self.assertEqual(prop.outreach_attempts, 1)

        comm = Communication.objects.get(property=prop)
        self.assertEqual(comm.recipient_email, "maria@example.com")
        self.assertTrue(comm.body_hash)
        self.assertEqual(Document.objects.filter(property=prop).count(), 2)

        listing = self.client.get(f"/api/workflow/properties/{prop.id}/communications")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()[0]["id"], comm.id)

    def test_workflow_communication_uses_sent_date_for_template_rendering(self):
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        response = self.client.post(
            f"/api/workflow/properties/{prop.id}/communications",
            data=json.dumps(
                {
                    "method": "email",
                    "action": ACTION_ATTEMPT_1,
                    "status": "sent",
                    "template_slug": "monthly-compliance",
                    "date_sent": "2026-02-05",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("2026-01-31", payload["body"])

    def test_generated_documents_endpoint_and_mail_packet_generation(self):
        prop = Property.objects.create(
            address="456 E Kearsley St",
            parcel_id="41-06-102-008",
            buyer_name="James Wilson",
            email="",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.settings(MEDIA_ROOT=Path(tmpdir), MEDIA_URL="/images/"):
                response = self.client.post(
                    "/api/workflow/letters/packet",
                    data=json.dumps({"property_ids": [prop.id]}),
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["batch_document"]["storage_url"].startswith("/images/generated_documents/"))
                self.assertEqual(len(payload["letters"]), 1)
                self.assertEqual(len(payload["audits"]), 1)

                property_docs = self.client.get(f"/api/workflow/properties/{prop.id}/documents")
                self.assertEqual(property_docs.status_code, 200)
                docs = property_docs.json()
                categories = {item["category"] for item in docs}
                self.assertIn("mail_packet", categories)
                self.assertIn("mail_audit", categories)

                batch_path = Path(tmpdir) / payload["batch_document"]["storage_key"]
                self.assertTrue(batch_path.exists())
                self.assertIn("mail packet", batch_path.read_text(encoding="utf-8").lower())

    def test_mail_packet_generation_returns_404_without_creating_artifacts_for_missing_template(self):
        prop = Property.objects.create(
            address="101 Broken Template Ave",
            parcel_id="41-99-999-999",
            buyer_name="Template Failure",
            email="",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.settings(MEDIA_ROOT=Path(tmpdir), MEDIA_URL="/images/"):
                response = self.client.post(
                    "/api/workflow/letters/packet",
                    data=json.dumps(
                        {
                            "property_ids": [prop.id],
                            "action": "UNKNOWN_ACTION",
                        }
                    ),
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 404)
                self.assertIn("No email template found", response.json()["detail"])
                self.assertEqual(Document.objects.count(), 0)
                self.assertFalse(any(Path(tmpdir).rglob("*")))
