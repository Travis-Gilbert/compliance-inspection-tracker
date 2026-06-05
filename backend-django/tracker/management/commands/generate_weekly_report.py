"""
Generate the weekly compliance report (Freeman's template) from tagged activity.

Prints the text report; --html / --pdf write rendered files. Review and send;
nothing goes out automatically.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate the weekly compliance report from tagged CaseEvent / ComplianceObservation activity."

    def add_arguments(self, parser):
        parser.add_argument("--week-of", default=None, help="any date in the target week (YYYY-MM-DD); default this week")
        parser.add_argument("--prepared-by", default="Travis Gilbert")
        parser.add_argument("--html", default=None, help="path to write the HTML report")
        parser.add_argument("--pdf", default=None, help="path to write the PDF (needs weasyprint)")

    def handle(self, *args, **opts):
        from tracker.services.compliance import report as report_mod

        reference = None
        if opts["week_of"]:
            reference = dt.date.fromisoformat(opts["week_of"])
        result = report_mod.build_report(reference, prepared_by=opts["prepared_by"])

        self.stdout.write(result["text"])

        if opts["html"]:
            with open(opts["html"], "w", encoding="utf-8") as handle:
                handle.write(result["html"])
            self.stdout.write(self.style.SUCCESS(f"wrote HTML -> {opts['html']}"))
        if opts["pdf"]:
            pdf = result["pdf"]
            if pdf is None:
                self.stderr.write(self.style.WARNING("PDF skipped: weasyprint not installed (pip install weasyprint)"))
            else:
                with open(opts["pdf"], "wb") as handle:
                    handle.write(pdf)
                self.stdout.write(self.style.SUCCESS(f"wrote PDF -> {opts['pdf']}"))
