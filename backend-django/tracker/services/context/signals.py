"""
Condition signals for the neighborhood-context layer.

Each signal reduces a Property to a single numeric that LISA then scores against
its local neighborhood. `signal_value` is a pure mapper (testable without a DB);
`collect` reads the DB and returns aligned arrays for the parcels that have a
location and a non-null value for the chosen signal.

The County ArcGIS open data carries no per-parcel assessed/taxable value, so the
populated first-class signals are tax_distress (from forfeiture_status), sale
recency (closing_date), and compliance status. assessed_value / value_trajectory
are defined but yield None until a value source exists.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

SIGNAL_KEYS = ("tax_distress", "sale_recency", "compliance", "assessed_value", "value_trajectory")

# +1 means higher is healthier; -1 means higher is worse.
SIGNAL_ORIENTATION = {
    "assessed_value": 1.0,
    "value_trajectory": 1.0,
    "sale_recency": -1.0,
    "tax_distress": -1.0,
    "compliance": -1.0,
}

# Michigan forfeiture/foreclosure distress, ordinal and tunable. Empty = none.
FORFEITURE_DISTRESS_SCORES = {
    "": 0.0,
    "CFD": 2.0,
    "NCFD": 3.0,
}
DEFAULT_FORFEITURE_SCORE = 1.0  # any other non-empty code = some distress

COMPLIANCE_SCORES = {
    "compliant": 0.0,
    "on_track": 0.5,
    "in_progress": 1.0,
    "needs_outreach": 2.0,
    "non_compliant": 3.0,
    "unknown": None,
}


def _get(prop, key, default=None):
    if isinstance(prop, dict):
        return prop.get(key, default)
    return getattr(prop, key, default)


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def signal_value(signal: str, prop, *, today: dt.date | None = None) -> float | None:
    """Derive a numeric for `signal` from a Property-like object/dict. None if unavailable."""
    if signal == "tax_distress":
        code = (_get(prop, "forfeiture_status") or "").strip().upper()
        if not code:
            return 0.0
        return FORFEITURE_DISTRESS_SCORES.get(code, DEFAULT_FORFEITURE_SCORE)
    if signal == "sale_recency":
        sold = _parse_date(_get(prop, "closing_date"))
        if not sold:
            return None
        today = today or dt.date.today()
        days = (today - sold).days
        return float(days) if days >= 0 else None
    if signal == "compliance":
        return COMPLIANCE_SCORES.get(_get(prop, "compliance_status") or "unknown")
    if signal == "assessed_value":
        value = _get(prop, "assessed_value")
        return float(value) if value is not None else None
    if signal == "value_trajectory":
        # Needs >= 2 ParcelValueSnapshot with assessed/taxable values; absent today.
        return None
    return None


def collect(parcels, signal: str, *, today: dt.date | None = None):
    """Return (parcel_ids, coords Nx2 [lon,lat], values N) for parcels with a
    location and a non-null value for `signal`. Arrays are aligned by index."""
    ids: list[str] = []
    coords: list[tuple[float, float]] = []
    values: list[float] = []
    for prop in parcels:
        lat = _get(prop, "latitude")
        lon = _get(prop, "longitude")
        if lat is None or lon is None:
            continue
        value = signal_value(signal, prop, today=today)
        if value is None:
            continue
        ids.append(_get(prop, "parcel_id"))
        coords.append((float(lon), float(lat)))
        values.append(float(value))
    return ids, np.asarray(coords, dtype=float), np.asarray(values, dtype=float)
