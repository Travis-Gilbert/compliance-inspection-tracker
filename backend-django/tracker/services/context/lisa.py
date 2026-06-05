"""
Local indicators of spatial association for the neighborhood-context layer.

local_stats is pure (values + libpysal W -> per-parcel stats) and testable on a
synthetic fixture. compute_and_store reads parcels, builds weights, runs the
stats, and upserts NeighborhoodContextScore rows.
"""

from __future__ import annotations

# esda Moran_Local quadrant codes -> cluster label.
CLUSTER_BY_QUADRANT = {1: "HH", 2: "LH", 3: "LL", 4: "HL"}


def local_stats(values, weights, *, significance: float = 0.05, permutations: int = 999, seed: int | None = None):
    """Per-parcel local context stats, aligned with `values` order.

    Each item: parcel_value, local_mean, local_std, z_score (local), spatial_lag,
    moran_cluster (HH/LH/LL/HL/NS), moran_p, gi_star, neighbor_positions.
    The local z-score is over the neighbor set (interpretable "sigmas above the
    block"); the cluster is esda's Moran quadrant gated by the pseudo p-value.
    """
    import numpy as np
    from esda.moran import Moran_Local

    try:
        from esda.getisord import G_Local
    except Exception:  # pragma: no cover - optional
        G_Local = None

    values = np.asarray(values, dtype=float)
    n = len(values)
    neighbors = weights.neighbors

    constant = bool(np.allclose(values, values[0])) if n else True
    moran = None
    gi = None
    if not constant and n >= 3:
        if seed is not None:
            np.random.seed(seed)
        moran = Moran_Local(values, weights, permutations=permutations)
        if G_Local is not None:
            try:
                if seed is not None:
                    np.random.seed(seed)
                gi = G_Local(values, weights, star=True, permutations=permutations)
            except Exception:  # pragma: no cover - G_Local can be picky on some W
                gi = None

    out = []
    for pos in range(n):
        nbr = np.asarray(neighbors.get(pos, []), dtype=int)
        nbr_vals = values[nbr] if nbr.size else np.asarray([], dtype=float)
        local_mean = float(nbr_vals.mean()) if nbr_vals.size else None
        local_std = float(nbr_vals.std(ddof=0)) if nbr_vals.size else None
        z = None
        if local_mean is not None and local_std:
            z = float((values[pos] - local_mean) / local_std)
        if moran is not None:
            p = float(moran.p_sim[pos])
            cluster = CLUSTER_BY_QUADRANT.get(int(moran.q[pos]), "NS") if p <= significance else "NS"
        else:
            p = None
            cluster = "NS"
        out.append(
            {
                "parcel_value": float(values[pos]),
                "local_mean": local_mean,
                "local_std": local_std,
                "z_score": z,
                "spatial_lag": local_mean,  # row-standardized lag == neighbor mean
                "moran_cluster": cluster,
                "moran_p": p,
                "gi_star": float(gi.Zs[pos]) if gi is not None else None,
                "neighbor_positions": [int(x) for x in nbr.tolist()],
            }
        )
    return out


def compute_and_store(
    *,
    neighborhood_def: str = "knn8",
    signal: str = "tax_distress",
    parcel_ids=None,
    k: int = 8,
    significance: float = 0.05,
    seed: int | None = None,
):
    from django.utils import timezone

    from tracker.models import NeighborhoodContextScore, Property

    from . import signals as signals_mod
    from .weights import build_weights

    today = timezone.now().date()
    qs = Property.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    if parcel_ids:
        qs = qs.filter(parcel_id__in=list(parcel_ids))
    parcels = list(qs)
    ids, coords, values = signals_mod.collect(parcels, signal, today=today)
    if len(ids) < 3:
        return {"computed": 0, "reason": "need >=3 parcels with this signal", "available": len(ids)}

    geojson = None
    if neighborhood_def in ("queen", "rook"):
        by_id = {p.parcel_id: p for p in parcels}
        geojson = [getattr(by_id.get(pid), "boundary_geojson", None) for pid in ids]
    weights = build_weights(coords, definition=neighborhood_def, geojson=geojson, k=k)
    stats = local_stats(values, weights, significance=significance, seed=seed)

    prop_by_id = {p.parcel_id: p for p in parcels}
    written = 0
    for pos, pid in enumerate(ids):
        row = dict(stats[pos])
        neighbor_ids = [ids[j] for j in row.pop("neighbor_positions", [])]
        NeighborhoodContextScore.objects.update_or_create(
            parcel_id=pid,
            neighborhood_def=neighborhood_def,
            signal=signal,
            defaults={"property": prop_by_id.get(pid), "neighbor_parcel_ids": neighbor_ids, **row},
        )
        written += 1
    return {"computed": written, "signal": signal, "neighborhood_def": neighborhood_def, "parcels": len(ids)}
