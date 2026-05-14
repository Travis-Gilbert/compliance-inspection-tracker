from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from typing import Any, Iterable

from django.utils import timezone

from tracker.services.compliance_timing import (
    ACTION_ATTEMPT_1,
    ACTION_ATTEMPT_2,
    ACTION_DEFAULT_NOTICE,
    ACTION_NOT_DUE_YET,
    ACTION_WARNING,
    ComplianceTimingError,
    ComplianceTimingResult,
    compute_compliance_timing,
    get_effective_program_rules,
)


TIMING_ACTIONS = (
    ACTION_ATTEMPT_1,
    ACTION_ATTEMPT_2,
    ACTION_WARNING,
    ACTION_DEFAULT_NOTICE,
)

ACTION_LABELS = {
    ACTION_ATTEMPT_1: "First Attempt",
    ACTION_ATTEMPT_2: "Second Attempt",
    ACTION_WARNING: "Warning",
    ACTION_DEFAULT_NOTICE: "Default Notice",
    "MISSING_EMAIL": "Missing Email",
    "TAX_VERIFICATION": "Tax Verification",
    "NEEDS_INSPECTION": "Needs Inspection",
    "MANUAL_REVIEW": "Manual Review",
}

QUEUE_ACTION_ORDER = (
    ACTION_ATTEMPT_1,
    ACTION_ATTEMPT_2,
    ACTION_WARNING,
    ACTION_DEFAULT_NOTICE,
    "MISSING_EMAIL",
    "TAX_VERIFICATION",
    "NEEDS_INSPECTION",
    "MANUAL_REVIEW",
)

OPEN_ACTION_STATUSES = {"open", "in_progress"}
SENT_COMMUNICATION_STATUSES = {"sent", "delivered"}
RESOLVED_FINDINGS = {
    "visibly_renovated",
    "occupied_maintained",
    "partial_progress",
    "appears_vacant",
    "structure_gone",
}


def build_action_queue(properties: Iterable[Any], as_of: date | datetime | None = None) -> dict[str, Any]:
    rules = get_effective_program_rules()
    groups: dict[str, list[dict[str, Any]]] = {action: [] for action in QUEUE_ACTION_ORDER}
    seen: dict[str, set[tuple[Any, str]]] = {action: set() for action in QUEUE_ACTION_ORDER}
    as_of_date = _coerce_date(as_of) or date.today()

    for prop in properties:
        timing_input = property_timing_input(prop)
        timing = compute_compliance_timing(timing_input, as_of=as_of_date, rules=rules)
        contact_email = property_contact_email(prop)
        workflow_closed = property_workflow_closed(prop)

        action_items = getattr(prop, "action_items", ())
        if hasattr(action_items, "all"):
            action_items = action_items.all()
        for action_item in action_items:
            if action_item.status not in OPEN_ACTION_STATUSES:
                continue
            _append_group_item(
                groups,
                seen,
                action_item.action,
                {
                    "propertyId": prop.id,
                    "parcelId": prop.parcel_id,
                    "address": prop.address,
                    "buyerName": property_buyer_name(prop),
                    "buyerEmail": contact_email,
                    "program": property_program_label(prop),
                    "action": action_item.action,
                    "actionLabel": ACTION_LABELS.get(action_item.action, action_item.action),
                    "status": action_item.status,
                    "dueDate": action_item.due_date.isoformat() if action_item.due_date else None,
                    "daysOverdue": int(action_item.days_overdue or 0),
                    "priority": int(action_item.priority or 0),
                    "enforcementLevel": int(action_item.enforcement_level or 0),
                    "reasons": list(action_item.reasons or []),
                    "source": action_item.source or "system",
                    "finding": prop.finding,
                    "manualOutcome": prop.manual_compliance_outcome,
                    "taxStatus": prop.tax_status,
                    "notes": "",
                },
            )

        if workflow_closed:
            continue

        if isinstance(timing, ComplianceTimingResult):
            if timing.is_due_now and timing.current_action in TIMING_ACTIONS:
                if contact_email:
                    _append_group_item(
                        groups,
                        seen,
                        timing.current_action,
                        _queue_item_from_timing(prop, timing, timing.current_action, contact_email),
                    )
                else:
                    _append_group_item(
                        groups,
                        seen,
                        "MISSING_EMAIL",
                        _queue_item_from_timing(
                            prop,
                            timing,
                            "MISSING_EMAIL",
                            contact_email,
                            extra_reasons=(
                                f"{timing.current_action} is due, but no buyer email is on file.",
                            ),
                        ),
                    )
            if getattr(prop, "finding", "") == "inconclusive":
                _append_group_item(
                    groups,
                    seen,
                    "NEEDS_INSPECTION",
                    _property_issue_item(
                        prop,
                        action="NEEDS_INSPECTION",
                        contact_email=contact_email,
                        due_date=None,
                        days_overdue=0,
                        priority=60,
                        reasons=("Desk review marked this property as inconclusive.",),
                    ),
                )
        else:
            _append_group_item(
                groups,
                seen,
                "MANUAL_REVIEW",
                _property_issue_item(
                    prop,
                    action="MANUAL_REVIEW",
                    contact_email=contact_email,
                    due_date=None,
                    days_overdue=0,
                    priority=50,
                    reasons=(timing.error,),
                    notes=timing.error,
                ),
            )

    for items in groups.values():
        items.sort(
            key=lambda item: (
                -int(item.get("priority", 0) or 0),
                -int(item.get("daysOverdue", 0) or 0),
                item.get("dueDate") or "9999-12-31",
                item.get("address") or "",
            )
        )

    return {
        "asOf": as_of_date.isoformat(),
        "groupOrder": list(QUEUE_ACTION_ORDER),
        "groups": [
            {
                "action": action,
                "label": ACTION_LABELS.get(action, action),
                "count": len(groups[action]),
                "items": groups[action],
            }
            for action in QUEUE_ACTION_ORDER
        ],
        "summary": {action: len(groups[action]) for action in QUEUE_ACTION_ORDER},
        "totalItems": sum(len(groups[action]) for action in QUEUE_ACTION_ORDER),
    }


def render_template_preview(
    prop: Any,
    action: str,
    template_slug: str | None = None,
    as_of: date | datetime | None = None,
    include_inactive: bool = False,
) -> dict[str, Any]:
    timing = compute_property_timing(prop, as_of=as_of)
    program_key = _program_key_from_timing_or_property(prop, timing)
    template = select_email_template(
        program_key=program_key,
        action=action,
        template_slug=template_slug,
        include_inactive=include_inactive,
    )
    if template is None:
        raise LookupError(f"No email template found for {program_key} / {action}")

    variants = template.variants or {}
    variant = variants.get(action)
    if not isinstance(variant, dict):
        raise LookupError(f'Template "{template.slug}" has no "{action}" variant')

    values = template_variables(prop, action=action, timing=timing)
    rendered_subject, subject_missing = _replace_template_tokens(str(variant.get("subject", "")), values)
    rendered_body, body_missing = _replace_template_tokens(str(variant.get("body", "")), values)
    missing_vars = sorted(set(subject_missing + body_missing))

    return {
        "propertyId": prop.id,
        "action": action,
        "template": {
            "slug": template.slug,
            "name": template.name,
            "status": template.status,
            "isActive": template.is_active,
        },
        "recipientEmail": values["{BuyerEmail}"],
        "subject": rendered_subject,
        "body": rendered_body,
        "missingVariables": missing_vars,
        "variables": {key.strip("{}"): value for key, value in values.items()},
        "timing": _timing_payload(timing),
    }


def select_email_template(
    program_key: str,
    action: str,
    template_slug: str | None = None,
    include_inactive: bool = False,
):
    from tracker.models import EmailTemplate

    queryset = EmailTemplate.objects.all()
    if not include_inactive:
        queryset = queryset.filter(is_active=True, status="active")
    templates = list(queryset.order_by("-is_active", "name"))
    if template_slug:
        templates = [template for template in templates if template.slug == template_slug]

    for template in templates:
        program_keys = list(template.program_keys or [])
        variants = template.variants or {}
        if program_key in program_keys and action in variants:
            return template
    return None


def template_variables(
    prop: Any,
    action: str,
    timing: ComplianceTimingResult | ComplianceTimingError,
) -> dict[str, str]:
    if isinstance(timing, ComplianceTimingResult):
        due_date = timing.due_date.isoformat()
        days_overdue = str(timing.days_overdue)
        program_label = timing.program_label
        next_action = ACTION_LABELS.get(timing.next_action or "", timing.next_action or "")
    else:
        due_date = ""
        days_overdue = "0"
        program_label = property_program_label(prop)
        next_action = ""

    return {
        "{BuyerName}": property_buyer_name(prop),
        "{PropertyAddress}": getattr(prop, "address", "") or "",
        "{DueDate}": due_date,
        "{DaysOverdue}": days_overdue,
        "{ProgramType}": program_label,
        "{BuyerEmail}": property_contact_email(prop),
        "{ParcelId}": getattr(prop, "parcel_id", "") or "",
        "{CurrentAction}": ACTION_LABELS.get(action, action),
        "{NextAction}": next_action,
        "{Organization}": getattr(prop, "organization", "") or "",
    }


def compute_property_timing(
    prop: Any,
    as_of: date | datetime | None = None,
) -> ComplianceTimingResult | ComplianceTimingError:
    return compute_compliance_timing(
        property_timing_input(prop),
        as_of=as_of,
        rules=get_effective_program_rules(),
    )


def property_timing_input(prop: Any) -> dict[str, Any]:
    return {
        "id": getattr(prop, "id", None),
        "parcel_id": getattr(prop, "parcel_id", "") or "",
        "address": getattr(prop, "address", "") or "",
        "buyer_name": property_buyer_name(prop),
        "email": property_contact_email(prop),
        "program": property_program_value(prop),
        "closing_date": getattr(prop, "closing_date", "") or "",
        "compliance_1st_attempt": getattr(prop, "compliance_1st_attempt", "") or "",
        "compliance_2nd_attempt": getattr(prop, "compliance_2nd_attempt", "") or "",
        "last_outreach_date": getattr(prop, "last_outreach_date", None),
        "communications": list(getattr(prop, "communications", ()).all())
        if hasattr(getattr(prop, "communications", ()), "all")
        else list(getattr(prop, "communications", ()) or ()),
    }


def property_buyer_name(prop: Any) -> str:
    buyer_name = getattr(prop, "buyer_name", "") or ""
    if buyer_name.strip():
        return buyer_name
    buyer = getattr(prop, "buyer", None)
    return getattr(buyer, "full_name", "") or ""


def property_contact_email(prop: Any) -> str:
    email = getattr(prop, "email", "") or ""
    if email.strip():
        return email
    buyer = getattr(prop, "buyer", None)
    return getattr(buyer, "email", "") or ""


def property_program_value(prop: Any) -> str:
    program = getattr(prop, "program", "") or ""
    if program.strip():
        return program
    program_record = getattr(prop, "program_record", None)
    if program_record is None:
        return ""
    return getattr(program_record, "key", "") or getattr(program_record, "label", "") or ""


def property_program_label(prop: Any) -> str:
    program_record = getattr(prop, "program_record", None)
    if program_record is not None and getattr(program_record, "label", ""):
        return str(program_record.label)
    return property_program_value(prop)


def property_workflow_closed(prop: Any) -> bool:
    if bool(getattr(prop, "is_resolved", False)):
        return True
    return (getattr(prop, "finding", "") or "") in RESOLVED_FINDINGS


def prepare_workflow_communication(
    prop: Any,
    *,
    method: str,
    direction: str,
    action: str,
    status: str,
    template_slug: str | None = None,
    recipient_email: str = "",
    subject: str = "",
    body: str = "",
    date_sent: date | None = None,
    sent_at: datetime | None = None,
    approved_at: datetime | None = None,
    provider_message_id: str = "",
) -> dict[str, Any]:
    preview = None
    preview_as_of = date_sent or (sent_at.date() if sent_at else None)
    if action:
        preview = render_template_preview(
            prop,
            action=action,
            template_slug=template_slug,
            as_of=preview_as_of,
        )

    final_recipient = recipient_email or (preview["recipientEmail"] if preview else property_contact_email(prop))
    final_subject = subject or (preview["subject"] if preview else "")
    final_body = body or (preview["body"] if preview else "")
    now = timezone.now()

    if status in SENT_COMMUNICATION_STATUSES:
        sent_timestamp = sent_at or now
        sent_date = date_sent or sent_timestamp.date()
        approved_timestamp = approved_at or now
    else:
        sent_timestamp = sent_at
        sent_date = date_sent
        approved_timestamp = approved_at

    return {
        "buyer": getattr(prop, "buyer", None),
        "template": preview["template"]["slug"] if preview else template_slug,
        "template_name": preview["template"]["name"] if preview else "",
        "method": method,
        "direction": direction,
        "action": action,
        "status": status,
        "recipient_email": final_recipient,
        "subject": final_subject,
        "body": final_body,
        "body_hash": sha256(final_body.encode("utf-8")).hexdigest() if final_body else "",
        "date_sent": sent_date,
        "sent_at": sent_timestamp,
        "approved_at": approved_timestamp,
        "provider_message_id": provider_message_id,
        "preview": preview,
    }


def apply_communication_rollups(prop: Any, *, action: str, status: str, method: str, date_sent: date | None) -> list[str]:
    if status not in SENT_COMMUNICATION_STATUSES or not date_sent:
        return []

    update_fields: list[str] = []
    if action == ACTION_ATTEMPT_1 and not getattr(prop, "compliance_1st_attempt", ""):
        prop.compliance_1st_attempt = date_sent.isoformat()
        update_fields.append("compliance_1st_attempt")
    if action == ACTION_ATTEMPT_2 and not getattr(prop, "compliance_2nd_attempt", ""):
        prop.compliance_2nd_attempt = date_sent.isoformat()
        update_fields.append("compliance_2nd_attempt")

    current_last_outreach = getattr(prop, "last_outreach_date", None)
    if current_last_outreach is None or date_sent >= current_last_outreach:
        prop.last_outreach_date = date_sent
        prop.last_outreach_method = method
        update_fields.extend(["last_outreach_date", "last_outreach_method"])

    prop.outreach_attempts = int(getattr(prop, "outreach_attempts", 0) or 0) + 1
    update_fields.append("outreach_attempts")
    return update_fields


def _append_group_item(
    groups: dict[str, list[dict[str, Any]]],
    seen: dict[str, set[tuple[Any, str]]],
    action: str,
    item: dict[str, Any],
) -> None:
    if action not in groups:
        return
    dedupe_key = (item.get("propertyId"), action)
    if dedupe_key in seen[action]:
        return
    seen[action].add(dedupe_key)
    groups[action].append(item)


def _queue_item_from_timing(
    prop: Any,
    timing: ComplianceTimingResult,
    action: str,
    contact_email: str,
    extra_reasons: tuple[str, ...] = (),
) -> dict[str, Any]:
    reasons = list(extra_reasons) + list(timing.reasons)
    priority = max(timing.days_overdue, 0) * 10 + timing.recommended_enforcement_level * 25
    if action == "MISSING_EMAIL":
        priority += 15

    return {
        "propertyId": prop.id,
        "parcelId": prop.parcel_id,
        "address": prop.address,
        "buyerName": property_buyer_name(prop),
        "buyerEmail": contact_email,
        "program": timing.program_label,
        "action": action,
        "actionLabel": ACTION_LABELS.get(action, action),
        "status": "open",
        "dueDate": timing.due_date.isoformat(),
        "daysOverdue": timing.days_overdue,
        "priority": priority,
        "enforcementLevel": timing.recommended_enforcement_level,
        "reasons": reasons,
        "source": "timing",
        "finding": prop.finding,
        "manualOutcome": prop.manual_compliance_outcome,
        "taxStatus": prop.tax_status,
        "notes": "",
        "timing": timing.as_dict(),
    }


def _property_issue_item(
    prop: Any,
    *,
    action: str,
    contact_email: str,
    due_date: date | None,
    days_overdue: int,
    priority: int,
    reasons: tuple[str, ...],
    notes: str = "",
) -> dict[str, Any]:
    return {
        "propertyId": prop.id,
        "parcelId": prop.parcel_id,
        "address": prop.address,
        "buyerName": property_buyer_name(prop),
        "buyerEmail": contact_email,
        "program": property_program_label(prop),
        "action": action,
        "actionLabel": ACTION_LABELS.get(action, action),
        "status": "open",
        "dueDate": due_date.isoformat() if due_date else None,
        "daysOverdue": days_overdue,
        "priority": priority,
        "enforcementLevel": 0,
        "reasons": list(reasons),
        "source": "derived",
        "finding": prop.finding,
        "manualOutcome": prop.manual_compliance_outcome,
        "taxStatus": prop.tax_status,
        "notes": notes,
    }


def _program_key_from_timing_or_property(
    prop: Any,
    timing: ComplianceTimingResult | ComplianceTimingError,
) -> str:
    if isinstance(timing, ComplianceTimingResult):
        return timing.program_key
    program_record = getattr(prop, "program_record", None)
    if program_record is not None and getattr(program_record, "key", ""):
        return str(program_record.key)
    return property_program_value(prop)


def _replace_template_tokens(template_text: str, values: dict[str, str]) -> tuple[str, list[str]]:
    rendered = template_text
    missing: list[str] = []
    for token, value in values.items():
        if not value and token != "{DaysOverdue}":
            missing.append(token)
        rendered = rendered.replace(token, value or token)
    return rendered, missing


def _timing_payload(timing: ComplianceTimingResult | ComplianceTimingError) -> dict[str, Any]:
    if isinstance(timing, ComplianceTimingResult):
        return timing.as_dict()
    return timing.as_dict()


def _coerce_date(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value
