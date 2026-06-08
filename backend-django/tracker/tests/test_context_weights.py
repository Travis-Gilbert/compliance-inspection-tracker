"""
Pure synthetic-fixture tests for the neighborhood-definition weight builders.

No network and no DB: every test feeds a coords array (and street names or a
mocked block-group polygon set) straight into build_weights / local_stats. The
Census fetch is monkeypatched so the blockgroup builder never touches TIGERweb.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase

from tracker.services.context import weights as weights_mod
from tracker.services.context.lisa import local_stats
from tracker.services.context.weights import build_weights, normalize_street_name


def _square(min_lon, min_lat, max_lon, max_lat):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]
        ],
    }


def _mock_block_groups():
    """Two adjacent block-group squares around west Flint coordinates."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"GEOID": "260490001001"},
                "geometry": _square(-83.71, 43.00, -83.70, 43.01),
            },
            {
                "type": "Feature",
                "properties": {"GEOID": "260490001002"},
                "geometry": _square(-83.70, 43.00, -83.69, 43.01),
            },
        ],
    }


class FaceblockWeightsTests(SimpleTestCase):
    def test_groups_same_street_and_isolates_unique_street(self):
        coords = np.array(
            [
                [-83.690, 43.010],
                [-83.691, 43.011],
                [-83.692, 43.012],
                [-83.700, 43.020],
            ],
            dtype=float,
        )
        streets = ["307 E Mason St", "311 E Mason St", "315 E Mason St", "5 Unique Ave"]

        w = build_weights(coords, definition="faceblock", street_names=streets, k=8)

        self.assertEqual(w.transform, "R")
        self.assertCountEqual(w.neighbors[0], [1, 2])
        self.assertCountEqual(w.neighbors[1], [0, 2])
        self.assertCountEqual(w.neighbors[2], [0, 1])
        self.assertEqual(w.neighbors[3], [])

    def test_nearest_k_caps_same_street_neighbors(self):
        coords = np.array([[-83.70 + i * 0.001, 43.01] for i in range(6)], dtype=float)
        streets = [f"{100 + i} Maple St" for i in range(6)]

        w = build_weights(coords, definition="faceblock", street_names=streets, k=2)

        for pos in range(6):
            self.assertEqual(len(w.neighbors[pos]), 2)
        # Position 0's two nearest same-street peers are 1 and 2.
        self.assertCountEqual(w.neighbors[0], [1, 2])

    def test_requires_street_names(self):
        coords = np.array([[-83.69, 43.01], [-83.70, 43.02]], dtype=float)
        with self.assertRaises(ValueError):
            build_weights(coords, definition="faceblock")

    def test_street_normalizer_collapses_forms(self):
        self.assertEqual(normalize_street_name("307 E MASON ST FLINT 48503"), "mason st")
        self.assertEqual(normalize_street_name("1502 N Saginaw St, Flint, MI"), "saginaw st")
        self.assertEqual(normalize_street_name("1600 Saginaw Street"), "saginaw st")
        self.assertEqual(normalize_street_name(""), "")
        self.assertEqual(normalize_street_name(None), "")

    def test_high_on_low_block_outlier_classifies_hl(self):
        streets: list[str] = []
        values: list[float] = []
        coords: list[tuple[float, float]] = []
        # "Low St": seven low parcels plus one planted high outlier (position 7).
        for i in range(7):
            streets.append(f"{100 + i * 2} Low St")
            values.append(0.0)
            coords.append((-83.70 + i * 0.0005, 43.010))
        streets.append("200 Low St")
        values.append(5.0)
        coords.append((-83.70 + 7 * 0.0005, 43.010))
        # A second block widens the global distribution so Moran has spread.
        for i in range(6):
            streets.append(f"{300 + i * 2} Other St")
            values.append(2.0)
            coords.append((-83.69 + i * 0.0005, 43.020))

        w = build_weights(
            np.asarray(coords, dtype=float),
            definition="faceblock",
            street_names=streets,
            k=8,
        )
        stats = local_stats(np.asarray(values, dtype=float), w, significance=0.05, seed=42)

        outlier = stats[7]
        self.assertEqual(outlier["parcel_value"], 5.0)
        self.assertEqual(outlier["local_mean"], 0.0)
        self.assertEqual(outlier["moran_cluster"], "HL")
        self.assertLessEqual(outlier["moran_p"], 0.05)


class BlockGroupWeightsTests(SimpleTestCase):
    def test_assigns_parcels_to_groups_and_builds_same_group_w(self):
        # 0,1 inside group ...001; 2,3 inside group ...002; 4 outside both.
        coords = np.array(
            [
                [-83.705, 43.005],
                [-83.704, 43.006],
                [-83.695, 43.005],
                [-83.694, 43.006],
                [-83.600, 43.500],
            ],
            dtype=float,
        )

        with patch.object(weights_mod, "fetch_block_group_geojson", return_value=_mock_block_groups()):
            w = build_weights(coords, definition="blockgroup")

        self.assertEqual(w.transform, "R")
        self.assertCountEqual(w.neighbors[0], [1])
        self.assertCountEqual(w.neighbors[1], [0])
        self.assertCountEqual(w.neighbors[2], [3])
        self.assertCountEqual(w.neighbors[3], [2])
        self.assertEqual(w.neighbors[4], [])

    def test_assign_block_groups_returns_geoid_or_none(self):
        coords = np.array([[-83.705, 43.005], [-83.600, 43.500]], dtype=float)

        with patch.object(weights_mod, "fetch_block_group_geojson", return_value=_mock_block_groups()):
            geoids = weights_mod.assign_block_groups(coords, state_fips="26", county_fips="049")

        self.assertEqual(geoids[0], "260490001001")
        self.assertIsNone(geoids[1])

    def test_fetch_failure_raises_runtime_error(self):
        weights_mod._BLOCK_GROUP_GEOJSON_CACHE.clear()
        coords = np.array([[-83.705, 43.005], [-83.704, 43.006]], dtype=float)

        with patch.object(
            weights_mod,
            "fetch_block_group_geojson",
            side_effect=RuntimeError("network required"),
        ):
            with self.assertRaises(RuntimeError):
                build_weights(coords, definition="blockgroup")
