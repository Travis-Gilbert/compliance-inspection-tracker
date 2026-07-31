from __future__ import annotations

import asyncio

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tracker.models import Property
from tracker.services.streetview_history import intake_street_history_batch


class Command(BaseCommand):
    help = (
        "Enumerate historical Street View panoramas as licensed pointers "
        "(photo intake P2). Does not warehouse Google pixels."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--parcel-id", action="append", dest="parcel_ids")
        parser.add_argument("--property-id", type=int, action="append", dest="property_ids")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        qs = Property.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
        if opts.get("parcel_ids"):
            qs = qs.filter(parcel_id__in=opts["parcel_ids"])
        if opts.get("property_ids"):
            qs = qs.filter(id__in=opts["property_ids"])
        qs = qs.order_by("id")
        if opts.get("limit"):
            qs = qs[: opts["limit"]]
        properties = list(qs)
        if not properties:
            raise CommandError("No geocoded properties matched the filters.")

        results = asyncio.run(
            intake_street_history_batch(properties, dry_run=opts["dry_run"])
        )
        if not opts["dry_run"]:
            Property.objects.filter(id__in=[p.id for p in properties]).update(
                historical_imagery_checked_at=timezone.now()
            )

        created = sum(r.created for r in results)
        updated = sum(r.updated for r in results)
        skipped = sum(r.skipped for r in results)
        errors = sum(len(r.errors) for r in results)
        prefix = "dry-run " if opts["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}historical Street View: properties={len(results)} "
                f"created={created} updated={updated} "
                f"skipped={skipped} errors={errors}"
            )
        )
        for result in results:
            if result.errors:
                self.stderr.write(
                    f"property {result.property_id}: {'; '.join(result.errors)}"
                )
