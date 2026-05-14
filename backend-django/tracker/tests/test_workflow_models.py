from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from tracker.models import (
    ActionItem,
    Buyer,
    Communication,
    Document,
    EmailTemplate,
    Note,
    Program,
    Property,
    TaxSnapshot,
)
from tracker.services.compliance_timing import (
    ACTION_ATTEMPT_1,
    compute_compliance_timing,
    load_program_rules_from_db,
)


class WorkflowModelTests(TestCase):
    def test_workflow_models_attach_without_replacing_property_rollups(self):
        buyer = Buyer.objects.create(
            full_name="Maria Santos",
            email="maria@example.com",
            organization="Santos Homes",
            status="active",
        )
        program = Program.objects.create(
            key="FeaturedHomes",
            label="Featured Homes",
            cadence="monthly",
            schedule=[{"day": 30, "action": ACTION_ATTEMPT_1, "level": 1}],
            grace_days=3,
        )
        template = EmailTemplate.objects.create(
            slug="test-template",
            name="Test Template",
            program_keys=["FeaturedHomes"],
            variants={ACTION_ATTEMPT_1: {"subject": "Subject", "body": "Body"}},
        )
        prop = Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer=buyer,
            buyer_name="Maria Santos",
            email="maria@example.com",
            organization="Santos Homes",
            program_record=program,
            program="Featured Homes",
            closing_date="2026-01-01",
        )
        action_item = ActionItem.objects.create(
            property=prop,
            buyer=buyer,
            program=program,
            action=ACTION_ATTEMPT_1,
            due_date=date(2026, 1, 31),
            reasons=["First attempt is due."],
            priority=80,
        )
        communication = Communication.objects.create(
            property=prop,
            buyer=buyer,
            template=template,
            method="email",
            action=ACTION_ATTEMPT_1,
            status="draft",
            recipient_email="maria@example.com",
            subject="Draft",
        )
        document = Document.objects.create(
            property=prop,
            communication=communication,
            filename="front-photo.jpg",
            category="photo",
            slot="Front Exterior",
        )
        note = Note.objects.create(property=prop, buyer=buyer, body="Reviewed by staff.")
        tax_snapshot = TaxSnapshot.objects.create(
            property=prop,
            status="delinquent",
            amount_owed="125.50",
            tax_year="2025",
        )

        prop.refresh_from_db()
        self.assertEqual(prop.buyer_name, "Maria Santos")
        self.assertEqual(prop.program, "Featured Homes")
        self.assertEqual(prop.buyer, buyer)
        self.assertEqual(prop.program_record, program)
        self.assertEqual(prop.action_items.get(), action_item)
        self.assertEqual(prop.communications.get(), communication)
        self.assertEqual(prop.documents.get(), document)
        self.assertEqual(prop.activity_notes.get(), note)
        self.assertEqual(prop.tax_snapshots.get(), tax_snapshot)


class SeedWorkflowDefaultsTests(TestCase):
    def test_seed_workflow_defaults_is_idempotent_and_updates_rows(self):
        out = StringIO()
        call_command("seed_workflow_defaults", stdout=out)

        self.assertEqual(Program.objects.count(), 4)
        self.assertEqual(EmailTemplate.objects.count(), 3)
        self.assertIn("Seeded workflow defaults", out.getvalue())

        Program.objects.filter(key="FeaturedHomes").update(label="Changed")
        EmailTemplate.objects.filter(slug="monthly-compliance").update(
            status="draft",
            is_active=False,
        )

        call_command("seed_workflow_defaults", stdout=StringIO())

        self.assertEqual(Program.objects.count(), 4)
        self.assertEqual(EmailTemplate.objects.count(), 3)
        self.assertEqual(Program.objects.get(key="FeaturedHomes").label, "Featured Homes")

        template = EmailTemplate.objects.get(slug="monthly-compliance")
        self.assertEqual(template.status, "active")
        self.assertTrue(template.is_active)
        self.assertIn(ACTION_ATTEMPT_1, template.variants)

    def test_timing_service_can_read_seeded_program_rules(self):
        call_command("seed_workflow_defaults", stdout=StringIO())
        Program.objects.filter(key="FeaturedHomes").update(grace_days=10)

        rules = load_program_rules_from_db()
        result = compute_compliance_timing(
            {"program": "Featured Homes", "closing_date": "2026-01-01"},
            as_of=date(2026, 2, 4),
            rules=rules,
        )

        self.assertEqual(result.program_key, "FeaturedHomes")
        self.assertEqual(result.current_action, ACTION_ATTEMPT_1)
        self.assertFalse(result.is_due_now)
        self.assertEqual(result.days_overdue, 0)

    def test_timing_service_uses_fallback_rules_when_database_has_no_programs(self):
        result = compute_compliance_timing(
            {"program": "Featured Homes", "closing_date": "2026-01-01"},
            as_of=date(2026, 2, 4),
            use_database_rules=True,
        )

        self.assertEqual(result.program_key, "FeaturedHomes")
        self.assertTrue(result.is_due_now)
        self.assertEqual(result.days_overdue, 1)
