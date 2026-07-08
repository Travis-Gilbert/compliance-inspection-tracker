from __future__ import annotations

import hashlib
import html
import re
import textwrap
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from tracker.models import CandidateProperty, Property, SourceConflict
from tracker.utils.address import build_address_key


SOURCE_LABELS = {
    "site_control_export": "Flint Property Portal / Site Control",
    "filemaker_csv": "Disposition inventory",
    "county_arcgis": "County GIS",
    "compliance_graphql": "Compliance system",
}

SOURCE_SHORT_LABELS = {
    "site_control_export": "Portal",
    "filemaker_csv": "Disposition",
    "county_arcgis": "County",
    "compliance_graphql": "Compliance",
}

PRIVATE_FIELD_MARKERS = {
    "buyer",
    "email",
    "phone",
    "organization",
    "notes",
    "reviewedby",
    "reviewed_by",
}


@dataclass(frozen=True)
class CoverageSummary:
    tracked_property_count: int
    parcels_indexed: int
    home_count: int
    active_program_count: int
    source_count: int
    open_conflict_count: int
    candidate_count: int


@dataclass(frozen=True)
class DiscoveryExample:
    parcel_id: str
    address: str
    reason: str
    evidence: str


@dataclass(frozen=True)
class PropertyIntelligenceReportSnapshot:
    prepared_on: date
    tracked_property_count: int
    parcels_indexed: int
    home_count: int
    active_program_count: int
    source_count: int
    open_conflict_count: int
    candidate_count: int
    resolved_this_period: int
    examples: list[DiscoveryExample]

    @property
    def coverage_line(self) -> str:
        if self.parcels_indexed:
            return (
                "Coverage: The cross-source property record index covers "
                f"{self.parcels_indexed} parcels across {self.source_count} sources; "
                f"{self.home_count} homes and {self.active_program_count} parcels in active "
                "disposition programs are tracked in Django."
            )
        return (
            "Coverage: The cross-source property record index has no imported source "
            f"receipts yet; Django currently tracks {self.tracked_property_count} parcels, "
            f"including {self.home_count} homes and {self.active_program_count} parcels "
            "in active disposition programs."
        )

    @property
    def discoveries_line(self) -> str:
        return (
            "Discoveries: "
            f"{self.candidate_count} candidate properties are queued for compliance review; "
            f"{self.open_conflict_count} record conflicts are open, and "
            f"{self.resolved_this_period} were resolved this period."
        )


def stable_key(*parts: str) -> str:
    raw = "|".join(part.strip().lower() for part in parts if part)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def source_name(source_id: str) -> str:
    return SOURCE_LABELS.get(source_id, source_id)


def source_short_name(source_id: str) -> str:
    return SOURCE_SHORT_LABELS.get(source_id, source_id)


def _is_private_label(label: str) -> bool:
    normalized = label.replace(" ", "_").replace("-", "_").lower()
    return any(marker in normalized for marker in PRIVATE_FIELD_MARKERS)


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def scrub_source_records(records: Any) -> list[dict[str, Any]]:
    """Normalize index source records and drop buyer/contact/private fields."""

    if not isinstance(records, list):
        return []

    normalized_records: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        source_id = _string(record.get("sourceId") or record.get("source_id") or record.get("source"))
        if not source_id:
            continue
        source_record_id = _string(
            record.get("sourceRecordId") or record.get("source_record_id") or record.get("id")
        )
        observed_at = _string(
            record.get("observedAt") or record.get("observed_at") or timezone.localdate().isoformat()
        )
        facts = []
        raw_facts = record.get("facts") if isinstance(record.get("facts"), list) else []
        for fact in raw_facts:
            if not isinstance(fact, dict):
                continue
            label = _string(fact.get("label") or fact.get("key") or fact.get("name"))
            if not label or _is_private_label(label):
                continue
            facts.append(
                {
                    "label": label,
                    "value": _string(fact.get("value")),
                }
            )
        normalized_records.append(
            {
                "sourceId": source_id,
                "sourceRecordId": source_record_id or f"{source_id}:{len(normalized_records) + 1}",
                "observedAt": observed_at,
                "facts": facts,
            }
        )
    return normalized_records


def _is_home(property_obj: Property) -> bool:
    text = " ".join(
        [
            property_obj.property_class or "",
            property_obj.land_use or "",
            property_obj.program or "",
        ]
    ).lower()
    if "vacant" in text and "home" not in text and "residential" not in text:
        return False
    if any(term in text for term in ["home", "residential", "single family", "dwelling"]):
        return True
    return bool(property_obj.program)


def coverage_summary(properties: QuerySet[Property] | None = None) -> CoverageSummary:
    property_rows = list(properties if properties is not None else Property.objects.all())
    source_ids = {
        record.get("sourceId")
        for property_obj in property_rows
        for record in (property_obj.sources if isinstance(property_obj.sources, list) else [])
        if isinstance(record, dict) and record.get("sourceId")
    }
    return CoverageSummary(
        tracked_property_count=len(property_rows),
        parcels_indexed=sum(
            1
            for property_obj in property_rows
            if isinstance(property_obj.sources, list) and len(property_obj.sources) > 0
        ),
        home_count=sum(1 for property_obj in property_rows if _is_home(property_obj)),
        active_program_count=sum(1 for property_obj in property_rows if bool(property_obj.program)),
        source_count=len(source_ids),
        open_conflict_count=SourceConflict.objects.filter(status="open").count(),
        candidate_count=CandidateProperty.objects.filter(status="queued").count(),
    )


def _period_bounds(
    start: date | None,
    end: date | None,
) -> tuple[datetime | None, datetime | None]:
    if start is None or end is None:
        return None, None
    return (
        timezone.make_aware(datetime.combine(start, time.min)),
        timezone.make_aware(datetime.combine(end, time.max)),
    )


def discovery_examples(limit: int = 3) -> list[DiscoveryExample]:
    rows = CandidateProperty.objects.filter(status="queued").order_by("parcel_id", "id")[
        : max(0, limit)
    ]
    return [
        DiscoveryExample(
            parcel_id=row.parcel_id,
            address=row.address,
            reason=row.reason,
            evidence=row.evidence,
        )
        for row in rows
    ]


def intelligence_report_snapshot(
    *,
    start: date | None = None,
    end: date | None = None,
    prepared_on: date | None = None,
) -> PropertyIntelligenceReportSnapshot:
    coverage = coverage_summary()
    start_dt, end_dt = _period_bounds(start, end)
    resolved_qs = SourceConflict.objects.filter(status="resolved")
    if start_dt is not None and end_dt is not None:
        resolved_qs = resolved_qs.filter(updated_at__range=(start_dt, end_dt))
    return PropertyIntelligenceReportSnapshot(
        prepared_on=prepared_on or timezone.localdate(),
        tracked_property_count=coverage.tracked_property_count,
        parcels_indexed=coverage.parcels_indexed,
        home_count=coverage.home_count,
        active_program_count=coverage.active_program_count,
        source_count=coverage.source_count,
        open_conflict_count=coverage.open_conflict_count,
        candidate_count=coverage.candidate_count,
        resolved_this_period=resolved_qs.count(),
        examples=discovery_examples(limit=3),
    )


def render_share_package_text(snapshot: PropertyIntelligenceReportSnapshot) -> str:
    lines = [
        "GCLBA Property Intelligence Share Package",
        f"Prepared {snapshot.prepared_on.isoformat()}",
        "",
        "What it does",
        (
            'The property portal answers "what is this parcel." The cross-source '
            'property record index answers "is this program property doing what its '
            'agreement requires, and which records disagree."'
        ),
        "",
        "Headline count",
        snapshot.coverage_line.removeprefix("Coverage: "),
        "",
        "Discoveries",
        snapshot.discoveries_line.removeprefix("Discoveries: "),
        "",
        "Example discoveries",
    ]
    if snapshot.examples:
        for example in snapshot.examples:
            label = example.address or "address pending"
            evidence = f" Evidence: {example.evidence}" if example.evidence else ""
            lines.append(f"- {example.parcel_id}: {label}. {example.reason}.{evidence}")
    else:
        lines.append(
            "- No candidate-property discoveries are queued yet. Import source-conflict "
            "data to populate this section with parcel-specific examples."
        )
    return "\n".join(lines)


def render_share_package_html(snapshot: PropertyIntelligenceReportSnapshot) -> str:
    esc = html.escape
    examples = snapshot.examples
    example_items = (
        "".join(
            "<li>"
            f"<strong>{esc(example.parcel_id)}</strong>: "
            f"{esc(example.address or 'address pending')}. "
            f"{esc(example.reason)}"
            f"{' Evidence: ' + esc(example.evidence) if example.evidence else ''}"
            "</li>"
            for example in examples
        )
        if examples
        else (
            "<li>No candidate-property discoveries are queued yet. Import "
            "source-conflict data to populate this section with parcel-specific "
            "examples.</li>"
        )
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>GCLBA Property Intelligence Share Package</title>"
        "<style>body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;"
        "color:#17231f;max-width:760px;margin:2rem auto;padding:0 1rem}"
        "h1{font-size:1.4rem;margin:0 0 .25rem}h2{font-size:1rem;"
        "border-bottom:1px solid #cbd8d3;padding-bottom:.2rem;margin-top:1.3rem}"
        ".meta{color:#4f625c}li{margin:.2rem 0}</style></head><body>"
        "<h1>GCLBA Property Intelligence Share Package</h1>"
        f"<p class='meta'>Prepared {snapshot.prepared_on.isoformat()}</p>"
        "<h2>What it does</h2>"
        "<p>The property portal answers &quot;what is this parcel.&quot; The "
        "cross-source property record index answers &quot;is this program property "
        "doing what its agreement requires, and which records disagree.&quot;</p>"
        "<h2>Headline count</h2>"
        f"<p>{esc(snapshot.coverage_line.removeprefix('Coverage: '))}</p>"
        "<h2>Discoveries</h2>"
        f"<p>{esc(snapshot.discoveries_line.removeprefix('Discoveries: '))}</p>"
        "<h2>Example discoveries</h2>"
        f"<ul>{example_items}</ul>"
        "</body></html>"
    )


def render_share_package_pdf(snapshot: PropertyIntelligenceReportSnapshot) -> bytes:
    text = render_share_package_text(snapshot)
    lines: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw_line, width=88) or [""])
    return _simple_text_pdf(lines[:54])


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _simple_text_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 760 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    chunks = [b"%PDF-1.4\n"]
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{idx} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    xref = [b"xref\n", f"0 {len(objects) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        b"trailer\n"
        + f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii")
        + b"startxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF\n"
    )
    return b"".join([*chunks, *xref, trailer])


def parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return timezone.localdate()
    return timezone.localdate()


def _money(value: Any) -> float | None:
    text = _string(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _integer(value: Any) -> int | None:
    text = _string(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _boolean(value: Any) -> bool | None:
    text = _string(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _date_text(value: Any) -> str:
    text = _string(value).strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return text[:20]


def _fact_value(dossier: dict[str, Any], labels: tuple[str, ...]) -> str:
    wanted = {label.lower() for label in labels}
    for record in dossier.get("records") or dossier.get("sources") or []:
        if not isinstance(record, dict):
            continue
        for fact in record.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            label = _string(fact.get("label") or fact.get("key") or fact.get("name"))
            if label.lower() in wanted:
                value = _string(fact.get("value")).strip()
                if value:
                    return value
    return ""


def _property_defaults_from_dossier(dossier: dict[str, Any]) -> dict[str, Any]:
    canonical = dossier.get("canonical") if isinstance(dossier.get("canonical"), dict) else {}
    address = _string(dossier.get("address")).strip()
    program = _string(canonical.get("program")).strip() or _fact_value(
        dossier,
        ("Program", "program", "FH_Status", "2023_Foreclosures_Status"),
    )
    land_use = _string(canonical.get("structure")).strip() or _fact_value(
        dossier,
        ("Structure", "ClassType", "Tbl_Prop_Cat_Meaning"),
    )
    condition = _string(canonical.get("condition")).strip() or _fact_value(
        dossier,
        ("Condition", "Regrid condition", "Tbl_Prop_Cat_Meaning"),
    )
    assessed_value = _money(canonical.get("assessedValue"))
    if assessed_value is None:
        assessed_value = _money(
            _fact_value(
                dossier,
                ("Assessed Value", "Assessment", "CURRENT SEV", "SEV", "Parc_Prop_Assmt"),
            )
        )
    owner = _string(canonical.get("owner")).strip() or _fact_value(
        dossier,
        ("Owner of record", "Owner", "OwnName", "TaxName"),
    )
    property_class = _fact_value(
        dossier,
        ("Property Class", "PropClass", "Parc_Prop_Class", "ClassType"),
    )
    homeowner_exemption = _boolean(_fact_value(dossier, ("Homeowner exemption",)))
    outreach_attempts = _integer(_fact_value(dossier, ("Outreach attempts",)))

    return {
        "address": address,
        "address_key": build_address_key(address) if address else "",
        "program": program,
        "land_use": land_use,
        "sources": scrub_source_records(dossier.get("records") or dossier.get("sources")),
        "owner_of_record": owner,
        "assessed_value": assessed_value,
        "property_class": property_class,
        "regrid_condition": condition,
        "compliance_status": _fact_value(dossier, ("Compliance", "complianceStatus")),
        "finding": _fact_value(dossier, ("Finding", "finding")),
        "detection_label": _fact_value(dossier, ("Detection label", "detectionLabel")),
        "closing_date": _date_text(_fact_value(dossier, ("Date of sale", "Sale Date", "closingDate"))),
        "purchase_type": _fact_value(dossier, ("Purchase type",)),
        "tax_status": _fact_value(dossier, ("Tax",)),
        "forfeiture_status": _fact_value(dossier, ("Forfeiture status",)),
        "forfeiture_status_year": _fact_value(dossier, ("Forfeiture year", "Parc_Forc_Year")),
        "homeowner_exemption": homeowner_exemption,
        "outreach_attempts": outreach_attempts,
        "latitude": _money(_fact_value(dossier, ("Latitude", "latitude"))),
        "longitude": _money(_fact_value(dossier, ("Longitude",))),
    }


def _apply_property_defaults(property_obj: Property, defaults: dict[str, Any], *, now) -> None:
    for field in (
        "address",
        "address_key",
        "program",
        "land_use",
        "owner_of_record",
        "property_class",
        "regrid_condition",
        "compliance_status",
        "finding",
        "detection_label",
        "closing_date",
        "purchase_type",
        "tax_status",
        "forfeiture_status",
        "forfeiture_status_year",
    ):
        value = defaults.get(field)
        if value not in (None, ""):
            setattr(property_obj, field, value)
    for field in ("assessed_value", "latitude", "longitude", "homeowner_exemption", "outreach_attempts"):
        value = defaults.get(field)
        if value is not None:
            setattr(property_obj, field, value)
    property_obj.sources = defaults["sources"]
    property_obj.updated_at = now


def import_property_intelligence(payload: dict[str, Any]) -> dict[str, int]:
    """Import dossiers/conflicts/candidates from the private index output."""

    parcels = payload.get("parcels", payload if isinstance(payload, list) else [])
    if not isinstance(parcels, list):
        parcels = []

    property_rows: dict[str, dict[str, Any]] = {}
    for item in parcels:
        if not isinstance(item, dict):
            continue
        dossier = item.get("dossier") if isinstance(item.get("dossier"), dict) else item
        parcel_id = _string(dossier.get("parcelId") or dossier.get("parcel_id"))
        if not parcel_id or len(parcel_id) > 20:
            continue
        property_rows[parcel_id] = _property_defaults_from_dossier(dossier)

    now = timezone.now()
    parcel_ids = list(property_rows.keys())
    property_by_parcel: dict[str, Property] = {}
    for property_obj in Property.objects.filter(parcel_id__in=parcel_ids).order_by("id"):
        property_by_parcel.setdefault(property_obj.parcel_id, property_obj)

    create_properties: list[Property] = []
    update_properties: list[Property] = []
    for parcel_id, defaults in property_rows.items():
        property_obj = property_by_parcel.get(parcel_id)
        if property_obj is None:
            property_obj = Property(parcel_id=parcel_id)
            for field, value in defaults.items():
                if value is not None:
                    setattr(property_obj, field, value)
            create_properties.append(property_obj)
            property_by_parcel[parcel_id] = property_obj
        else:
            _apply_property_defaults(property_obj, defaults, now=now)
            update_properties.append(property_obj)

    property_update_fields = [
        "address",
        "address_key",
        "program",
        "land_use",
        "sources",
        "owner_of_record",
        "assessed_value",
        "property_class",
        "regrid_condition",
        "compliance_status",
        "finding",
        "detection_label",
        "closing_date",
        "purchase_type",
        "tax_status",
        "forfeiture_status",
        "forfeiture_status_year",
        "homeowner_exemption",
        "outreach_attempts",
        "latitude",
        "longitude",
        "updated_at",
    ]

    with transaction.atomic():
        if create_properties:
            Property.objects.bulk_create(create_properties, batch_size=1000)
        if update_properties:
            Property.objects.bulk_update(update_properties, property_update_fields, batch_size=1000)

    property_by_parcel = {}
    for property_obj in Property.objects.filter(parcel_id__in=parcel_ids).order_by("id"):
        property_by_parcel.setdefault(property_obj.parcel_id, property_obj)

    conflict_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_conflict in payload.get("conflicts", []):
        if not isinstance(raw_conflict, dict):
            continue
        parcel_id = _string(raw_conflict.get("parcelId") or raw_conflict.get("parcel_id"))
        kind = _string(raw_conflict.get("kind"))
        title = _string(raw_conflict.get("title"))
        if not parcel_id or not kind or not title:
            continue
        external_key = _string(raw_conflict.get("id") or raw_conflict.get("externalKey"))
        if not external_key:
            external_key = stable_key(parcel_id, kind, title)
        source = _string(raw_conflict.get("source") or "gclba-index")
        conflict_rows[(source, external_key)] = {
            "property": property_by_parcel.get(parcel_id),
            "parcel_id": parcel_id,
            "source": source,
            "external_key": external_key,
            "kind": kind,
            "severity": _string(raw_conflict.get("severity") or "review"),
            "title": title,
            "plain_language": _string(
                raw_conflict.get("plainLanguage") or raw_conflict.get("plain_language")
            ),
            "evidence": [
                _string(value)
                for value in raw_conflict.get("evidence", [])
                if isinstance(value, str)
            ],
            "observed_at": parse_date(raw_conflict.get("observedAt") or raw_conflict.get("observed_at")),
            "status": _string(raw_conflict.get("status") or "open"),
            "metadata": raw_conflict.get("metadata") if isinstance(raw_conflict.get("metadata"), dict) else {},
        }

    existing_conflicts: dict[tuple[str, str], SourceConflict] = {}
    conflict_keys = [key for _, key in conflict_rows]
    for conflict in SourceConflict.objects.filter(external_key__in=conflict_keys).order_by("id"):
        existing_conflicts.setdefault((conflict.source, conflict.external_key), conflict)

    create_conflicts: list[SourceConflict] = []
    update_conflicts: list[SourceConflict] = []
    for key, defaults in conflict_rows.items():
        conflict = existing_conflicts.get(key)
        if conflict is None:
            create_conflicts.append(SourceConflict(**defaults))
            continue
        for field, value in defaults.items():
            setattr(conflict, field, value)
        conflict.updated_at = now
        update_conflicts.append(conflict)

    with transaction.atomic():
        if create_conflicts:
            SourceConflict.objects.bulk_create(create_conflicts, batch_size=1000)
        if update_conflicts:
            SourceConflict.objects.bulk_update(
                update_conflicts,
                [
                    "property",
                    "parcel_id",
                    "kind",
                    "severity",
                    "title",
                    "plain_language",
                    "evidence",
                    "observed_at",
                    "status",
                    "metadata",
                    "updated_at",
                ],
                batch_size=1000,
            )

    conflict_by_key: dict[str, SourceConflict] = {}
    for conflict in SourceConflict.objects.filter(external_key__in=conflict_keys).order_by("id"):
        conflict_by_key.setdefault(conflict.external_key, conflict)

    candidate_rows: dict[str, dict[str, Any]] = {}
    for raw_candidate in payload.get("candidates", payload.get("candidateProperties", [])):
        if not isinstance(raw_candidate, dict):
            continue
        parcel_id = _string(raw_candidate.get("parcelId") or raw_candidate.get("parcel_id"))
        reason = _string(raw_candidate.get("reason"))
        if not parcel_id or not reason:
            continue
        external_key = _string(raw_candidate.get("id") or raw_candidate.get("externalKey"))
        if not external_key:
            external_key = stable_key(parcel_id, reason)
        conflict_key = _string(raw_candidate.get("sourceConflictId") or raw_candidate.get("source_conflict_id"))
        evidence = raw_candidate.get("evidence")
        if isinstance(evidence, list):
            evidence = " ".join(_string(value) for value in evidence if isinstance(value, str))
        candidate_rows[external_key] = {
            "property": property_by_parcel.get(parcel_id),
            "source_conflict": conflict_by_key.get(conflict_key),
            "parcel_id": parcel_id,
            "external_key": external_key,
            "address": _string(raw_candidate.get("address")),
            "reason": reason,
            "evidence": _string(evidence),
            "status": _string(raw_candidate.get("status") or "queued"),
            "metadata": raw_candidate.get("metadata") if isinstance(raw_candidate.get("metadata"), dict) else {},
        }

    existing_candidates: dict[str, CandidateProperty] = {}
    candidate_keys = list(candidate_rows.keys())
    for candidate in CandidateProperty.objects.filter(external_key__in=candidate_keys).order_by("id"):
        existing_candidates.setdefault(candidate.external_key, candidate)

    create_candidates: list[CandidateProperty] = []
    update_candidates: list[CandidateProperty] = []
    for key, defaults in candidate_rows.items():
        candidate = existing_candidates.get(key)
        if candidate is None:
            create_candidates.append(CandidateProperty(**defaults))
            continue
        for field, value in defaults.items():
            setattr(candidate, field, value)
        candidate.updated_at = now
        update_candidates.append(candidate)

    with transaction.atomic():
        if create_candidates:
            CandidateProperty.objects.bulk_create(create_candidates, batch_size=1000)
        if update_candidates:
            CandidateProperty.objects.bulk_update(
                update_candidates,
                [
                    "property",
                    "source_conflict",
                    "parcel_id",
                    "address",
                    "reason",
                    "evidence",
                    "status",
                    "metadata",
                    "updated_at",
                ],
                batch_size=1000,
            )

    return {
        "properties": len(property_rows),
        "conflicts": len(conflict_rows),
        "candidates": len(candidate_rows),
    }
