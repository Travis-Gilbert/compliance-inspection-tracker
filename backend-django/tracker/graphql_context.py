"""
GCLBA neighborhood-context + compliance GraphQL types and queries (Claude lane).

Kept in a separate module and merged into the schema via strawberry.tools.merge_types
so the shared graphql_schema.py only gains an import and a one-line schema change.
Exposes the Phase 2 (context scores) and Phase 4 (compliance) backend so the GCLBA
fork can consume real data over the same urql/GraphQL layer.

Types are defined before the query classes that reference them (no future
annotations), so Strawberry resolves them directly.
"""

import datetime as dt
import math

import strawberry
from strawberry.scalars import JSON


@strawberry.type
class NeighborhoodContextScoreType:
    parcel_id: str
    neighborhood_def: str
    signal: str
    parcel_value: float | None
    local_mean: float | None
    local_std: float | None
    z_score: float | None
    spatial_lag: float | None
    moran_cluster: str
    moran_p: float | None
    gi_star: float | None
    neighbor_parcel_ids: JSON


@strawberry.type
class CaseEventType:
    occurred_at: dt.datetime
    transition: str
    actor: str
    category_tag: str
    note: str


@strawberry.type
class ComplianceCaseType:
    id: int
    parcel_id: str
    program: str
    status: str
    sale_date: dt.date | None
    rehab_deadline: dt.date | None
    current_confidence: float | None


@strawberry.type
class WeeklyReportCategoryType:
    tag: str
    label: str
    target_pct: int
    actual_pct: float
    count: int


@strawberry.type
class WeeklyReportType:
    start: dt.date
    end: dt.date
    prepared_by: str
    categories: list[WeeklyReportCategoryType]
    text: str
    html: str


def _finite(value: float | None) -> float | None:
    """Collapse NaN/inf to None.

    GraphQL Float cannot represent NaN or infinity; a single non-finite value
    poisons the whole response with a "Float cannot represent non numeric
    value: nan" error, which flips the frontend into its no-data state. Isolated
    parcels and zero-variance neighborhoods can produce NaN in the LISA stats,
    so guard every float field here. All of these fields are already nullable on
    the client.
    """
    if value is None:
        return None
    try:
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _score_type(score) -> NeighborhoodContextScoreType:
    return NeighborhoodContextScoreType(
        parcel_id=score.parcel_id,
        neighborhood_def=score.neighborhood_def,
        signal=score.signal,
        parcel_value=_finite(score.parcel_value),
        local_mean=_finite(score.local_mean),
        local_std=_finite(score.local_std),
        z_score=_finite(score.z_score),
        spatial_lag=_finite(score.spatial_lag),
        moran_cluster=score.moran_cluster,
        moran_p=_finite(score.moran_p),
        gi_star=_finite(score.gi_star),
        neighbor_parcel_ids=score.neighbor_parcel_ids or [],
    )


def _case_type(case) -> ComplianceCaseType:
    return ComplianceCaseType(
        id=case.id,
        parcel_id=case.parcel_id,
        program=case.program,
        status=case.status,
        sale_date=case.sale_date,
        rehab_deadline=case.rehab_deadline,
        current_confidence=case.current_confidence,
    )


@strawberry.type
class ContextQuery:
    @strawberry.field
    def context_scores(
        self,
        neighborhood_def: str = "faceblock",
        signal: str = "tax_distress",
        parcel_ids: list[str] | None = None,
        limit: int = 2000,
    ) -> list[NeighborhoodContextScoreType]:
        from tracker.models import NeighborhoodContextScore

        qs = NeighborhoodContextScore.objects.filter(neighborhood_def=neighborhood_def, signal=signal)
        if parcel_ids:
            qs = qs.filter(parcel_id__in=parcel_ids)
        return [_score_type(s) for s in qs[: max(1, min(limit, 5000))]]

    @strawberry.field
    def context_score(
        self,
        parcel_id: str,
        neighborhood_def: str = "faceblock",
        signal: str = "tax_distress",
    ) -> NeighborhoodContextScoreType | None:
        from tracker.models import NeighborhoodContextScore

        score = NeighborhoodContextScore.objects.filter(
            parcel_id=parcel_id, neighborhood_def=neighborhood_def, signal=signal
        ).first()
        return _score_type(score) if score else None


@strawberry.type
class ComplianceQuery:
    @strawberry.field
    def compliance_cases(
        self,
        status: str | None = None,
        program: str | None = None,
        limit: int = 100,
    ) -> list[ComplianceCaseType]:
        from tracker.models import ComplianceCase

        qs = ComplianceCase.objects.all()
        if status:
            qs = qs.filter(status=status)
        if program:
            qs = qs.filter(program=program)
        return [_case_type(c) for c in qs[: max(1, min(limit, 500))]]

    @strawberry.field
    def compliance_case(self, parcel_id: str) -> ComplianceCaseType | None:
        from tracker.models import ComplianceCase

        case = ComplianceCase.objects.filter(parcel_id=parcel_id).first()
        return _case_type(case) if case else None

    @strawberry.field
    def case_events(self, parcel_id: str, limit: int = 50) -> list[CaseEventType]:
        from tracker.models import CaseEvent

        events = CaseEvent.objects.filter(case__parcel_id=parcel_id).order_by("-occurred_at")[: max(1, min(limit, 500))]
        return [
            CaseEventType(
                occurred_at=event.occurred_at,
                transition=event.transition,
                actor=event.actor,
                category_tag=event.category_tag,
                note=event.note,
            )
            for event in events
        ]

    @strawberry.field
    def weekly_report(
        self,
        week_of: dt.date | None = None,
        prepared_by: str = "Travis Gilbert",
    ) -> WeeklyReportType:
        from tracker.services.compliance import report as report_mod

        result = report_mod.build_report(week_of, prepared_by=prepared_by)
        data = result["data"]
        categories = [
            WeeklyReportCategoryType(
                tag=tag,
                label=report_mod.CATEGORY_LABELS.get(tag, tag),
                target_pct=bucket.get("target_pct", 0),
                actual_pct=bucket.get("actual_pct", 0.0),
                count=bucket.get("count", 0),
            )
            for tag, bucket in data.categories.items()
        ]
        return WeeklyReportType(
            start=data.start,
            end=data.end,
            prepared_by=data.prepared_by,
            categories=categories,
            text=result["text"],
            html=result["html"],
        )
