"""Tests for photo intake storage, timeline, supersede, and Twenty projection."""
from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from tracker.models import Property, PropertyImageEvidence, TwentySyncRecord
from tracker.services.photo_storage import build_storage_key, sha256_bytes, store_owned_bytes
from tracker.services.photo_supersede import supersede_undated_satellite_for_property
from tracker.services.photo_timeline import assemble_timeline
from tracker.services.streetview_history import PanoPointer, upsert_historical_pointer
from tracker.services.twenty_sync import build_twenty_sync_candidates


class PhotoStorageTests(TestCase):
    def test_store_owned_bytes_writes_local_and_is_idempotent_by_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.settings(IMAGE_CACHE_DIR=root, MEDIA_ROOT=root, R2_ACCOUNT_ID=""):
                first = store_owned_bytes(
                    b"chip-bytes",
                    parcel_id="14-13-577-021",
                    source="NAIP_AERIAL",
                    capture_date="2022-06-15",
                )
                second = store_owned_bytes(
                    b"chip-bytes",
                    parcel_id="14-13-577-021",
                    source="NAIP_AERIAL",
                    capture_date="2022-06-15",
                )
                self.assertFalse(first.reused_existing)
                self.assertTrue(second.reused_existing)
                self.assertEqual(first.sha256, sha256_bytes(b"chip-bytes"))
                self.assertEqual(
                    first.storage_key,
                    build_storage_key(
                        parcel_id="14-13-577-021",
                        source="NAIP_AERIAL",
                        capture_date="2022-06-15",
                    ),
                )
                self.assertTrue((root / first.storage_key).is_file())


class PhotoTimelineTests(TestCase):
    def test_assemble_timeline_tags_before_and_current_around_closing(self):
        prop = Property.objects.create(
            address="100 Test St",
            parcel_id="11-11-111-111",
            closing_date="2022-05-16",
            latitude=43.0,
            longitude=-83.7,
        )
        PropertyImageEvidence.objects.create(
            property=prop,
            image_source="NAIP_AERIAL",
            image_kind="AERIAL",
            capture_date="2020-07-01",
            capture_date_precision="DAY",
            source_license="PUBLIC_DOMAIN",
            image_url="https://example.test/2020.jpg",
        )
        PropertyImageEvidence.objects.create(
            property=prop,
            image_source="NAIP_AERIAL",
            image_kind="AERIAL",
            capture_date="2023-06-01",
            capture_date_precision="DAY",
            source_license="PUBLIC_DOMAIN",
            image_url="https://example.test/2023.jpg",
        )
        timeline = assemble_timeline(prop)
        self.assertEqual(timeline.before.capture_date, "2020-07-01")
        self.assertEqual(timeline.current.capture_date, "2023-06-01")
        self.assertEqual(
            [e.tag for e in timeline.entries],
            ["BEFORE", "CURRENT"],
        )


class PhotoSupersedeTests(TestCase):
    def test_supersede_marks_undated_satellite_when_naip_exists(self):
        prop = Property.objects.create(
            address="200 Test St",
            parcel_id="22-22-222-222",
            satellite_path="/images/sat.jpg",
            latitude=43.0,
            longitude=-83.7,
        )
        naip = PropertyImageEvidence.objects.create(
            property=prop,
            image_source="NAIP_AERIAL",
            image_kind="AERIAL",
            capture_date="2021-08-10",
            capture_date_precision="DAY",
            source_license="PUBLIC_DOMAIN",
            image_url="https://example.test/naip.jpg",
        )
        result = supersede_undated_satellite_for_property(prop)
        self.assertEqual(result.superseded, 1)
        self.assertEqual(result.created_legacy, 1)
        sat = PropertyImageEvidence.objects.get(property=prop, image_source="SATELLITE")
        self.assertEqual(sat.superseded_by_id, naip.id)


class StreetHistoryPointerTests(TestCase):
    def test_upsert_historical_pointer_is_idempotent_on_pano(self):
        prop = Property.objects.create(
            address="300 Test St",
            parcel_id="33-33-333-333",
            latitude=43.0,
            longitude=-83.7,
        )
        pointer = PanoPointer(
            pano_id="pano-abc",
            capture_date="2019-06",
            capture_date_precision="MONTH",
            camera_lat=43.0001,
            camera_lng=-83.7001,
            heading_degrees=180.0,
        )
        row1, created1 = upsert_historical_pointer(prop, pointer)
        row2, created2 = upsert_historical_pointer(prop, pointer)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(row1.id, row2.id)
        self.assertEqual(row1.storage_key, "")
        self.assertEqual(row1.sha256, "")
        self.assertEqual(row1.source_license, "LICENSED_DISPLAY_ONLY")
        self.assertIn("/api/imagery/pano/pano-abc", row1.image_url)


@override_settings(GCLBA_BACKEND_PUBLIC_URL="https://backend.test")
class ImageEvidenceProjectionTests(TestCase):
    def test_projects_intake_rows_and_skips_legacy_when_covered(self):
        prop = Property.objects.create(
            address="400 Test St",
            parcel_id="44-44-444-444",
            streetview_path="/images/sv.jpg",
            streetview_date="2025-06",
            streetview_historical_path="/images/hist.jpg",
            streetview_historical_date="2019-06",
            satellite_path="/images/sat.jpg",
            latitude=43.0,
            longitude=-83.7,
        )
        naip = PropertyImageEvidence.objects.create(
            property=prop,
            image_source="NAIP_AERIAL",
            image_kind="AERIAL",
            capture_date="2022-06-15",
            capture_date_precision="DAY",
            storage_key="parcels/44-44-444-444/NAIP_AERIAL/2022-06-15.jpg",
            sha256="a" * 64,
            source_license="PUBLIC_DOMAIN",
            image_url="https://backend.test/images/parcels/44-44-444-444/NAIP_AERIAL/2022-06-15.jpg",
            footprint_meters=60,
        )
        hist = PropertyImageEvidence.objects.create(
            property=prop,
            image_source="HISTORICAL_STREET_VIEW",
            image_kind="HISTORICAL_EXTERIOR",
            capture_date="2018-05",
            capture_date_precision="MONTH",
            pano_id="pano-xyz",
            source_license="LICENSED_DISPLAY_ONLY",
            image_url="https://backend.test/api/imagery/pano/pano-xyz?heading=90.0",
            heading_degrees=90.0,
        )
        sat = PropertyImageEvidence.objects.create(
            property=prop,
            image_source="SATELLITE",
            image_kind="AERIAL",
            capture_date="",
            source_license="LICENSED_DISPLAY_ONLY",
            image_url="/images/sat.jpg",
            superseded_by=naip,
        )
        TwentySyncRecord.objects.create(
            tenant_id="gclba",
            object_name="image_evidence",
            external_key=f"image_evidence:{prop.id}:NAIP_AERIAL:2022-06-15",
            twenty_record_id="twenty-naip-1",
            property=prop,
        )

        candidates = build_twenty_sync_candidates(objects=("image_evidence",), limit=10)
        by_key = {c.external_key: c for c in candidates}

        self.assertIn(f"image_evidence:{prop.id}:NAIP_AERIAL:2022-06-15", by_key)
        naip_payload = by_key[f"image_evidence:{prop.id}:NAIP_AERIAL:2022-06-15"].payload
        self.assertEqual(naip_payload["imageSource"], "NAIP_AERIAL")
        self.assertEqual(naip_payload["captureDatePrecision"], "DAY")
        self.assertEqual(naip_payload["sha256"], "a" * 64)
        self.assertEqual(naip_payload["djangoEvidenceId"], naip.id)

        hist_key = f"image_evidence:{prop.id}:HISTORICAL_STREET_VIEW:pano-xyz"
        self.assertIn(hist_key, by_key)
        self.assertEqual(by_key[hist_key].payload["panoId"], "pano-xyz")
        self.assertEqual(by_key[hist_key].payload["headingDegrees"], 90.0)

        sat_key = f"image_evidence:{prop.id}:evidence:{sat.id}"
        self.assertIn(sat_key, by_key)
        self.assertEqual(by_key[sat_key].payload["supersededBy"], "twenty-naip-1")

        # Legacy historical/satellite skipped because intake covers those sources;
        # legacy current street view still projects (no STREET_VIEW evidence row).
        self.assertIn(f"image_evidence:{prop.id}:streetview", by_key)
        self.assertNotIn(f"image_evidence:{prop.id}:streetview_historical", by_key)
        self.assertNotIn(f"image_evidence:{prop.id}:satellite", by_key)
