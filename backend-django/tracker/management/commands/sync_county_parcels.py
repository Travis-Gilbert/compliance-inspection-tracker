"""
Sync Genesee County parcels (the ArcGIS open-data spine) into Property +
ParcelValueSnapshot, with a per-run SyncRun audit. Daily cadence on Railway;
a plain management command locally.

--dry-run pulls and maps live features WITHOUT any DB writes (or matching), so the
mapping pipeline can be verified before a database exists.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tracker.services.ingest import arcgis_sync, sources
from tracker.services.ingest.arcgis_client import ArcGisClient


class Command(BaseCommand):
    help = "Sync Genesee County parcels (ArcGIS spine) into Property + ParcelValueSnapshot."

    def add_arguments(self, parser):
        parser.add_argument("--key", default="county_parcels", help="DataSource key to sync")
        parser.add_argument("--limit", type=int, default=None, help="cap number of pages")
        parser.add_argument("--record-count", type=int, default=None, help="page size (small for testing)")
        parser.add_argument("--dry-run", action="store_true", help="pull + map live features, no DB")
        parser.add_argument("--reseed", action="store_true", help="force-refresh DataSource rows from sources.py")
        parser.add_argument("--reset-cursor", action="store_true", help="clear last_cursor before syncing")
        parser.add_argument(
            "--recompute-context",
            action="store_true",
            help="after a successful sync, recompute neighborhood-context scores (full set, for spatial correctness)",
        )

    def handle(self, *args, **opts):
        if opts["dry_run"]:
            self._dry_run(opts)
            return

        created, _ = arcgis_sync.seed_data_sources(force=opts["reseed"])
        if created:
            self.stdout.write(f"seeded {created} DataSource row(s)")

        source = arcgis_sync.get_active_source(opts["key"])
        if source is None:
            self.stderr.write(self.style.ERROR(f"No active DataSource for key={opts['key']!r}"))
            return

        if opts["reset_cursor"]:
            source.last_cursor = ""
            source.save(update_fields=["last_cursor"])

        run, result = arcgis_sync.sync_source(
            source,
            page_limit=opts["limit"],
            record_count=opts["record_count"],
        )
        line = (
            f"[{run.status}] fetched={result.fetched} matched={result.matched} "
            f"updated={result.updated} unmatched={result.unmatched} max_oid={result.max_oid}"
        )
        style = self.style.SUCCESS if run.status == "ok" else self.style.WARNING
        self.stdout.write(style(line))
        if result.errors:
            self.stderr.write(self.style.ERROR("errors: " + "; ".join(result.errors)))

        if opts["recompute_context"] and run.status == "ok" and result.updated:
            # Full recompute: LISA needs each parcel's complete neighborhood, so a
            # changed-only scope would build wrong neighbor sets. Cheap at this scale.
            from tracker.services.context import lisa

            context_result = lisa.compute_and_store()
            self.stdout.write(self.style.SUCCESS(f"context recompute: {context_result}"))

    def _dry_run(self, opts):
        seed = sources.seed_for(opts["key"]) or sources.COUNTY_PARCELS
        limit = opts["limit"] or 5
        client = ArcGisClient(
            seed["base_url"],
            seed["layer_id"],
            object_id_field=seed.get("object_id_field", "OBJECTID"),
            max_record_count=seed.get("max_record_count", 2000),
            out_sr=seed.get("out_sr", 4326),
        )
        self.stdout.write(f"DRY RUN {seed['key']} ({seed['base_url']}/{seed['layer_id']})")
        count = 0
        try:
            for feature in client.iter_features(0, record_count=opts["record_count"] or limit, page_limit=1):
                mapped = arcgis_sync.map_feature(feature, seed)
                if mapped is None:
                    self.stdout.write("  (skipped: no parcel id)")
                    continue
                mapped.pop("_oid", None)
                has_geom = "yes" if mapped.pop("boundary_geojson", None) else "no"
                self.stdout.write(
                    f"  {mapped.get('parcel_id')}: owner={mapped.get('owner_of_record')!r} "
                    f"status={mapped.get('forfeiture_status')!r}/{mapped.get('forfeiture_status_year')!r} "
                    f"addr={mapped.get('address')!r} geom={has_geom}"
                )
                count += 1
                if count >= limit:
                    break
        finally:
            client.close()
        self.stdout.write(self.style.SUCCESS(f"dry-run mapped {count} feature(s), no DB writes"))
