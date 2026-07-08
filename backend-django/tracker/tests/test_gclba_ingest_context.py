import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from tracker.models import DataSource, NeighborhoodContextScore, ParcelValueSnapshot, Property
from tracker.services.context import composite, lisa, signals
from tracker.services.ingest import arcgis_sync, sources
from tracker.services.ingest.arcgis_client import ArcGisClient
from tracker.services.ingest.arcgis_resolver import resolve_arcgis_layer


class ArcGisClientTests(SimpleTestCase):
    def test_object_id_where_clause_uses_high_water_cursor(self):
        client = ArcGisClient("https://example.test/FeatureServer", 0, delay_seconds=0)
        try:
            self.assertEqual(client._where(42), "OBJECTID > 42")
            self.assertEqual(
                client._where(42, "Status = 'NCFD'"),
                "(OBJECTID > 42) AND (Status = 'NCFD')",
            )
        finally:
            client.close()

    def test_edit_date_where_clause_uses_timestamp_literal(self):
        client = ArcGisClient(
            "https://example.test/FeatureServer",
            0,
            edit_date_field="EditDate",
            delay_seconds=0,
        )
        try:
            self.assertEqual(client._where(""), "1=1")
            self.assertEqual(
                client._where("2026-06-01T12:30:00Z"),
                "EditDate > TIMESTAMP '2026-06-01 12:30:00'",
            )
            self.assertEqual(client._order_by(), "EditDate ASC, OBJECTID ASC")
        finally:
            client.close()


class GclbaIngestContextTests(TestCase):
    def test_resolver_finds_polygon_parcel_layer_metadata(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                pass

            def json(self):
                return self.payload

        class FakeClient:
            def get(self, url, params):
                if url.endswith("/sharing/rest/search"):
                    return FakeResponse(
                        {
                            "results": [
                                {
                                    "type": "Feature Service",
                                    "title": "CountyRealProperty",
                                    "url": "https://services.example/CountyRealProperty/FeatureServer",
                                }
                            ]
                        }
                    )
                if url.endswith("/FeatureServer"):
                    return FakeResponse({"layers": [{"id": 0, "name": "Parcels"}]})
                return FakeResponse(
                    {
                        "name": "Parcels",
                        "geometryType": "esriGeometryPolygon",
                        "objectIdField": "OBJECTID",
                        "maxRecordCount": 2000,
                        "editFieldsInfo": {"editDateField": "EditDate"},
                        "fields": [
                            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
                            {"name": "PARIDSHORT"},
                            {"name": "OWNNAME"},
                            {"name": "Lat"},
                            {"name": "Lon"},
                            {"name": "Status"},
                            {"name": "StatusYr"},
                            {"name": "PROPNUM"},
                            {"name": "PROPSTREET"},
                        ],
                    }
                )

        resolved = resolve_arcgis_layer(
            org_url="https://gccountymi.maps.arcgis.com",
            search_query="parcel",
            service_name_contains="CountyRealProperty",
            client=FakeClient(),
        )

        self.assertEqual(resolved.base_url, "https://services.example/CountyRealProperty/FeatureServer")
        self.assertEqual(resolved.layer_id, "0")
        self.assertEqual(resolved.object_id_field, "OBJECTID")
        self.assertEqual(resolved.edit_date_field, "EditDate")
        self.assertEqual(resolved.field_map["PARIDSHORT"], "parcel_id")
        self.assertEqual(resolved.config["status_field"], "Status")

    def test_map_feature_normalizes_county_feature(self):
        feature = {
            "attributes": {
                "OBJECTID": 7,
                "PARIDSHORT": "41-06-538-004",
                "OWNNAME": "GENESEE COUNTY LAND BANK",
                "PROPNUM": "307",
                "PROPDIR": "E",
                "PROPSTREET": "MASON ST",
                "PROPCITY": "FLINT",
                "PROPZIP": "48503",
                "Status": "NCFD",
                "StatusYr": "2025",
                "Lat": 43.018,
                "Lon": -83.694,
            },
            "geometry": {
                "rings": [
                    [
                        [-83.695, 43.017],
                        [-83.693, 43.017],
                        [-83.693, 43.019],
                        [-83.695, 43.019],
                        [-83.695, 43.017],
                    ]
                ]
            },
        }

        mapped = arcgis_sync.map_feature(feature, sources.COUNTY_PARCELS)

        self.assertEqual(mapped["parcel_id"], "41-06-538-004")
        self.assertEqual(mapped["owner_of_record"], "GENESEE COUNTY LAND BANK")
        self.assertEqual(mapped["forfeiture_status"], "NCFD")
        self.assertEqual(mapped["forfeiture_status_year"], "2025")
        self.assertEqual(mapped["boundary_geojson"]["type"], "Polygon")
        self.assertIn("MASON", mapped["address"])

    def test_sync_source_upserts_property_snapshot_and_cursor(self):
        source = DataSource.objects.create(
            key="county_parcels",
            label="County parcels",
            kind="arcgis",
            base_url="https://example.test/FeatureServer",
            layer_id="0",
            object_id_field="OBJECTID",
            field_map=sources.COUNTY_PARCELS["field_map"],
            config={
                "parcel_id_field": "PARIDSHORT",
                "address_part_fields": sources.COUNTY_PARCELS["address_part_fields"],
                "status_field": "Status",
                "status_year_field": "StatusYr",
                "max_record_count": 2000,
                "out_sr": 4326,
            },
        )
        prop = Property.objects.create(
            address="307 Mason St",
            parcel_id="41-06-538-004",
            buyer_name="Tracked buyer",
        )
        feature = {
            "attributes": {
                "OBJECTID": 11,
                "PARIDSHORT": "41-06-538-004",
                "OWNNAME": "GENESEE COUNTY LAND BANK",
                "Status": "CFD",
                "StatusYr": "2024",
                "Lat": 43.018,
                "Lon": -83.694,
            },
            "geometry": {
                "rings": [
                    [
                        [-83.695, 43.017],
                        [-83.693, 43.017],
                        [-83.693, 43.019],
                        [-83.695, 43.019],
                        [-83.695, 43.017],
                    ]
                ]
            },
        }

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def count_since(self, *args, **kwargs):
                return 1

            def iter_features(self, *args, **kwargs):
                yield feature

            def close(self):
                pass

        with patch("tracker.services.ingest.arcgis_sync.ArcGisClient", FakeClient):
            run, result = arcgis_sync.sync_source(source)

        source.refresh_from_db()
        prop.refresh_from_db()
        self.assertEqual(run.status, "ok")
        self.assertEqual(result.fetched, 1)
        self.assertEqual(result.matched, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(source.last_cursor, "11")
        self.assertEqual(prop.owner_of_record, "GENESEE COUNTY LAND BANK")
        self.assertEqual(prop.forfeiture_status, "CFD")
        self.assertEqual(ParcelValueSnapshot.objects.get().forfeiture_status, "CFD")

    def test_context_scores_graphql_query_returns_neighbor_set(self):
        prop = Property.objects.create(
            address="100 Context St",
            parcel_id="41-00-000-001",
            latitude=43.01,
            longitude=-83.69,
            boundary_geojson={"type": "Polygon", "coordinates": []},
            owner_of_record="GCLBA",
            forfeiture_status="NCFD",
        )
        NeighborhoodContextScore.objects.create(
            property=prop,
            parcel_id=prop.parcel_id,
            neighborhood_def="knn8",
            signal="tax_distress",
            parcel_value=3,
            local_mean=1,
            local_std=1,
            z_score=2,
            moran_cluster="HL",
            moran_p=0.02,
            neighbor_parcel_ids=["41-00-000-002", "41-00-000-003"],
        )

        response = self.client.post(
            "/graphql",
            data=json.dumps(
                {
                    "query": """
                    query {
                      properties(limit: 1) {
                        parcelId
                        boundaryGeojson
                        ownerOfRecord
                        forfeitureStatus
                      }
                      contextScores(signal: "tax_distress", neighborhoodDef: "knn8") {
                        parcelId
                        zScore
                        moranCluster
                        moranP
                        neighborParcelIds
                      }
                    }
                    """
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        self.assertEqual(payload["data"]["properties"][0]["ownerOfRecord"], "GCLBA")
        score = payload["data"]["contextScores"][0]
        self.assertEqual(score["parcelId"], "41-00-000-001")
        self.assertEqual(score["moranCluster"], "HL")
        self.assertEqual(score["neighborParcelIds"], ["41-00-000-002", "41-00-000-003"])

    def test_compute_context_scores_writes_lisa_rows(self):
        for index, status in enumerate(["", "CFD", "NCFD", "NCFD"]):
            Property.objects.create(
                address=f"{index} Context Ave",
                parcel_id=f"41-00-000-00{index}",
                latitude=43.0 + index * 0.001,
                longitude=-83.7 + index * 0.001,
                forfeiture_status=status,
            )

        result = lisa.compute_and_store(
            signal="tax_distress",
            neighborhood_def="knn1",
            k=1,
            seed=7,
        )

        self.assertEqual(result["computed"], 4)
        self.assertEqual(NeighborhoodContextScore.objects.count(), 4)

    def test_composite_orients_distress_as_lower_performance(self):
        self.assertEqual(signals.SIGNAL_ORIENTATION["tax_distress"], -1.0)
        statuses = ["", "CFD", "NCFD", "NCFD"]
        for index, status in enumerate(statuses):
            Property.objects.create(
                address=f"{index} Composite Ave",
                parcel_id=f"41-00-100-00{index}",
                latitude=43.0 + index * 0.001,
                longitude=-83.7 + index * 0.001,
                forfeiture_status=status,
            )

        result = composite.compute_composite(
            neighborhood_def="knn1",
            k=1,
            weights={"tax_distress": 1.0},
            seed=7,
        )

        self.assertEqual(result["computed"], 4)
        no_distress = NeighborhoodContextScore.objects.get(parcel_id="41-00-100-000")
        high_distress = NeighborhoodContextScore.objects.get(parcel_id="41-00-100-002")
        self.assertGreater(no_distress.parcel_value, high_distress.parcel_value)

    def test_compute_context_scores_faceblock_groups_by_street(self):
        # Three parcels on the same street + one on a unique street. faceblock
        # parses the street name from Property.address, so same-street parcels
        # become neighbors and the unique-street parcel gets an empty set.
        rows = [
            ("100 Mason St", "41-00-000-010", "CFD", -83.700, 43.010),
            ("104 Mason St", "41-00-000-011", "NCFD", -83.701, 43.011),
            ("108 Mason St", "41-00-000-012", "", -83.702, 43.012),
            ("5 Solitary Ave", "41-00-000-013", "NCFD", -83.720, 43.030),
        ]
        for address, parcel_id, status, lon, lat in rows:
            Property.objects.create(
                address=address,
                parcel_id=parcel_id,
                latitude=lat,
                longitude=lon,
                forfeiture_status=status,
            )

        result = lisa.compute_and_store(
            signal="tax_distress",
            neighborhood_def="faceblock",
            k=8,
            seed=7,
        )

        self.assertEqual(result["computed"], 4)
        self.assertEqual(result["neighborhood_def"], "faceblock")
        solitary = NeighborhoodContextScore.objects.get(parcel_id="41-00-000-013")
        self.assertEqual(solitary.neighbor_parcel_ids, [])
        mason = NeighborhoodContextScore.objects.get(parcel_id="41-00-000-010")
        self.assertCountEqual(mason.neighbor_parcel_ids, ["41-00-000-011", "41-00-000-012"])

    def test_sync_county_parcels_dry_run_maps_live_shape_without_db_writes(self):
        out = StringIO()
        feature = {
            "attributes": {
                "OBJECTID": 1,
                "PARIDSHORT": "41-06-538-004",
                "OWNNAME": "GENESEE COUNTY LAND BANK",
                "Status": "NCFD",
                "StatusYr": "2025",
            },
            "geometry": {
                "rings": [
                    [
                        [-83.7, 43.0],
                        [-83.69, 43.0],
                        [-83.69, 43.01],
                        [-83.7, 43.01],
                        [-83.7, 43.0],
                    ]
                ]
            },
        }
        with patch("tracker.management.commands.sync_county_parcels.ArcGisClient") as fake_client:
            fake_client.return_value.iter_features.return_value = [feature]
            call_command("sync_county_parcels", "--dry-run", "--limit", "1", stdout=out)

        self.assertIn("41-06-538-004", out.getvalue())
        self.assertEqual(Property.objects.count(), 0)
