"""
Compute neighborhood-context LISA scores into NeighborhoodContextScore.

Runs after the County ArcGIS sync so scores reflect fresh signals; can be scoped
to a subset of parcels for an incremental recompute. KNN-on-centroids is the
default neighborhood definition.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Compute neighborhood-context LISA scores (Local Moran / Getis-Ord)."

    def add_arguments(self, parser):
        parser.add_argument("--signal", default="tax_distress", help="condition signal to score")
        parser.add_argument("--neighborhood-def", default="knn8", help="knn{N} | queen | rook")
        parser.add_argument("--k", type=int, default=8, help="k for KNN weights")
        parser.add_argument("--parcels", nargs="*", default=None, help="limit to these parcel ids")
        parser.add_argument("--composite", action="store_true", help="compute the composite blend")
        parser.add_argument("--seed", type=int, default=None, help="permutation seed for reproducibility")

    def handle(self, *args, **opts):
        from tracker.services.context import composite, lisa

        if opts["composite"]:
            result = composite.compute_composite(
                neighborhood_def=opts["neighborhood_def"],
                parcel_ids=opts["parcels"],
                k=opts["k"],
                seed=opts["seed"],
            )
        else:
            result = lisa.compute_and_store(
                signal=opts["signal"],
                neighborhood_def=opts["neighborhood_def"],
                parcel_ids=opts["parcels"],
                k=opts["k"],
                seed=opts["seed"],
            )
        style = self.style.SUCCESS if result.get("computed") else self.style.WARNING
        self.stdout.write(style(str(result)))
