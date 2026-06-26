from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from tracker.services.twenty_sync import DEFAULT_OBJECTS, sync_twenty_projection


class Command(BaseCommand):
    help = "Project Django canonical records into the Twenty CRM sync table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="sync all properties instead of the default first 50",
        )
        parser.add_argument(
            "--as-of",
            default=None,
            help="workflow queue date used for outreach rows (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="build candidates and print counts without writing TwentySyncRecord rows",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="property cohort size; ignored when --all is provided",
        )
        parser.add_argument(
            "--object",
            action="append",
            choices=DEFAULT_OBJECTS,
            dest="objects",
            help="object slice to sync; repeatable. Defaults to all supported slices.",
        )
        parser.add_argument(
            "--tenant-id",
            default="gclba",
            help="tenant key stored on TwentySyncRecord rows",
        )

    def handle(self, *args, **opts):
        as_of = None
        if opts["as_of"]:
            try:
                as_of = dt.date.fromisoformat(opts["as_of"])
            except ValueError as exc:
                raise CommandError("--as-of must use YYYY-MM-DD") from exc

        result = sync_twenty_projection(
            as_of=as_of,
            dry_run=opts["dry_run"],
            limit=None if opts["all"] else opts["limit"],
            objects=opts["objects"] or DEFAULT_OBJECTS,
            tenant_id=opts["tenant_id"],
        )

        prefix = "dry-run " if opts["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}twenty sync candidates={result.candidates} "
                f"projected={result.projected} created={result.created} "
                f"updated={result.updated} unchanged={result.unchanged}"
            )
        )
