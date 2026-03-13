import unittest
from datetime import date

from app.services.enrichment import (
    apply_priority_scores,
    closing_age_days,
    haversine_clusters,
    haversine_miles,
    parse_closing_date,
)


class TestEnrichmentMath(unittest.TestCase):
    def test_parse_and_age_calculation(self):
        parsed = parse_closing_date("03/15/2024")
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 3)
        self.assertEqual(parsed.day, 15)

        age = closing_age_days("2024-03-15", as_of=date(2026, 3, 13))
        self.assertEqual(age, (date(2026, 3, 13) - date(2024, 3, 15)).days)

    def test_haversine_distance(self):
        self.assertAlmostEqual(haversine_miles(43.0, -83.7, 43.0, -83.7), 0.0, places=6)
        distance = haversine_miles(43.0, -83.7, 43.01, -83.7)
        self.assertGreater(distance, 0.65)
        self.assertLess(distance, 0.75)

    def test_priority_scoring_and_clustering(self):
        sample = [
            {
                "id": 1,
                "address": "A",
                "program": "Featured Homes",
                "closing_date": "2023-01-01",
                "detection_label": "likely_demolished",
                "detection_score": 0.9,
                "finding": "",
                "streetview_available": False,
                "satellite_path": "",
                "latitude": 43.0,
                "longitude": -83.7,
                "compliance_1st_attempt": "",
                "compliance_2nd_attempt": "",
            },
            {
                "id": 2,
                "address": "B",
                "program": "Ready for Rehab",
                "closing_date": "2025-01-01",
                "detection_label": "likely_occupied",
                "detection_score": 0.2,
                "finding": "occupied_maintained",
                "streetview_available": True,
                "satellite_path": "/tmp/sat.jpg",
                "latitude": 43.0005,
                "longitude": -83.7004,
                "compliance_1st_attempt": "2025-11-01",
                "compliance_2nd_attempt": "",
            },
            {
                "id": 3,
                "address": "C",
                "program": "Featured Homes",
                "closing_date": "2023-01-01",
                "detection_label": "likely_vacant",
                "detection_score": 0.7,
                "finding": "",
                "streetview_available": True,
                "satellite_path": "",
                "latitude": 43.0007,
                "longitude": -83.7006,
                "compliance_1st_attempt": "",
                "compliance_2nd_attempt": "",
            },
        ]

        enriched = apply_priority_scores(sample, as_of=date(2026, 3, 13))
        high = next(row for row in enriched if row["id"] == 1)
        low = next(row for row in enriched if row["id"] == 2)
        self.assertGreater(high["priority_score"], low["priority_score"])
        self.assertIn(high["priority_level"], {"high", "medium"})

        clusters = haversine_clusters(enriched, radius_miles=0.1, min_points=2)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["property_count"], 3)


if __name__ == "__main__":
    unittest.main()
