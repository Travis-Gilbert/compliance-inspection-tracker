"""
Sync Genesee County building permits into permit ComplianceObservations.

A permit on a parcel after its sale date is the cleanest objective rehab-activity
signal (verification rail). --dry-run pulls and maps live permits with no DB.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tracker.services.ingest import arcgis_sync, sources
from tracker.services.ingest.arcgis_client import ArcGisClient


class Command(BaseCommand):
    help = "Sync building permits into permit ComplianceObservations (verification rail)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="cap features mapped/pages")
        parser.add_argument("--record-count", type=int, default=None, help="page size (small for testing)")
        parser.add_argument("--dry-run", action="store_true", help="pull + map permits, no DB")
        parser.add_argument("--reseed", action="store_true", help="force-refresh DataSource rows")

    def handle(self, *args, **opts):
        from tracker.services.compliance import verification

        if opts["dry_run"]:
            seed = sources.seed_for("building_permits") or sources.BUILDING_PERMITS
            client = ArcGisClient(
                seed["base_url"],
                seed["layer_id"],
                object_id_field=seed.get("object_id_field", "OBJECTID"),
                max_record_count=seed.get("max_record_count", 2000),
            )
            limit = opts["limit"] or 5
            count = 0
            try:
                for feature in client.iter_features(0, record_count=opts["record_count"] or limit, page_limit=1):
                    permit = verification.map_permit(feature, seed)
                    if not permit:
                        self.stdout.write("  (skip: no parcel id)")
                        continue
                    self.stdout.write(
                        f"  {permit['parcel_id']}  date={permit['permit_date']}  "
                        f"cat={permit['category']!r}  val={permit['value']}  {permit['permit_key']}"
                    )
                    count += 1
                    if count >= limit:
                        break
            finally:
                client.close()
            self.stdout.write(self.style.SUCCESS(f"dry-run mapped {count} permit(s), no DB"))
            return

        arcgis_sync.seed_data_sources(force=opts["reseed"])
        source = arcgis_sync.get_active_source("building_permits")
        if source is None:
            self.stderr.write(self.style.ERROR("No active building_permits DataSource"))
            return
        run, result = verification.sync_building_permits(
            source, page_limit=opts["limit"], record_count=opts["record_count"]
        )
        style = self.style.SUCCESS if run.status == "ok" else self.style.WARNING
        self.stdout.write(
            style(f"[{run.status}] fetched={result['fetched']} matched={result['matched']} created={result['created']}")
        )
        if result["errors"]:
            self.stderr.write(self.style.ERROR("errors: " + "; ".join(result["errors"])))
