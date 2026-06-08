"""
Spatial weights for the neighborhood-context layer (libpysal).

Four neighborhood definitions, matching SPEC-NEIGHBORHOOD-CONTEXT-VIZ line 49:

  faceblock  org-facing default. Block-face proxy: parcels sharing the same
             normalized primary street name, restricted to the nearest K by
             haversine distance among same-street parcels. The open County feed
             lacks block-face/side-of-street geometry, so same-street + nearest-K
             is the honest proxy for "this block".
  knn / knn{N}  k-nearest neighbors on centroids (analyst default). Needs only
                a coords array.
  queen / rook  contiguity from polygon geometry (Property.boundary_geojson),
                via geopandas + shapely.
  blockgroup  real Census block-group membership: each parcel is assigned a
              block-group GEOID by point-in-polygon against Genesee County, MI
              block-group polygons fetched from the Census TIGERweb REST service.

The County feed is ~232 scattered tax-reverted parcels, so neighbor sets are
often small or empty under every definition; that is correct, not a bug. A
parcel with no peer gets an empty neighbor list (LISA degrades it to NS). We
never fabricate neighbors or block-group membership.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time

DEFAULT_K = 8

# Genesee County, Michigan: state FIPS 26, county FIPS 049.
GENESEE_STATE_FIPS = "26"
GENESEE_COUNTY_FIPS = "049"

# Census TIGERweb ArcGIS REST: "Census Block Groups" is layer 10 of the current
# tigerWMS_Current MapServer (Census Tracts=8, Census Block Groups=10, verified
# 2026-06-08 against the live /layers metadata). Pulled once per county and
# cached so repeated runs do not refetch.
TIGERWEB_BLOCK_GROUPS_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "tigerWMS_Current/MapServer/10/query"
)
_BLOCK_GROUP_CACHE_TTL_SECONDS = 30 * 24 * 3600  # block-group geometry is ~decadal

# Module-level cache (process lifetime) keyed by (state_fips, county_fips).
_BLOCK_GROUP_GEOJSON_CACHE: dict[tuple[str, str], dict] = {}


def _knn_k(definition: str, default: int) -> int:
    suffix = definition[3:]
    return int(suffix) if suffix.isdigit() else default


def build_weights(
    coords,
    *,
    definition: str = "knn8",
    geojson=None,
    street_names=None,
    k: int = DEFAULT_K,
    state_fips: str = GENESEE_STATE_FIPS,
    county_fips: str = GENESEE_COUNTY_FIPS,
):
    """Build a row-standardized libpysal W for the neighborhood definition.

    coords: Nx2 array of (lon, lat), aligned with street_names/geojson.
    faceblock: same normalized street name + nearest-K (needs street_names).
    knn / knn{N}: k-nearest neighbors from coords. Analyst default.
    queen / rook: contiguity from polygon geometry (needs geopandas + shapely).
    blockgroup: same Census block-group GEOID (point-in-polygon, real polygons).
    """
    if definition.startswith("knn"):
        kk = _knn_k(definition, k)
        try:
            from libpysal.weights import KNN
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("libpysal is required for KNN weights") from exc
        weights = KNN.from_array(coords, k=kk)
        weights.transform = "r"
        return weights
    if definition == "faceblock":
        weights = _faceblock_weights(coords, street_names, k=k)
        weights.transform = "r"
        return weights
    if definition == "blockgroup":
        weights = _blockgroup_weights(coords, state_fips=state_fips, county_fips=county_fips)
        weights.transform = "r"
        return weights
    if definition in ("queen", "rook"):
        weights = _contiguity_weights(geojson, definition)
        weights.transform = "r"
        return weights
    raise ValueError(f"unsupported neighborhood_def: {definition!r}")


# --- faceblock (block-face proxy) -------------------------------------------

_HOUSE_NUMBER_RE = re.compile(r"^\s*\d+[A-Za-z]?\s+")
_LEADING_DIR_RE = re.compile(r"^(?:[NSEW]|NE|NW|SE|SW)\s+", re.IGNORECASE)
_TRAILING_CITY_STATE_ZIP_RE = re.compile(
    r"\s+(?:flint|burton|davison|fenton|flushing|grand\s+blanc|mt\.?\s+morris|"
    r"mount\s+morris|swartz\s+creek|clio|linden|mi|michigan)\b.*$",
    re.IGNORECASE,
)


def normalize_street_name(address: str | None) -> str:
    """Normalized primary street name from a full address string.

    Strips the leading house number and any directional prefix, drops trailing
    city / state / zip, then applies the shared suffix normalization. Returns a
    lowercase key (e.g. "307 E Mason St Flint 48503" -> "mason st"). Empty string
    when no street can be recovered (parcel ends up with no same-street peer).
    """
    if not address:
        return ""
    from tracker.utils.address import normalize_address

    text = normalize_address(str(address))
    # Drop a comma-delimited tail (", Flint, MI 48503") before anything else, so
    # the formatted_address form collapses to the same key as the bare form.
    text = text.split(",", 1)[0]
    text = _TRAILING_CITY_STATE_ZIP_RE.sub("", text)
    text = _HOUSE_NUMBER_RE.sub("", text)
    text = _LEADING_DIR_RE.sub("", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _faceblock_weights(coords, street_names, *, k: int = DEFAULT_K):
    """W where neighbors share the same normalized street name, nearest-K by
    haversine. Parcels with no same-street peer get an empty neighbor list."""
    import numpy as np
    from libpysal.weights import W

    coords = np.asarray(coords, dtype=float)
    n = len(coords)
    if street_names is None:
        raise ValueError("faceblock weights require street_names aligned with coords")
    if len(street_names) != n:
        raise ValueError("street_names length must match coords length")

    keys = [normalize_street_name(s) for s in street_names]
    same_street: dict[str, list[int]] = {}
    for idx, key in enumerate(keys):
        if key:
            same_street.setdefault(key, []).append(idx)

    neighbors: dict[int, list[int]] = {}
    for pos in range(n):
        key = keys[pos]
        peers = [j for j in same_street.get(key, []) if j != pos] if key else []
        if not peers:
            neighbors[pos] = []
            continue
        lon, lat = float(coords[pos][0]), float(coords[pos][1])
        peers.sort(key=lambda j: _haversine_m(lon, lat, float(coords[j][0]), float(coords[j][1])))
        neighbors[pos] = peers[: max(1, k)]

    return W(neighbors, silence_warnings=True)


# --- blockgroup (real Census block-group membership) ------------------------

def _block_group_cache_path(state_fips: str, county_fips: str) -> str:
    name = f"tigerweb_blockgroups_{state_fips}_{county_fips}.json"
    return os.path.join(tempfile.gettempdir(), name)


def fetch_block_group_geojson(*, state_fips: str, county_fips: str, force: bool = False) -> dict:
    """Genesee County block-group polygons as a GeoJSON FeatureCollection.

    Cached at module level and on disk under the temp dir so repeated runs do not
    refetch. Raises RuntimeError (naming the dependency) when the fetch fails so
    the caller can skip the blockgroup def rather than fabricate membership.
    """
    cache_key = (state_fips, county_fips)
    if not force and cache_key in _BLOCK_GROUP_GEOJSON_CACHE:
        return _BLOCK_GROUP_GEOJSON_CACHE[cache_key]

    disk_path = _block_group_cache_path(state_fips, county_fips)
    if not force and os.path.exists(disk_path):
        age = time.time() - os.path.getmtime(disk_path)
        if age < _BLOCK_GROUP_CACHE_TTL_SECONDS:
            try:
                with open(disk_path, encoding="utf-8") as handle:
                    data = json.load(handle)
                _BLOCK_GROUP_GEOJSON_CACHE[cache_key] = data
                return data
            except (OSError, ValueError):
                pass  # corrupt cache -> refetch

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("httpx is required to fetch Census block-group polygons") from exc

    params = {
        "where": f"STATE='{state_fips}' AND COUNTY='{county_fips}'",
        "outFields": "GEOID,STATE,COUNTY,TRACT,BLKGRP",
        "outSR": "4326",
        "f": "geojson",
        "returnGeometry": "true",
    }
    try:
        response = httpx.get(TIGERWEB_BLOCK_GROUPS_URL, params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # network / HTTP / decode
        raise RuntimeError(
            "could not fetch Census block-group polygons from TIGERweb "
            f"({TIGERWEB_BLOCK_GROUPS_URL}); network required"
        ) from exc

    features = data.get("features") if isinstance(data, dict) else None
    if not features:
        raise RuntimeError(
            "Census TIGERweb returned no block-group features for "
            f"state={state_fips} county={county_fips}"
        )

    _BLOCK_GROUP_GEOJSON_CACHE[cache_key] = data
    try:
        with open(disk_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
    except OSError:  # pragma: no cover - cache write is best-effort
        pass
    return data


def _geoid_of(feature: dict) -> str:
    props = feature.get("properties") or {}
    geoid = props.get("GEOID")
    if geoid:
        return str(geoid)
    parts = [props.get("STATE"), props.get("COUNTY"), props.get("TRACT"), props.get("BLKGRP")]
    return "".join(str(p) for p in parts if p is not None)


def assign_block_groups(coords, *, state_fips: str, county_fips: str) -> list[str | None]:
    """Per-parcel block-group GEOID by point-in-polygon. None when outside every
    fetched block group."""
    from shapely.geometry import Point, shape
    from shapely.prepared import prep

    data = fetch_block_group_geojson(state_fips=state_fips, county_fips=county_fips)
    prepared = []
    for feature in data.get("features", []):
        geom = feature.get("geometry")
        if not geom:
            continue
        try:
            polygon = shape(geom)
        except (ValueError, AttributeError):  # pragma: no cover - malformed geometry
            continue
        prepared.append((_geoid_of(feature), prep(polygon)))

    assignments: list[str | None] = []
    for lon, lat in coords:
        point = Point(float(lon), float(lat))
        found = None
        for geoid, polygon in prepared:
            if polygon.covers(point):
                found = geoid
                break
        assignments.append(found)
    return assignments


def _blockgroup_weights(coords, *, state_fips: str, county_fips: str):
    """W where parcels sharing a Census block-group GEOID are neighbors. Parcels
    outside every fetched block group get an empty neighbor list."""
    import numpy as np
    from libpysal.weights import W

    coords = np.asarray(coords, dtype=float)
    n = len(coords)
    geoids = assign_block_groups(coords, state_fips=state_fips, county_fips=county_fips)

    by_geoid: dict[str, list[int]] = {}
    for idx, geoid in enumerate(geoids):
        if geoid:
            by_geoid.setdefault(geoid, []).append(idx)

    neighbors: dict[int, list[int]] = {}
    for pos in range(n):
        geoid = geoids[pos]
        peers = [j for j in by_geoid.get(geoid, []) if j != pos] if geoid else []
        neighbors[pos] = peers
    return W(neighbors, silence_warnings=True)


# --- queen / rook contiguity ------------------------------------------------

def _contiguity_weights(geojson_list, kind: str):
    if not geojson_list:
        raise ValueError(f"{kind} contiguity needs polygon geometry (boundary_geojson)")
    try:
        import geopandas as gpd
        from libpysal.weights import Queen, Rook
        from shapely.geometry import shape
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("geopandas + shapely required for contiguity weights") from exc
    geoms = [shape(geo) for geo in geojson_list]
    gdf = gpd.GeoDataFrame(geometry=geoms)
    builder = Queen if kind == "queen" else Rook
    return builder.from_dataframe(gdf, use_index=False)
