from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from tracker.models import Communication, Document, Property
from tracker.services.workflow import compute_property_timing, render_template_preview


@dataclass(frozen=True)
class GeneratedArtifact:
    document: Document
    path: Path


@dataclass(frozen=True)
class PreparedMailPacket:
    property_obj: Property
    action: str
    preview: dict[str, Any]


def list_property_documents(property_id: int) -> list[Document]:
    return list(
        Document.objects.filter(property_id=property_id)
        .select_related("communication")
        .order_by("-created_at", "-id")
    )


def create_communication_artifacts(property_obj: Property, communication: Communication) -> list[Document]:
    if communication.status not in {"sent", "delivered"}:
        return []

    timestamp = timezone.localtime(communication.sent_at or timezone.now())
    stamp = timestamp.strftime("%Y%m%d-%H%M%S")
    action_slug = _slugify(communication.action or communication.method or "communication")
    base_name = f"{stamp}-{action_slug}"

    proof_text = _communication_proof_text(property_obj, communication)
    proof_document = _write_text_document(
        property_obj=property_obj,
        communication=communication,
        category="communication_proof",
        filename=f"{base_name}-proof.txt",
        content=proof_text,
        metadata={
            "kind": "communication_proof",
            "action": communication.action,
            "status": communication.status,
            "method": communication.method,
        },
    ).document

    audit_payload = {
        "kind": "communication_audit",
        "propertyId": property_obj.id,
        "communicationId": communication.id,
        "action": communication.action,
        "status": communication.status,
        "method": communication.method,
        "direction": communication.direction,
        "recipientEmail": communication.recipient_email,
        "templateName": communication.template_name,
        "providerMessageId": communication.provider_message_id,
        "subject": communication.subject,
        "bodyHash": communication.body_hash,
        "approvedAt": communication.approved_at.isoformat() if communication.approved_at else None,
        "sentAt": communication.sent_at.isoformat() if communication.sent_at else None,
        "dateSent": communication.date_sent.isoformat() if communication.date_sent else None,
        "createdAt": communication.created_at.isoformat() if communication.created_at else None,
    }
    audit_document = _write_json_document(
        property_obj=property_obj,
        communication=communication,
        category="communication_audit",
        filename=f"{base_name}-audit.json",
        payload=audit_payload,
        metadata={
            "kind": "communication_audit",
            "action": communication.action,
            "status": communication.status,
        },
    ).document

    return [proof_document, audit_document]


def create_mail_packet_bundle(
    properties: Iterable[Property],
    *,
    action: str | None = None,
    template_slug: str | None = None,
) -> dict[str, Any]:
    generated_letters: list[Document] = []
    generated_audits: list[Document] = []
    prepared_packets: list[PreparedMailPacket] = []
    packet_entries: list[dict[str, Any]] = []
    packet_sections: list[str] = []
    property_ids: list[int] = []
    now = timezone.localtime(timezone.now())
    stamp = now.strftime("%Y%m%d-%H%M%S")

    for property_obj in properties:
        timing = compute_property_timing(property_obj)
        effective_action = action or _default_packet_action(timing)
        preview = render_template_preview(
            property_obj,
            action=effective_action,
            template_slug=template_slug,
        )
        prepared_packets.append(
            PreparedMailPacket(
                property_obj=property_obj,
                action=effective_action,
                preview=preview,
            )
        )
        packet_entries.append(
            {
                "propertyId": property_obj.id,
                "address": property_obj.address,
                "parcelId": property_obj.parcel_id,
                "buyerName": property_obj.buyer_name,
                "program": property_obj.program,
                "action": effective_action,
                "dueDate": preview["timing"].get("dueDate"),
                "daysOverdue": preview["timing"].get("daysOverdue"),
                "template": preview["template"],
            }
        )
        packet_sections.append(_mail_letter_html(property_obj, preview))
        property_ids.append(property_obj.id)

    for prepared in prepared_packets:
        property_obj = prepared.property_obj
        effective_action = prepared.action
        preview = prepared.preview
        base_name = f"{stamp}-{property_obj.id}-{_slugify(effective_action)}"
        letter_document = _write_text_document(
            property_obj=property_obj,
            communication=None,
            category="mail_packet",
            filename=f"{base_name}-letter.html",
            content=_mail_letter_html_document(property_obj, preview),
            mime_type="text/html",
            metadata={
                "kind": "mail_packet",
                "action": effective_action,
                "template": preview["template"]["slug"],
                "missingVariables": preview["missingVariables"],
            },
        ).document
        generated_letters.append(letter_document)

        audit_payload = {
            "kind": "mail_packet_audit",
            "propertyId": property_obj.id,
            "action": effective_action,
            "template": preview["template"],
            "timing": preview["timing"],
            "missingVariables": preview["missingVariables"],
            "generatedAt": now.isoformat(),
            "notes": [
                "Packet generated for manual print and mail review.",
                "Confirm buyer mailing address before sending.",
            ],
        }
        audit_document = _write_json_document(
            property_obj=property_obj,
            communication=None,
            category="mail_audit",
            filename=f"{base_name}-audit.json",
            payload=audit_payload,
            metadata={
                "kind": "mail_packet_audit",
                "action": effective_action,
                "template": preview["template"]["slug"],
            },
        ).document
        generated_audits.append(audit_document)

    batch_document = _write_text_document(
        property_obj=None,
        communication=None,
        category="mail_packet_batch",
        filename=f"{stamp}-mail-packet-batch.html",
        content=_mail_packet_batch_html(packet_sections),
        mime_type="text/html",
        metadata={
            "kind": "mail_packet_batch",
            "propertyIds": property_ids,
            "count": len(property_ids),
        },
    ).document

    manifest_document = _write_json_document(
        property_obj=None,
        communication=None,
        category="mail_packet_batch_manifest",
        filename=f"{stamp}-mail-packet-manifest.json",
        payload={
            "kind": "mail_packet_batch_manifest",
            "generatedAt": now.isoformat(),
            "propertyIds": property_ids,
            "entries": packet_entries,
        },
        metadata={
            "kind": "mail_packet_batch_manifest",
            "propertyIds": property_ids,
            "count": len(property_ids),
        },
    ).document

    return {
        "batch_document": batch_document,
        "manifest_document": manifest_document,
        "letters": generated_letters,
        "audits": generated_audits,
    }


def _write_text_document(
    *,
    property_obj: Property | None,
    communication: Communication | None,
    category: str,
    filename: str,
    content: str,
    mime_type: str = "text/plain",
    metadata: dict[str, Any] | None = None,
) -> GeneratedArtifact:
    relative_path = _document_relative_path(category, property_obj, filename)
    absolute_path = _document_absolute_path(relative_path)
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_text(content, encoding="utf-8")
    document = Document.objects.create(
        property=property_obj,
        communication=communication,
        filename=filename,
        storage_key=relative_path.as_posix(),
        storage_url=_document_url(relative_path),
        mime_type=mime_type,
        size_bytes=absolute_path.stat().st_size,
        category=category,
        slot="generated",
        metadata=metadata or {},
    )
    return GeneratedArtifact(document=document, path=absolute_path)


def _write_json_document(
    *,
    property_obj: Property | None,
    communication: Communication | None,
    category: str,
    filename: str,
    payload: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> GeneratedArtifact:
    return _write_text_document(
        property_obj=property_obj,
        communication=communication,
        category=category,
        filename=filename,
        content=json.dumps(payload, indent=2, sort_keys=True),
        mime_type="application/json",
        metadata=metadata,
    )


def _document_relative_path(category: str, property_obj: Property | None, filename: str) -> Path:
    if property_obj is not None:
        return Path("generated_documents") / category / str(property_obj.id) / filename
    return Path("generated_documents") / category / filename


def _document_absolute_path(relative_path: Path) -> Path:
    return Path(settings.MEDIA_ROOT) / relative_path


def _document_url(relative_path: Path) -> str:
    media_base = settings.MEDIA_URL.rstrip("/")
    return f"{media_base}/{relative_path.as_posix()}"


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "document"


def _default_packet_action(timing: Any) -> str:
    if isinstance(timing, dict):
        return timing.get("currentAction") or timing.get("nextAction") or "ATTEMPT_1"
    current_action = getattr(timing, "current_action", "")
    next_action = getattr(timing, "next_action", None)
    return current_action if current_action and current_action != "NOT_DUE_YET" else (next_action or "ATTEMPT_1")


def _communication_proof_text(property_obj: Property, communication: Communication) -> str:
    lines = [
        "GCLBA Compliance Communication Proof",
        "",
        f"Property: {property_obj.address}",
        f"Parcel ID: {property_obj.parcel_id}",
        f"Buyer: {property_obj.buyer_name}",
        f"Program: {property_obj.program}",
        f"Method: {communication.method}",
        f"Action: {communication.action}",
        f"Status: {communication.status}",
        f"Recipient Email: {communication.recipient_email}",
        f"Date Sent: {communication.date_sent.isoformat() if communication.date_sent else ''}",
        f"Sent At: {communication.sent_at.isoformat() if communication.sent_at else ''}",
        f"Approved At: {communication.approved_at.isoformat() if communication.approved_at else ''}",
        f"Template: {communication.template_name}",
        f"Provider Message ID: {communication.provider_message_id}",
        f"Body Hash: {communication.body_hash}",
        "",
        f"Subject: {communication.subject}",
        "",
        communication.body or "",
    ]
    return "\n".join(lines)


def _mail_letter_html_document(property_obj: Property, preview: dict[str, Any]) -> str:
    return _mail_packet_batch_html([_mail_letter_html(property_obj, preview)])


def _mail_packet_batch_html(sections: list[str]) -> str:
    body = "\n<hr class=\"packet-break\" />\n".join(sections)
    return (
        "<!doctype html>"
        "<html lang=\"en\">"
        "<head>"
        "<meta charset=\"utf-8\" />"
        "<title>Compliance Mail Packet</title>"
        "<style>"
        "body { font-family: Georgia, serif; color: #1f2937; margin: 0; background: #f7f5ef; }"
        ".packet-shell { max-width: 960px; margin: 0 auto; padding: 32px 24px 64px; }"
        ".letter { background: #ffffff; border: 1px solid #d6d3d1; padding: 32px; margin-bottom: 32px; box-shadow: 0 12px 24px rgba(15, 23, 42, 0.06); }"
        ".eyebrow { font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: #166534; margin-bottom: 12px; }"
        ".meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 24px; margin: 18px 0 24px; font-size: 14px; }"
        ".subject { font-size: 20px; font-weight: 700; margin: 24px 0 12px; }"
        ".body { white-space: pre-wrap; line-height: 1.65; font-size: 15px; }"
        ".alert { margin-top: 18px; padding: 12px 14px; background: #fff7ed; border: 1px solid #fdba74; color: #9a3412; font-size: 13px; }"
        ".packet-break { border: 0; border-top: 1px dashed #cbd5e1; margin: 28px 0; }"
        "@media print { body { background: #ffffff; } .packet-shell { max-width: none; padding: 0; } .letter { box-shadow: none; border: 0; page-break-after: always; margin: 0; } .packet-break { display: none; } }"
        "</style>"
        "</head>"
        "<body><div class=\"packet-shell\">"
        f"{body}"
        "</div></body></html>"
    )


def _mail_letter_html(property_obj: Property, preview: dict[str, Any]) -> str:
    timing = preview["timing"]
    action_label = timing.get("currentAction") or preview["action"]
    return (
        "<section class=\"letter\">"
        "<div class=\"eyebrow\">Compliance Mail Packet</div>"
        f"<h1>{escape(property_obj.address or '')}</h1>"
        "<div class=\"meta-grid\">"
        f"<div><strong>Parcel ID:</strong> {escape(property_obj.parcel_id or 'Not listed')}</div>"
        f"<div><strong>Buyer:</strong> {escape(property_obj.buyer_name or 'Not listed')}</div>"
        f"<div><strong>Program:</strong> {escape(property_obj.program or 'Not listed')}</div>"
        f"<div><strong>Action:</strong> {escape(str(action_label or 'Not available'))}</div>"
        f"<div><strong>Due Date:</strong> {escape(str(timing.get('dueDate') or 'Not available'))}</div>"
        f"<div><strong>Days Overdue:</strong> {escape(str(timing.get('daysOverdue') or 0))}</div>"
        "</div>"
        f"<div class=\"subject\">{escape(preview['subject'])}</div>"
        f"<div class=\"body\">{escape(preview['body'])}</div>"
        "<div class=\"alert\">"
        "Manual mail step: confirm the correct mailing address before printing and sending this packet. "
        "This generated packet is a draft artifact for staff review."
        "</div>"
        "</section>"
    )
