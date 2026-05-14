from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

from tracker.services.enrichment import parse_closing_date


ACTION_ATTEMPT_1 = "ATTEMPT_1"
ACTION_ATTEMPT_2 = "ATTEMPT_2"
ACTION_WARNING = "WARNING"
ACTION_DEFAULT_NOTICE = "DEFAULT_NOTICE"
ACTION_NOT_DUE_YET = "NOT_DUE_YET"
ACTION_MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass(frozen=True)
class ScheduleStep:
    day: int
    action: str
    level: int


@dataclass(frozen=True)
class ProgramRule:
    key: str
    label: str
    cadence: str
    schedule: tuple[ScheduleStep, ...]
    grace_days: int = 0
    required_uploads: tuple[str, ...] = ()
    required_docs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComplianceTimingResult:
    property_id: Any | None
    parcel_id: str
    address: str
    buyer_name: str
    buyer_email: str
    program_key: str
    program_label: str
    days_since_close: int
    current_action: str
    recommended_enforcement_level: int
    due_date: date
    is_due_now: bool
    days_overdue: int
    action_already_sent: bool
    completed_actions: tuple[str, ...]
    next_action: str | None
    next_due_date: date | None
    last_contact_date: date | None
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "propertyId": self.property_id,
            "parcelId": self.parcel_id,
            "address": self.address,
            "buyerName": self.buyer_name,
            "buyerEmail": self.buyer_email,
            "programType": self.program_key,
            "programLabel": self.program_label,
            "daysSinceClose": self.days_since_close,
            "currentAction": self.current_action,
            "recommendedEnforcementLevel": self.recommended_enforcement_level,
            "dueDate": self.due_date.isoformat(),
            "isDueNow": self.is_due_now,
            "daysOverdue": self.days_overdue,
            "actionAlreadySent": self.action_already_sent,
            "completedActions": list(self.completed_actions),
            "nextAction": self.next_action,
            "nextDueDate": self.next_due_date.isoformat() if self.next_due_date else None,
            "lastContactDate": self.last_contact_date.isoformat() if self.last_contact_date else None,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ComplianceTimingError:
    error: str
    property_id: Any | None = None
    parcel_id: str = ""
    address: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "propertyId": self.property_id,
            "parcelId": self.parcel_id,
            "address": self.address,
            "buyerName": "",
            "buyerEmail": "",
            "programType": "",
            "programLabel": "",
            "daysSinceClose": 0,
            "currentAction": ACTION_MANUAL_REVIEW,
            "recommendedEnforcementLevel": 0,
            "dueDate": "",
            "isDueNow": False,
            "daysOverdue": 0,
            "actionAlreadySent": False,
            "completedActions": [],
            "nextAction": None,
            "nextDueDate": None,
            "lastContactDate": None,
            "reasons": [self.error],
        }


DEFAULT_PROGRAM_RULES: dict[str, ProgramRule] = {
    "FeaturedHomes": ProgramRule(
        key="FeaturedHomes",
        label="Featured Homes",
        cadence="monthly",
        grace_days=3,
        schedule=(
            ScheduleStep(day=30, action=ACTION_ATTEMPT_1, level=1),
            ScheduleStep(day=60, action=ACTION_ATTEMPT_2, level=2),
            ScheduleStep(day=90, action=ACTION_WARNING, level=3),
            ScheduleStep(day=120, action=ACTION_DEFAULT_NOTICE, level=4),
        ),
        required_uploads=(
            "Front Exterior",
            "Rear Exterior",
            "Kitchen",
            "Bathroom",
            "Living Area",
            "Bedroom",
            "Basement",
            "Active Work Area",
        ),
        required_docs=("Permits (if applicable)", "Contracts (if applicable)"),
    ),
    "Ready4Rehab": ProgramRule(
        key="Ready4Rehab",
        label="Ready4Rehab",
        cadence="monthly",
        grace_days=3,
        schedule=(
            ScheduleStep(day=30, action=ACTION_ATTEMPT_1, level=1),
            ScheduleStep(day=60, action=ACTION_ATTEMPT_2, level=2),
            ScheduleStep(day=90, action=ACTION_WARNING, level=3),
            ScheduleStep(day=120, action=ACTION_DEFAULT_NOTICE, level=4),
        ),
        required_uploads=(
            "Front Exterior",
            "Rear Exterior",
            "Kitchen",
            "Bathroom",
            "Living Area",
            "Bedroom",
            "Basement",
            "Active Work Area",
        ),
        required_docs=("Permits (if applicable)", "Contracts (if applicable)"),
    ),
    "Demolition": ProgramRule(
        key="Demolition",
        label="Demolition",
        cadence="milestones",
        grace_days=0,
        schedule=(
            ScheduleStep(day=14, action=ACTION_ATTEMPT_1, level=1),
            ScheduleStep(day=30, action=ACTION_WARNING, level=3),
            ScheduleStep(day=45, action=ACTION_DEFAULT_NOTICE, level=4),
        ),
        required_uploads=("Site Before", "During", "After"),
        required_docs=("Contractor Agreement", "Disposal Receipt"),
    ),
    "VIP": ProgramRule(
        key="VIP",
        label="VIP",
        cadence="quarterly",
        grace_days=5,
        schedule=(
            ScheduleStep(day=90, action=ACTION_ATTEMPT_1, level=1),
            ScheduleStep(day=120, action=ACTION_ATTEMPT_2, level=2),
            ScheduleStep(day=150, action=ACTION_WARNING, level=3),
            ScheduleStep(day=180, action=ACTION_DEFAULT_NOTICE, level=4),
        ),
        required_uploads=("Front Exterior", "Rear Exterior"),
        required_docs=("Insurance Proof",),
    ),
}


PROGRAM_ALIASES = {
    "featured": "FeaturedHomes",
    "featuredhomes": "FeaturedHomes",
    "fhadjvl": "FeaturedHomes",
    "ready4rehab": "Ready4Rehab",
    "readyforrehab": "Ready4Rehab",
    "r4r": "Ready4Rehab",
    "r4radjvl": "Ready4Rehab",
    "demolition": "Demolition",
    "demo": "Demolition",
    "vip": "VIP",
    "vipspotlight": "VIP",
}


def normalize_program_key(program: Any) -> str:
    value = str(program or "").strip()
    if not value:
        return ""
    token = "".join(ch for ch in value.lower() if ch.isalnum())
    return PROGRAM_ALIASES.get(token, value)


def get_program_rule(
    program: Any,
    rules: Mapping[str, ProgramRule | Mapping[str, Any]] | None = None,
) -> ProgramRule | None:
    rule_map = rules or DEFAULT_PROGRAM_RULES
    key = normalize_program_key(program)
    if key in rule_map:
        return _coerce_rule(key, rule_map[key])
    return None


def compute_compliance_timing(
    record: Any,
    as_of: date | datetime | None = None,
    rules: Mapping[str, ProgramRule | Mapping[str, Any]] | None = None,
    use_database_rules: bool = False,
) -> ComplianceTimingResult | ComplianceTimingError:
    today = _coerce_date(as_of) or date.today()
    property_id = _record_get(record, "id", "property_id", "propertyId")
    parcel_id = str(_record_get(record, "parcel_id", "parcelId", default="") or "")
    address = str(_record_get(record, "address", default="") or "")

    program_value = _record_get(record, "program", "program_type", "programType", default="")
    if rules is None and use_database_rules:
        rules = get_effective_program_rules()
    rule = get_program_rule(program_value, rules=rules)
    if not rule:
        return ComplianceTimingError(
            error=f"No rules found for program: {program_value}",
            property_id=property_id,
            parcel_id=parcel_id,
            address=address,
        )

    close_raw = _record_get(
        record,
        "closing_date",
        "close_date",
        "closeDate",
        "date_sold",
        "dateSold",
    )
    close_date = parse_date_value(close_raw)
    if not close_date:
        return ComplianceTimingError(
            error="Missing closing date",
            property_id=property_id,
            parcel_id=parcel_id,
            address=address,
        )

    days_since_close = (today - close_date).days
    schedule = tuple(sorted(rule.schedule, key=lambda step: step.day))
    current_step = _current_schedule_step(schedule, days_since_close)
    completed_actions = _completed_actions(record)

    effective_step = current_step
    action_already_sent = False
    if current_step.action != ACTION_NOT_DUE_YET and current_step.action in completed_actions:
        action_already_sent = True
        next_due_uncompleted = next(
            (
                step
                for step in schedule
                if step.day > current_step.day
                and days_since_close >= step.day
                and step.action not in completed_actions
            ),
            None,
        )
        if next_due_uncompleted:
            effective_step = next_due_uncompleted
            action_already_sent = False

    next_step = next(
        (
            step
            for step in schedule
            if step.day > effective_step.day and step.action not in completed_actions
        ),
        None,
    )

    due_date = close_date + timedelta(days=effective_step.day)
    raw_days_overdue = (today - due_date).days - rule.grace_days
    is_due_now = (
        effective_step.action != ACTION_NOT_DUE_YET
        and not action_already_sent
        and raw_days_overdue >= 0
    )
    days_overdue = max(0, raw_days_overdue)

    result = ComplianceTimingResult(
        property_id=property_id,
        parcel_id=parcel_id,
        address=address,
        buyer_name=str(_record_get(record, "buyer_name", "buyerName", default="") or ""),
        buyer_email=str(_record_get(record, "email", "buyer_email", "buyerEmail", default="") or ""),
        program_key=rule.key,
        program_label=rule.label,
        days_since_close=days_since_close,
        current_action=effective_step.action,
        recommended_enforcement_level=effective_step.level,
        due_date=due_date,
        is_due_now=is_due_now,
        days_overdue=days_overdue,
        action_already_sent=action_already_sent,
        completed_actions=tuple(sorted(completed_actions)),
        next_action=next_step.action if next_step else None,
        next_due_date=close_date + timedelta(days=next_step.day) if next_step else None,
        last_contact_date=_last_contact_date(record),
        reasons=_build_reasons(
            current_action=effective_step.action,
            due_date=due_date,
            is_due_now=is_due_now,
            days_overdue=days_overdue,
            action_already_sent=action_already_sent,
            next_step=next_step,
        ),
    )
    return result


def compute_batch_timing(
    records: Iterable[Any],
    as_of: date | datetime | None = None,
    rules: Mapping[str, ProgramRule | Mapping[str, Any]] | None = None,
    use_database_rules: bool = False,
) -> list[ComplianceTimingResult]:
    if rules is None and use_database_rules:
        rules = get_effective_program_rules()
    results = [
        result
        for result in (
            compute_compliance_timing(record, as_of=as_of, rules=rules)
            for record in records
        )
        if isinstance(result, ComplianceTimingResult)
    ]
    return sorted(results, key=lambda item: (item.days_overdue, item.due_date), reverse=True)


def load_program_rules_from_db() -> dict[str, ProgramRule]:
    from tracker.models import Program

    rules: dict[str, ProgramRule] = {}
    for program in Program.objects.filter(is_active=True):
        rule = _coerce_rule(
            program.key,
            {
                "key": program.key,
                "label": program.label,
                "cadence": program.cadence,
                "schedule": program.schedule,
                "grace_days": program.grace_days,
                "required_uploads": program.required_uploads,
                "required_docs": program.required_docs,
            },
        )
        rules[rule.key] = rule
    return rules


def get_effective_program_rules() -> dict[str, ProgramRule]:
    try:
        db_rules = load_program_rules_from_db()
    except Exception:
        db_rules = {}
    return db_rules or DEFAULT_PROGRAM_RULES


def parse_date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None

    clean = str(value).strip()
    if not clean:
        return None

    if "T" in clean:
        try:
            return datetime.fromisoformat(clean.replace("Z", "+00:00")).date()
        except ValueError:
            pass

    return parse_closing_date(clean)


def _record_get(record: Any, *names: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        for name in names:
            if name in record:
                return record[name]
        return default

    for name in names:
        if hasattr(record, name):
            return getattr(record, name)
    return default


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _completed_actions(record: Any) -> set[str]:
    completed = set()
    if _has_value(_record_get(record, "compliance_1st_attempt", "compliance1stAttempt")):
        completed.add(ACTION_ATTEMPT_1)
    if _has_value(_record_get(record, "compliance_2nd_attempt", "compliance2ndAttempt")):
        completed.add(ACTION_ATTEMPT_2)

    communications = _record_get(record, "communications", default=()) or ()
    if hasattr(communications, "all"):
        communications = communications.all()

    for communication in communications:
        action = _record_get(communication, "action", default="")
        if not action:
            continue
        status = str(_record_get(communication, "status", default="") or "").lower()
        sent_at = _record_get(communication, "sent_at", "sentAt", "date_sent", "dateSent")
        if status in {"sent", "delivered"} or _has_value(sent_at):
            completed.add(str(action))

    return completed


def _last_contact_date(record: Any) -> date | None:
    direct = parse_date_value(
        _record_get(record, "last_outreach_date", "lastContactDate", "last_contact_date")
    )
    if direct:
        return direct

    contacts: list[date] = []
    communications = _record_get(record, "communications", default=()) or ()
    if hasattr(communications, "all"):
        communications = communications.all()
    for communication in communications:
        sent_date = parse_date_value(
            _record_get(communication, "sent_at", "sentAt", "date_sent", "dateSent")
        )
        if sent_date:
            contacts.append(sent_date)
    return max(contacts) if contacts else None


def _current_schedule_step(schedule: tuple[ScheduleStep, ...], days_since_close: int) -> ScheduleStep:
    for step in reversed(schedule):
        if days_since_close >= step.day:
            return step
    return ScheduleStep(day=0, action=ACTION_NOT_DUE_YET, level=0)


def _coerce_date(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value


def _coerce_rule(key: str, rule: ProgramRule | Mapping[str, Any]) -> ProgramRule:
    if isinstance(rule, ProgramRule):
        return rule

    schedule_raw = rule.get("schedule") or rule.get("scheduleDaysFromClose") or ()
    schedule = tuple(
        ScheduleStep(
            day=int(step["day"]),
            action=str(step["action"]),
            level=int(step.get("level", 0)),
        )
        for step in schedule_raw
    )
    return ProgramRule(
        key=str(rule.get("key") or key),
        label=str(rule.get("label") or key),
        cadence=str(rule.get("cadence") or ""),
        schedule=schedule,
        grace_days=int(rule.get("grace_days", rule.get("graceDays", 0)) or 0),
        required_uploads=tuple(rule.get("required_uploads", rule.get("requiredUploads", ())) or ()),
        required_docs=tuple(rule.get("required_docs", rule.get("requiredDocs", ())) or ()),
    )


def _build_reasons(
    current_action: str,
    due_date: date,
    is_due_now: bool,
    days_overdue: int,
    action_already_sent: bool,
    next_step: ScheduleStep | None,
) -> tuple[str, ...]:
    if current_action == ACTION_NOT_DUE_YET:
        return ("No workflow action is due yet.",)
    if is_due_now:
        return (f"{current_action} is due as of {due_date.isoformat()}.",)
    if action_already_sent:
        if next_step:
            return (
                f"{current_action} has already been logged.",
                f"Next action is {next_step.action}.",
            )
        return (f"{current_action} has already been logged.",)
    if days_overdue == 0:
        return (f"{current_action} is inside the program grace period.",)
    return (f"{current_action} is not due yet.",)
