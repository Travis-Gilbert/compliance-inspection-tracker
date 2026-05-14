from datetime import date

from django.test import SimpleTestCase

from tracker.services.compliance_timing import (
    ACTION_ATTEMPT_1,
    ACTION_ATTEMPT_2,
    ACTION_DEFAULT_NOTICE,
    ACTION_NOT_DUE_YET,
    ACTION_WARNING,
    ComplianceTimingError,
    ComplianceTimingResult,
    compute_batch_timing,
    compute_compliance_timing,
    normalize_program_key,
)


class ComplianceTimingTests(SimpleTestCase):
    def test_featured_homes_default_notice_due(self):
        result = compute_compliance_timing(
            {
                "id": 10,
                "address": "307 Mason St",
                "parcel_id": "41-06-538-004",
                "buyer_name": "Derek Dohrman",
                "program": "Featured Homes",
                "closing_date": "2026-01-01",
            },
            as_of=date(2026, 5, 13),
        )

        self.assertIsInstance(result, ComplianceTimingResult)
        self.assertEqual(result.program_key, "FeaturedHomes")
        self.assertEqual(result.current_action, ACTION_DEFAULT_NOTICE)
        self.assertEqual(result.recommended_enforcement_level, 4)
        self.assertEqual(result.due_date, date(2026, 5, 1))
        self.assertTrue(result.is_due_now)
        self.assertEqual(result.days_overdue, 9)

    def test_ready_for_rehab_alias_uses_ready4rehab_rules(self):
        result = compute_compliance_timing(
            {
                "program": "Ready for Rehab",
                "closing_date": "2026-01-01",
            },
            as_of=date(2026, 3, 5),
        )

        self.assertIsInstance(result, ComplianceTimingResult)
        self.assertEqual(result.program_key, "Ready4Rehab")
        self.assertEqual(result.current_action, ACTION_ATTEMPT_2)
        self.assertEqual(result.due_date, date(2026, 3, 2))
        self.assertTrue(result.is_due_now)
        self.assertEqual(result.days_overdue, 0)

    def test_demolition_schedule_skips_second_attempt(self):
        result = compute_compliance_timing(
            {
                "programType": "Demo",
                "dateSold": "2026-01-01",
            },
            as_of=date(2026, 2, 18),
        )

        self.assertIsInstance(result, ComplianceTimingResult)
        self.assertEqual(result.program_key, "Demolition")
        self.assertEqual(result.current_action, ACTION_DEFAULT_NOTICE)
        self.assertEqual(result.due_date, date(2026, 2, 15))
        self.assertTrue(result.is_due_now)
        self.assertEqual(result.days_overdue, 3)

    def test_vip_grace_period_delays_due_now(self):
        inside_grace = compute_compliance_timing(
            {"program": "VIP Spotlight", "closing_date": "2026-01-01"},
            as_of=date(2026, 4, 5),
        )
        after_grace = compute_compliance_timing(
            {"program": "VIP", "closing_date": "2026-01-01"},
            as_of=date(2026, 4, 7),
        )

        self.assertIsInstance(inside_grace, ComplianceTimingResult)
        self.assertEqual(inside_grace.current_action, ACTION_ATTEMPT_1)
        self.assertFalse(inside_grace.is_due_now)
        self.assertEqual(inside_grace.days_overdue, 0)

        self.assertIsInstance(after_grace, ComplianceTimingResult)
        self.assertEqual(after_grace.current_action, ACTION_ATTEMPT_1)
        self.assertTrue(after_grace.is_due_now)
        self.assertEqual(after_grace.days_overdue, 1)

    def test_completed_first_attempt_advances_to_second_attempt(self):
        result = compute_compliance_timing(
            {
                "program": "Featured Homes",
                "closing_date": "2026-01-01",
                "compliance_1st_attempt": "2026-02-05",
            },
            as_of=date(2026, 3, 5),
        )

        self.assertIsInstance(result, ComplianceTimingResult)
        self.assertEqual(result.completed_actions, (ACTION_ATTEMPT_1,))
        self.assertEqual(result.current_action, ACTION_ATTEMPT_2)
        self.assertTrue(result.is_due_now)
        self.assertFalse(result.action_already_sent)

    def test_completed_current_action_waits_for_next_due_step(self):
        result = compute_compliance_timing(
            {
                "program": "Featured Homes",
                "closing_date": "2026-01-01",
                "compliance_1st_attempt": "2026-02-05",
                "compliance_2nd_attempt": "2026-03-05",
            },
            as_of=date(2026, 3, 5),
        )

        self.assertIsInstance(result, ComplianceTimingResult)
        self.assertEqual(result.current_action, ACTION_ATTEMPT_2)
        self.assertTrue(result.action_already_sent)
        self.assertFalse(result.is_due_now)
        self.assertEqual(result.next_action, ACTION_WARNING)
        self.assertEqual(result.next_due_date, date(2026, 4, 1))

    def test_not_due_yet_before_first_schedule_step(self):
        result = compute_compliance_timing(
            {"program": "Featured Homes", "closing_date": "2026-01-01"},
            as_of=date(2026, 1, 15),
        )

        self.assertIsInstance(result, ComplianceTimingResult)
        self.assertEqual(result.current_action, ACTION_NOT_DUE_YET)
        self.assertFalse(result.is_due_now)
        self.assertEqual(result.next_action, ACTION_ATTEMPT_1)
        self.assertEqual(result.next_due_date, date(2026, 1, 31))

    def test_communication_action_counts_as_completed(self):
        result = compute_compliance_timing(
            {
                "program": "Featured Homes",
                "closing_date": "2026-01-01",
                "communications": [
                    {"action": ACTION_ATTEMPT_1, "status": "sent", "sentAt": "2026-02-01"},
                ],
            },
            as_of=date(2026, 3, 5),
        )

        self.assertIsInstance(result, ComplianceTimingResult)
        self.assertEqual(result.completed_actions, (ACTION_ATTEMPT_1,))
        self.assertEqual(result.last_contact_date, date(2026, 2, 1))
        self.assertEqual(result.current_action, ACTION_ATTEMPT_2)

    def test_unknown_program_returns_error(self):
        result = compute_compliance_timing(
            {"program": "Developer Lot", "closing_date": "2026-01-01"},
            as_of=date(2026, 2, 1),
        )

        self.assertIsInstance(result, ComplianceTimingError)
        self.assertIn("No rules found", result.error)

    def test_missing_closing_date_returns_error(self):
        result = compute_compliance_timing(
            {"program": "Featured Homes"},
            as_of=date(2026, 2, 1),
        )

        self.assertIsInstance(result, ComplianceTimingError)
        self.assertEqual(result.error, "Missing closing date")

    def test_batch_timing_sorts_most_overdue_first(self):
        results = compute_batch_timing(
            [
                {"id": 1, "program": "Featured Homes", "closing_date": "2026-01-01"},
                {"id": 2, "program": "Demolition", "closing_date": "2026-01-01"},
            ],
            as_of=date(2026, 2, 18),
        )

        self.assertEqual([item.property_id for item in results], [1, 2])

    def test_program_normalization_supports_old_and_current_names(self):
        self.assertEqual(normalize_program_key("Featured"), "FeaturedHomes")
        self.assertEqual(normalize_program_key("Ready for Rehab"), "Ready4Rehab")
        self.assertEqual(normalize_program_key("VIP Spotlight"), "VIP")
