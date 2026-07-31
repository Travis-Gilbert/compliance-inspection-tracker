from __future__ import annotations

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from tracker.models import Property
from tracker.services.naip_intake import intake_naip_for_property
from tracker.services.photo_supersede import supersede_undated_satellite_for_property
from tracker.services.photo_timeline import assemble_timeline
from tracker.services.streetview_history import intake_street_history_for_property


class Command(BaseCommand):
    help = (
        "Photo intake: NAIP chips (P1), historical Street View pointers (P2), "
        "and supersede undated satellite when NAIP exists (P6)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--naip",
            action="store_true",
            help="run NAIP aerial intake",
        )
        parser.add_argument(
            "--street-history",
            action="store_true",
            help="enumerate historical Street View pano pointers (no Google pixels stored)",
        )
        parser.add_argument(
            "--supersede",
            action="store_true",
            help="mark undated satellite rows superseded when NAIP covers the parcel",
        )
        parser.add_argument(
            "--all-units",
            action="store_true",
            help="run --naip, --street-history, and --supersede",
        )
        parser.add_argument(
            "--property-id",
            type=int,
            action="append",
            dest="property_ids",
            help="limit to property id(s); repeatable",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="max properties to process (geocoded cohort)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="discover vintages/panos without writing rows or storage",
        )
        parser.add_argument(
            "--show-timeline",
            action="store_true",
            help="print assembled BEFORE/CURRENT timeline after intake",
        )

    def handle(self, *args, **opts):
        run_naip = opts["naip"] or opts["all_units"]
        run_street = opts["street_history"] or opts["all_units"]
        run_supersede = opts["supersede"] or opts["all_units"]
        if not (run_naip or run_street or run_supersede):
            raise CommandError("Specify --naip, --street-history, --supersede, or --all-units")

        qs = Property.objects.filter(latitude__isnull=False, longitude__isnull=False).order_by("id")
        if opts["property_ids"]:
            qs = qs.filter(id__in=opts["property_ids"])
        if opts["limit"] is not None:
            qs = qs[: max(0, opts["limit"])]
        properties = list(qs)
        if not properties:
            self.stdout.write("No geocoded properties matched.")
            return

        dry_run = opts["dry_run"]
        prefix = "dry-run " if dry_run else ""
        self.stdout.write(f"{prefix}Processing {len(properties)} properties…")

        totals = {
            "naip_created": 0,
            "naip_updated": 0,
            "street_created": 0,
            "street_updated": 0,
            "superseded": 0,
            "errors": 0,
        }

        for prop in properties:
            label = prop.parcel_id or prop.address or f"id={prop.id}"
            if run_naip:
                result = intake_naip_for_property(prop, dry_run=dry_run)
                totals["naip_created"] += result.created
                totals["naip_updated"] += result.updated
                totals["errors"] += len(result.errors)
                self.stdout.write(
                    f"  NAIP {label}: +{result.created} ~{result.updated} "
                    f"vintages={result.vintages or '-'} "
                    f"errors={result.errors or '-'}"
                )
            if run_street:
                result = async_to_sync(intake_street_history_for_property)(prop, dry_run=dry_run)
                totals["street_created"] += result.created
                totals["street_updated"] += result.updated
                totals["errors"] += len(result.errors)
                self.stdout.write(
                    f"  Street {label}: +{result.created} ~{result.updated} "
                    f"panos={len(result.panos)} errors={result.errors or '-'}"
                )
            if run_supersede and not dry_run:
                result = supersede_undated_satellite_for_property(prop)
                totals["superseded"] += result.superseded
                self.stdout.write(
                    f"  Supersede {label}: superseded={result.superseded} "
                    f"legacy={result.created_legacy}"
                )
            if opts["show_timeline"]:
                timeline = assemble_timeline(prop)
                before = timeline.before.capture_date if timeline.before else "-"
                current = timeline.current.capture_date if timeline.current else "-"
                self.stdout.write(
                    f"  Timeline {label}: closing={timeline.closing_date or '-'} "
                    f"BEFORE={before} CURRENT={current} entries={len(timeline.entries)}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}done naip=+{totals['naip_created']}/~{totals['naip_updated']} "
                f"street=+{totals['street_created']}/~{totals['street_updated']} "
                f"superseded={totals['superseded']} errors={totals['errors']}"
            )
        )
