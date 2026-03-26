"""
Management command to deduplicate properties.

Preserves the dedup logic from database.py using raw SQL via
django.db.connection.cursor(), as recommended in the task spec.
The logic is complex enough that ORM-ifying it would be counterproductive.
"""
from django.core.management.base import BaseCommand
from django.db import connection

from tracker.utils.address import build_address_key


def _has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _dedupe_score(row: dict) -> int:
    score = 0
    weighted_fields = {
        "finding": 50,
        "notes": 40,
        "reviewed_at": 30,
        "detection_ran_at": 20,
        "imagery_fetched_at": 15,
        "geocoded_at": 10,
        "streetview_historical_path": 6,
        "compliance_1st_attempt": 5,
        "compliance_2nd_attempt": 5,
        "email": 3,
        "organization": 3,
        "purchase_type": 3,
    }
    for field, weight in weighted_fields.items():
        if _has_value(row.get(field)):
            score += weight
    if row.get("streetview_available"):
        score += 8
    if _has_value(row.get("satellite_path")):
        score += 8
    return score


class Command(BaseCommand):
    help = "Deduplicate properties by parcel_id or address_key"

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM tracker_property ORDER BY id")
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        groups = {}
        for row in rows:
            parcel_id = (row.get("parcel_id") or "").strip().lower()
            address_key = row.get("address_key") or build_address_key(row.get("address", ""))
            key = f"parcel:{parcel_id}" if parcel_id else f"address:{address_key}"
            if key in {"parcel:", "address:"}:
                continue
            groups.setdefault(key, []).append(row)

        merged_count = 0
        deleted_count = 0

        for group_rows in groups.values():
            if len(group_rows) < 2:
                continue

            ranked = sorted(group_rows, key=lambda r: (-_dedupe_score(r), r["id"]))
            primary = ranked[0]
            duplicates = ranked[1:]

            # Merge fields from duplicates into primary
            for dup in duplicates:
                for field in columns:
                    if field in ("id", "created_at", "updated_at"):
                        continue
                    if not _has_value(primary.get(field)) and _has_value(dup.get(field)):
                        primary[field] = dup[field]

            # Reassign communications and delete duplicates
            duplicate_ids = [d["id"] for d in duplicates]
            with connection.cursor() as cursor:
                if duplicate_ids:
                    placeholders = ", ".join(["%s"] * len(duplicate_ids))
                    cursor.execute(
                        f"UPDATE tracker_communication SET property_id = %s WHERE property_id IN ({placeholders})",
                        [primary["id"], *duplicate_ids],
                    )
                    cursor.execute(
                        f"DELETE FROM tracker_property WHERE id IN ({placeholders})",
                        duplicate_ids,
                    )
                    deleted_count += len(duplicate_ids)

            merged_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Dedup complete: {merged_count} groups merged, {deleted_count} duplicates removed"
            )
        )
