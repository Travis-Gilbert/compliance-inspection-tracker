"""
Spatial weights for the neighborhood-context layer (libpysal).

KNN-on-centroids is the default and the only definition sourceable today (needs
only libpysal + a coords array). Queen/Rook contiguity need polygon geometry
(Property.boundary_geojson) and geopandas + shapely.
"""

from __future__ import annotations

DEFAULT_K = 8


def _knn_k(definition: str, default: int) -> int:
    suffix = definition[3:]
    return int(suffix) if suffix.isdigit() else default


def build_weights(coords, *, definition: str = "knn8", geojson=None, k: int = DEFAULT_K):
    """Build a row-standardized libpysal W for the neighborhood definition.

    knn / knn{N}: k-nearest neighbors from coords (lon/lat). Default.
    queen / rook: contiguity from polygon geometry (needs geopandas + shapely).
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
    if definition in ("queen", "rook"):
        weights = _contiguity_weights(geojson, definition)
        weights.transform = "r"
        return weights
    raise ValueError(f"unsupported neighborhood_def: {definition!r}")


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
