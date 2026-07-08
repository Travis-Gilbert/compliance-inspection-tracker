from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from tracker.services.property_intelligence import import_property_intelligence


class Command(BaseCommand):
    help = "Import scrubbed property-intelligence dossiers from gclba-index JSON output."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to a gclba-index dossier JSON export.")

    def handle(self, *args, **opts):
        path = Path(opts["path"]).expanduser()
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise CommandError("Import payload must be a JSON object.")

        result = import_property_intelligence(payload)
        self.stdout.write(
            self.style.SUCCESS(
                "imported index dossiers "
                f"properties={result['properties']} "
                f"conflicts={result['conflicts']} "
                f"candidates={result['candidates']}"
            )
        )
