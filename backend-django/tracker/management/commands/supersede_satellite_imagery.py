from __future__ import annotations

from django.core.management.base import BaseCommand

from tracker.models import Property
from tracker.services.photo_supersede import supersede_undated_satellite_batch


class Command(BaseCommand):
    help = (
        "Mark undated SATELLITE evidence superseded when dated NAIP covers "
        "the same parcel (photo intake P6)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--parcel-id", action="append", dest="parcel_ids")
        parser.add_argument("--property-id", type=int, action="append", dest="property_ids")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        qs = Property.objects.all().order_by("id")
        if opts.get("parcel_ids"):
            qs = qs.filter(parcel_id__in=opts["parcel_ids"])
        if opts.get("property_ids"):
            qs = qs.filter(id__in=opts["property_ids"])
        if opts.get("limit"):
            qs = qs[: opts["limit"]]
        properties = list(qs)

        if opts["dry_run"]:
            # Dry-run: count only without writing.
            from tracker.models import PropertyImageEvidence

            with_naip = (
                PropertyImageEvidence.objects.filter(
                    image_source="NAIP_AERIAL",
                    superseded_by__isnull=True,
                )
                .exclude(capture_date="")
                .values_list("property_id", flat=True)
                .distinct()
            )
            undated = PropertyImageEvidence.objects.filter(
                property_id__in=with_naip,
                image_source="SATELLITE",
                capture_date="",
                superseded_by__isnull=True,
            ).count()
            legacy = Property.objects.filter(
                id__in=with_naip,
            ).exclude(satellite_path="").count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"dry-run supersede: candidate_undated_evidence={undated} "
                    f"legacy_satellite_paths={legacy}"
                )
            )
            return

        results = supersede_undated_satellite_batch(properties)
        superseded = sum(r.superseded for r in results)
        created_legacy = sum(r.created_legacy for r in results)
        skipped = sum(r.skipped for r in results)
        self.stdout.write(
            self.style.SUCCESS(
                f"supersede: properties={len(results)} superseded={superseded} "
                f"legacy_materialized={created_legacy} skipped={skipped}"
            )
        )
