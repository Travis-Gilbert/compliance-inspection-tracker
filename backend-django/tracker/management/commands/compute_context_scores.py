"""
Compute neighborhood-context LISA scores into NeighborhoodContextScore.

Runs after the County ArcGIS sync so scores reflect fresh signals; can be scoped
to a subset of parcels for an incremental recompute. By default it computes every
neighborhood definition the frontend can toggle (faceblock, knn8, queen,
blockgroup) for the chosen signal AND the composite blend, so every toggle has
data. faceblock is the org-facing default (this-block proxy); knn8 is the analyst
default. blockgroup needs the Census TIGERweb fetch, so it is skipped with a note
(not a crash) when the network is unavailable.

Pass --neighborhood-def to compute a single definition instead of the full set.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Org-facing default first. rook stays available (selectable) but is not in the
# default set to keep the toggle list to the four spec definitions + composite.
DEFAULT_DEFS = ("faceblock", "knn8", "queen", "blockgroup")


class Command(BaseCommand):
    help = "Compute neighborhood-context LISA scores (Local Moran / Getis-Ord)."

    def add_arguments(self, parser):
        parser.add_argument("--signal", default="tax_distress", help="condition signal to score")
        parser.add_argument(
            "--neighborhood-def",
            default=None,
            help="faceblock | knn{N} | queen | rook | blockgroup (default: all toggles)",
        )
        parser.add_argument("--k", type=int, default=8, help="k for KNN / faceblock weights")
        parser.add_argument("--parcels", nargs="*", default=None, help="limit to these parcel ids")
        parser.add_argument(
            "--composite",
            action="store_true",
            help="compute only the composite blend (skip the per-signal pass)",
        )
        parser.add_argument(
            "--no-composite",
            action="store_true",
            help="skip the composite blend (per-signal pass only)",
        )
        parser.add_argument("--seed", type=int, default=None, help="permutation seed for reproducibility")

    def handle(self, *args, **opts):
        from tracker.services.context import composite, lisa

        defs = [opts["neighborhood_def"]] if opts["neighborhood_def"] else list(DEFAULT_DEFS)

        for definition in defs:
            if not opts["composite"]:
                self._run(
                    lambda d=definition: lisa.compute_and_store(
                        signal=opts["signal"],
                        neighborhood_def=d,
                        parcel_ids=opts["parcels"],
                        k=opts["k"],
                        seed=opts["seed"],
                    ),
                    definition,
                )
            if not opts["no_composite"]:
                self._run(
                    lambda d=definition: composite.compute_composite(
                        neighborhood_def=d,
                        parcel_ids=opts["parcels"],
                        k=opts["k"],
                        seed=opts["seed"],
                    ),
                    definition,
                )

    def _run(self, fn, definition):
        try:
            result = fn()
        except Exception as exc:
            # One definition must never kill the rest of the loop. blockgroup can
            # raise RuntimeError when the Census fetch is unavailable (skip, never
            # fabricate membership); KNN/contiguity can raise on degenerate inputs
            # (e.g. k >= parcel count on a tiny subset). Log and move on.
            note = f"skipped neighborhood_def={definition}: {exc}"
            logger.warning(note)
            self.stdout.write(self.style.WARNING(note))
            return
        style = self.style.SUCCESS if result.get("computed") else self.style.WARNING
        self.stdout.write(style(str(result)))
