from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tracker.models import Property
from tracker.services.naip_intake import (
    DEFAULT_FOOTPRINT_METERS,
    DEFAULT_OUTPUT_SIZE,
    intake_naip_batch,
)


class Command(BaseCommand):
    help = "Ingest dated NAIP aerial chips for geocoded properties (photo intake P1)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--parcel-id", action="append", dest="parcel_ids")
        parser.add_argument("--property-id", type=int, action="append", dest="property_ids")
        parser.add_argument("--footprint-meters", type=float, default=DEFAULT_FOOTPRINT_METERS)
        parser.add_argument("--chip-size", type=int, default=DEFAULT_OUTPUT_SIZE)
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

        results = intake_naip_batch(
            properties,
            footprint_meters=opts["footprint_meters"],
            output_size=opts["chip_size"],
            dry_run=opts["dry_run"],
        )
        created = sum(r.created for r in results)
        updated = sum(r.updated for r in results)
        skipped = sum(r.skipped for r in results)
        errors = sum(len(r.errors) for r in results)
        prefix = "dry-run " if opts["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}NAIP ingest: properties={len(results)} "
                f"created={created} updated={updated} "
                f"skipped={skipped} errors={errors}"
            )
        )
        for result in results:
            if result.errors:
                self.stderr.write(
                    f"property {result.property_id}: {'; '.join(result.errors)}"
                )
