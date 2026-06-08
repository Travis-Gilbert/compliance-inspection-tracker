"""
Weighted composite index across signals for the neighborhood-context layer.

Blends per-parcel signal values into one composite, reweighting to the signals
each parcel actually has (no imputation, per spec), then runs the same LISA on
the composite so it carries its own cluster classification.
"""

from __future__ import annotations

DEFAULT_WEIGHTS = {"tax_distress": 0.5, "sale_recency": 0.2, "compliance": 0.3}


def compute_composite(
    *,
    neighborhood_def: str = "knn8",
    parcel_ids=None,
    k: int = 8,
    weights=None,
    significance: float = 0.05,
    seed: int | None = None,
):
    import numpy as np
    from django.utils import timezone

    from tracker.models import NeighborhoodContextScore, Property

    from . import signals as signals_mod
    from .lisa import local_stats
    from .weights import build_weights

    blend = weights or DEFAULT_WEIGHTS
    today = timezone.now().date()
    qs = Property.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    if parcel_ids:
        qs = qs.filter(parcel_id__in=list(parcel_ids))

    ids: list[str] = []
    coords: list[tuple[float, float]] = []
    values: list[float] = []
    prop_by_id: dict = {}
    for prop in qs:
        if prop.latitude is None or prop.longitude is None:
            continue
        num = wsum = 0.0
        for sig, weight in blend.items():
            value = signals_mod.signal_value(sig, prop, today=today)
            if value is None:
                continue
            num += weight * value
            wsum += weight
        if wsum == 0:
            continue
        ids.append(prop.parcel_id)
        coords.append((float(prop.longitude), float(prop.latitude)))
        values.append(num / wsum)
        prop_by_id[prop.parcel_id] = prop

    if len(ids) < 3:
        return {"computed": 0, "reason": "need >=3 parcels with >=1 signal", "available": len(ids)}

    geojson = None
    if neighborhood_def in ("queen", "rook"):
        geojson = [getattr(prop_by_id.get(pid), "boundary_geojson", None) for pid in ids]
    street_names = None
    if neighborhood_def == "faceblock":
        street_names = [getattr(prop_by_id.get(pid), "address", "") for pid in ids]
    weights_obj = build_weights(
        np.asarray(coords, dtype=float),
        definition=neighborhood_def,
        geojson=geojson,
        street_names=street_names,
        k=k,
    )
    stats = local_stats(np.asarray(values, dtype=float), weights_obj, significance=significance, seed=seed)
    written = 0
    for pos, pid in enumerate(ids):
        row = dict(stats[pos])
        neighbor_ids = [ids[j] for j in row.pop("neighbor_positions", [])]
        NeighborhoodContextScore.objects.update_or_create(
            parcel_id=pid,
            neighborhood_def=neighborhood_def,
            signal="composite",
            defaults={"property": prop_by_id.get(pid), "neighbor_parcel_ids": neighbor_ids, **row},
        )
        written += 1
    return {"computed": written, "signal": "composite", "neighborhood_def": neighborhood_def, "parcels": len(ids)}
