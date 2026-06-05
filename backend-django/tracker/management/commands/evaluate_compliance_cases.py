"""
Daily deadline/escalation pass: evaluate open compliance cases against their
benchmarks + program timing, transition lifecycle status, and log CaseEvents.
Scheduled job on Railway; a plain command locally.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Evaluate open compliance cases and transition lifecycle status (deadline engine)."

    def add_arguments(self, parser):
        parser.add_argument("--as-of", default=None, help="evaluation date (YYYY-MM-DD); default today")
        parser.add_argument("--lead-days", type=int, default=30, help="at_risk lead window in days")

    def handle(self, *args, **opts):
        from tracker.services.compliance import deadline

        as_of = dt.date.fromisoformat(opts["as_of"]) if opts["as_of"] else None
        changed = deadline.evaluate_open_cases(as_of=as_of, lead_days=opts["lead_days"])
        if not changed:
            self.stdout.write(self.style.SUCCESS("no case status changes"))
            return
        for parcel_id, status in changed:
            self.stdout.write(f"  {parcel_id} -> {status}")
        self.stdout.write(self.style.SUCCESS(f"{len(changed)} case(s) transitioned"))
