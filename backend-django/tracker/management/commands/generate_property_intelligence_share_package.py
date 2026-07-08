from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from tracker.services.property_intelligence import (
    intelligence_report_snapshot,
    render_share_package_html,
    render_share_package_pdf,
    render_share_package_text,
)


class Command(BaseCommand):
    help = "Generate the plain-language GCLBA property intelligence share package."

    def add_arguments(self, parser):
        parser.add_argument("--text", default=None, help="path to write the text share package")
        parser.add_argument("--html", default=None, help="path to write the HTML share package")
        parser.add_argument("--pdf", default=None, help="path to write the PDF share package")

    def handle(self, *args, **opts):
        snapshot = intelligence_report_snapshot()
        text = render_share_package_text(snapshot)

        self.stdout.write(text)

        if opts["text"]:
            Path(opts["text"]).write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"wrote text -> {opts['text']}"))

        if opts["html"]:
            Path(opts["html"]).write_text(render_share_package_html(snapshot), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"wrote HTML -> {opts['html']}"))

        if opts["pdf"]:
            Path(opts["pdf"]).write_bytes(render_share_package_pdf(snapshot))
            self.stdout.write(self.style.SUCCESS(f"wrote PDF -> {opts['pdf']}"))
