"""
Neighborhood-context spatial analysis for the GCLBA build.

Scores every parcel by its condition RELATIVE to its local spatial neighborhood
(Local Moran's I / Getis-Ord), rather than in absolute terms. Sibling to
services/enrichment.py and services/ingest/.

- signals.py   per-parcel condition signal derivation (pure + DB collection)
- weights.py   libpysal spatial weights (KNN default; Queen/Rook need geopandas)
- lisa.py       Local Moran, local z-score, spatial lag, Getis-Ord; writes scores
- composite.py  weighted blend across signals, reweighted to available signals

Heavy deps (libpysal, esda, geopandas) are imported inside functions so this
package imports cleanly even before they are installed.
"""
