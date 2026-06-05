"""
Deadline and escalation engine (the 40% oversight duty).

Consumes the existing compliance_timing.compute_compliance_timing (so it never
diverges from build_action_queue) plus the case's Benchmark rows, maps the result
to a ComplianceCase lifecycle status, and logs the transition as a CaseEvent. It
does NOT create or close ActionItem rows: status is a separate axis from the
actionable queue.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from tracker.services.compliance_timing import (
    ACTION_DEFAULT_NOTICE,
    ACTION_NOT_DUE_YET,
    ACTION_WARNING,
    ComplianceTimingError,
    compute_compliance_timing,
)

DEFAULT_LEAD_DAYS = 30  # at_risk when a due date is within this window

# Lifecycle severity (auto-managed statuses; "closed" is terminal and never auto-set).
SEVERITY = ["active", "on_track", "at_risk", "non_compliant", "escalated"]


def _most_severe(statuses):
    best, best_index = None, -1
    for status in statuses:
        index = SEVERITY.index(status) if status in SEVERITY else -1
        if index > best_index:
            best, best_index = status, index
    return best


def status_from_timing(result, today: dt.date, lead_days: int = DEFAULT_LEAD_DAYS):
    """Pure: map a ComplianceTimingResult to (status, reasons). No DB."""
    reasons: list[str] = []
    action = result.current_action
    if action == ACTION_DEFAULT_NOTICE and result.is_due_now:
        reasons.append(f"default notice due, {result.days_overdue}d overdue")
        return "escalated", reasons
    if action == ACTION_WARNING and result.is_due_now:
        reasons.append(f"warning due, {result.days_overdue}d overdue")
        return "non_compliant", reasons
    if result.is_due_now:
        reasons.append(f"{action} due, {result.days_overdue}d overdue")
        return "at_risk", reasons
    days_to_due = (result.due_date - today).days if result.due_date else None
    if action != ACTION_NOT_DUE_YET and days_to_due is not None and 0 <= days_to_due <= lead_days:
        reasons.append(f"{action} due in {days_to_due}d")
        return "at_risk", reasons
    if result.completed_actions:
        return "on_track", reasons
    return "active", reasons


def evaluate_case(case, *, as_of: dt.date | None = None, lead_days: int = DEFAULT_LEAD_DAYS):
    """Compute the target lifecycle status for a case from benchmarks + timing. (DB read)"""
    today = as_of or timezone.now().date()
    statuses: list[str] = []
    reasons: list[str] = []

    for benchmark in case.benchmarks.all():
        if not benchmark.due_date or benchmark.met:
            continue
        if benchmark.due_date < today:
            statuses.append("non_compliant")
            reasons.append(f"benchmark '{benchmark.label}' passed unmet ({benchmark.due_date})")
        elif 0 <= (benchmark.due_date - today).days <= lead_days:
            statuses.append("at_risk")
            reasons.append(f"benchmark '{benchmark.label}' due in {(benchmark.due_date - today).days}d")

    prop = case.property
    if prop is not None:
        result = compute_compliance_timing(prop, as_of=today, use_database_rules=True)
        if isinstance(result, ComplianceTimingError):
            reasons.append(f"timing unavailable: {result.error}")
        else:
            status, why = status_from_timing(result, today, lead_days)
            statuses.append(status)
            reasons.extend(why)

    return (_most_severe(statuses) or "active"), reasons


def apply_evaluation(case, *, as_of=None, lead_days=DEFAULT_LEAD_DAYS, actor="deadline_engine"):
    """Evaluate a case and, if its status changed, transition + log a CaseEvent. (DB)"""
    if case.status == "closed":
        return None
    target, reasons = evaluate_case(case, as_of=as_of, lead_days=lead_days)
    if target == case.status:
        return None
    from .cases import transition_case

    return transition_case(
        case,
        target,
        reason="; ".join(reasons) or "deadline evaluation",
        actor=actor,
        category_tag="oversight_enforcement",
    )


def evaluate_open_cases(*, as_of=None, lead_days=DEFAULT_LEAD_DAYS):
    """Evaluate every non-closed case; return [(parcel_id, new_status)] for changes. (DB)"""
    from tracker.models import ComplianceCase

    changed = []
    cases = (
        ComplianceCase.objects.exclude(status="closed")
        .select_related("property")
        .prefetch_related("benchmarks")
    )
    for case in cases:
        event = apply_evaluation(case, as_of=as_of, lead_days=lead_days)
        if event is not None:
            changed.append((case.parcel_id, case.status))
    return changed
