import math
from datetime import date, datetime
from typing import Optional

from app.models.property import RESOLVED_FINDINGS


PROGRAM_PRIORITY_WEIGHT = {
    "Featured Homes": 16.0,
    "Ready for Rehab": 14.0,
    "VIP Spotlight": 10.0,
    "Demolition": 4.0,
}

DETECTION_PRIORITY_WEIGHT = {
    "likely_demolished": 28.0,
    "likely_vacant": 22.0,
    "likely_occupied": 6.0,
    "no_streetview": 9.0,
    "unprocessed": 10.0,
}


def parse_closing_date(value: str) -> Optional[date]:
    if not value:
        return None
    clean = value.strip()
    if not clean:
        return None

    formats = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%Y-%m",
        "%m/%Y",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(clean, fmt)
            if fmt in ("%Y-%m", "%m/%Y"):
                return date(parsed.year, parsed.month, 1)
            return parsed.date()
        except ValueError:
            continue

    # Best effort for ISO-like prefixes.
    if len(clean) >= 7 and clean[4] == "-":
        try:
            return date(int(clean[0:4]), int(clean[5:7]), 1)
        except ValueError:
            return None
    return None


def closing_age_days(closing_date: str, as_of: Optional[date] = None) -> Optional[int]:
    parsed = parse_closing_date(closing_date)
    if not parsed:
        return None
    today = as_of or date.today()
    return max(0, (today - parsed).days)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_miles = 3958.8
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_miles * c


def has_contact_attempt(prop: dict) -> bool:
    return bool(prop.get("compliance_1st_attempt") or prop.get("compliance_2nd_attempt"))


def compute_priority_score(prop: dict, as_of: Optional[date] = None) -> tuple[float, dict]:
    finding = (prop.get("finding") or "").strip()
    detection_label = (prop.get("detection_label") or "unprocessed").strip()
    detection_score = prop.get("detection_score")
    detection_score = float(detection_score) if detection_score not in (None, "") else 0.0
    detection_score = max(0.0, min(detection_score, 1.0))
    program = (prop.get("program") or "").strip()

    first_attempt = bool((prop.get("compliance_1st_attempt") or "").strip())
    second_attempt = bool((prop.get("compliance_2nd_attempt") or "").strip())

    components: dict[str, float] = {}
    score = 0.0

    if finding == "inconclusive":
        components["finding"] = 24.0
    elif not finding:
        components["finding"] = 18.0
    elif finding in {f.value for f in RESOLVED_FINDINGS}:
        components["finding"] = -18.0
    else:
        components["finding"] = 8.0
    score += components["finding"]

    components["detection_label"] = DETECTION_PRIORITY_WEIGHT.get(detection_label, 10.0)
    components["detection_score"] = detection_score * 20.0
    score += components["detection_label"] + components["detection_score"]

    components["program"] = PROGRAM_PRIORITY_WEIGHT.get(program, 8.0)
    score += components["program"]

    if not first_attempt and not second_attempt:
        components["compliance_attempts"] = 14.0
    elif first_attempt and not second_attempt:
        components["compliance_attempts"] = 9.0
    else:
        components["compliance_attempts"] = 4.0
    score += components["compliance_attempts"]

    age_days = closing_age_days(prop.get("closing_date", ""), as_of=as_of)
    if age_days is None:
        components["closing_age"] = 4.0
    else:
        components["closing_age"] = min(12.0, (age_days / 365.0) * 8.0)
    score += components["closing_age"]

    if not prop.get("streetview_available") and not prop.get("satellite_path"):
        components["imagery"] = 5.0
        score += components["imagery"]
    else:
        components["imagery"] = 0.0

    score = round(max(0.0, min(100.0, score)), 2)
    if score >= 70:
        level = "high"
    elif score >= 45:
        level = "medium"
    else:
        level = "low"

    components["level"] = level
    if age_days is not None:
        components["closing_age_days"] = float(age_days)
    return score, components


def apply_priority_scores(properties: list[dict], as_of: Optional[date] = None) -> list[dict]:
    enriched = []
    for prop in properties:
        score, components = compute_priority_score(prop, as_of=as_of)
        record = dict(prop)
        record["priority_score"] = score
        record["priority_level"] = components["level"]
        record["has_contact_attempt"] = has_contact_attempt(prop)
        if "closing_age_days" in components:
            record["closing_age_days"] = int(components["closing_age_days"])
        else:
            record["closing_age_days"] = None
        record["priority_components"] = components
        enriched.append(record)
    return enriched


def filter_by_contact(properties: list[dict], contact: str) -> list[dict]:
    if contact == "contacted":
        return [prop for prop in properties if prop.get("has_contact_attempt")]
    if contact == "no_contact":
        return [prop for prop in properties if not prop.get("has_contact_attempt")]
    return properties


def summarize_buyers(properties: list[dict]) -> list[dict]:
    buyer_map: dict[str, dict] = {}
    for prop in properties:
        buyer_name = (prop.get("buyer_name") or "").strip()
        organization = (prop.get("organization") or "").strip()
        key = buyer_name or organization or "Unknown"
        if key not in buyer_map:
            buyer_map[key] = {
                "buyer": key,
                "organization": organization if organization and organization != key else "",
                "property_count": 0,
                "geocoded_count": 0,
                "reviewed_count": 0,
                "unreviewed_count": 0,
                "high_priority_count": 0,
                "average_priority_score": 0.0,
                "programs": {},
            }

        row = buyer_map[key]
        row["property_count"] += 1
        if prop.get("latitude") is not None and prop.get("longitude") is not None:
            row["geocoded_count"] += 1
        if prop.get("finding"):
            row["reviewed_count"] += 1
        else:
            row["unreviewed_count"] += 1
        if prop.get("priority_level") == "high":
            row["high_priority_count"] += 1
        row["average_priority_score"] += float(prop.get("priority_score") or 0.0)

        program = (prop.get("program") or "Unknown").strip() or "Unknown"
        row["programs"][program] = row["programs"].get(program, 0) + 1

    summary = []
    for buyer in buyer_map.values():
        if buyer["property_count"]:
            buyer["average_priority_score"] = round(
                buyer["average_priority_score"] / buyer["property_count"],
                2,
            )
        buyer["programs"] = dict(sorted(buyer["programs"].items(), key=lambda item: (-item[1], item[0])))
        summary.append(buyer)

    summary.sort(
        key=lambda row: (
            -row["high_priority_count"],
            -row["property_count"],
            -row["average_priority_score"],
            row["buyer"],
        )
    )
    return summary


def haversine_clusters(
    properties: list[dict],
    radius_miles: float = 0.35,
    min_points: int = 2,
) -> list[dict]:
    geocoded = [
        prop for prop in properties
        if prop.get("latitude") is not None and prop.get("longitude") is not None
    ]
    if not geocoded:
        return []

    indexed = {prop["id"]: prop for prop in geocoded}
    adjacency: dict[int, set[int]] = {prop["id"]: set() for prop in geocoded}

    for i, left in enumerate(geocoded):
        for right in geocoded[i + 1:]:
            dist = haversine_miles(
                float(left["latitude"]),
                float(left["longitude"]),
                float(right["latitude"]),
                float(right["longitude"]),
            )
            if dist <= radius_miles:
                adjacency[left["id"]].add(right["id"])
                adjacency[right["id"]].add(left["id"])

    visited: set[int] = set()
    clusters: list[dict] = []
    cluster_index = 0

    for prop in geocoded:
        start_id = prop["id"]
        if start_id in visited:
            continue

        stack = [start_id]
        component: list[int] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    stack.append(neighbor)

        if len(component) < min_points:
            continue

        cluster_props = [indexed[prop_id] for prop_id in component]
        latitudes = [float(p["latitude"]) for p in cluster_props]
        longitudes = [float(p["longitude"]) for p in cluster_props]
        cluster_index += 1

        clusters.append(
            {
                "cluster_id": f"cluster-{cluster_index}",
                "property_count": len(cluster_props),
                "centroid": {
                    "latitude": round(sum(latitudes) / len(latitudes), 6),
                    "longitude": round(sum(longitudes) / len(longitudes), 6),
                },
                "bounds": {
                    "min_latitude": min(latitudes),
                    "max_latitude": max(latitudes),
                    "min_longitude": min(longitudes),
                    "max_longitude": max(longitudes),
                },
                "average_priority_score": round(
                    sum(float(p.get("priority_score", 0.0)) for p in cluster_props) / len(cluster_props),
                    2,
                ),
                "properties": sorted(
                    [
                        {
                            "id": p["id"],
                            "address": p.get("address", ""),
                            "program": p.get("program", ""),
                            "priority_score": p.get("priority_score", 0.0),
                            "priority_level": p.get("priority_level", "low"),
                            "latitude": p.get("latitude"),
                            "longitude": p.get("longitude"),
                        }
                        for p in cluster_props
                    ],
                    key=lambda item: (-float(item["priority_score"]), item["address"]),
                ),
            }
        )

    clusters.sort(
        key=lambda item: (
            -item["property_count"],
            -item["average_priority_score"],
            item["cluster_id"],
        )
    )
    return clusters
