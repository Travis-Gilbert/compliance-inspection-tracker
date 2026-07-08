from datetime import date

import strawberry
import strawberry_django
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from strawberry.file_uploads import Upload
from strawberry.scalars import JSON
from strawberry_django.optimizer import DjangoOptimizerExtension
from strawberry.tools import merge_types

from tracker.graphql_context import ComplianceQuery, ContextQuery

from tracker.models import (
    ActionItem,
    Buyer,
    CandidateProperty,
    Communication,
    Document,
    EmailTemplate,
    Program,
    Property,
    PropertyPhoto,
    SourceConflict,
)
from tracker.services.property_intelligence import coverage_summary, source_name
from tracker.services.workflow import (
    apply_communication_rollups,
    build_action_queue,
    prepare_workflow_communication,
    render_template_preview,
)
from tracker.services.workflow_documents import (
    create_communication_artifacts,
    list_property_documents,
    save_uploaded_property_document,
)


@strawberry_django.type(
    Buyer,
    fields=[
        "id",
        "full_name",
        "email",
        "phone",
        "organization",
        "status",
        "flags",
        "created_at",
        "updated_at",
    ],
)
class BuyerType:
    pass


@strawberry_django.type(
    Program,
    fields=[
        "id",
        "key",
        "label",
        "cadence",
        "schedule",
        "grace_days",
        "required_uploads",
        "required_docs",
        "is_active",
        "created_at",
        "updated_at",
    ],
)
class ProgramType:
    pass


@strawberry_django.type(
    PropertyPhoto,
    fields=[
        "id",
        "side",
        "original_filename",
        "caption",
        "source",
        "is_primary",
        "photo_date",
        "photo_latitude",
        "photo_longitude",
        "distance_from_property_meters",
        "proximity_status",
        "metadata",
        "uploaded_at",
        "updated_at",
    ],
)
class PropertyPhotoType:
    property_id: int
    image_url: str

    @strawberry_django.field(only=["property_id"])
    def property_id(self, root: PropertyPhoto) -> int:
        return root.property_id

    @strawberry_django.field(only=["image"])
    def image_url(self, root: PropertyPhoto) -> str:
        return root.public_url


@strawberry_django.type(
    Document,
    fields=[
        "id",
        "filename",
        "storage_key",
        "storage_url",
        "mime_type",
        "size_bytes",
        "category",
        "slot",
        "metadata",
        "created_at",
    ],
)
class DocumentType:
    property_id: int | None
    communication_id: int | None

    @strawberry_django.field(only=["property_id"])
    def property_id(self, root: Document) -> int | None:
        return root.property_id

    @strawberry_django.field(only=["communication_id"])
    def communication_id(self, root: Document) -> int | None:
        return root.communication_id


@strawberry_django.type(
    Communication,
    fields=[
        "id",
        "method",
        "direction",
        "action",
        "template_name",
        "status",
        "recipient_email",
        "date_sent",
        "sent_at",
        "approved_at",
        "provider_message_id",
        "subject",
        "body",
        "response_received",
        "response_date",
        "response_notes",
        "created_at",
    ],
)
class CommunicationType:
    property_id: int
    buyer_id: int | None
    template_id: int | None

    @strawberry_django.field(only=["property_id"])
    def property_id(self, root: Communication) -> int:
        return root.property_id

    @strawberry_django.field(only=["buyer_id"])
    def buyer_id(self, root: Communication) -> int | None:
        return root.buyer_id

    @strawberry_django.field(only=["template_id"])
    def template_id(self, root: Communication) -> int | None:
        return root.template_id


@strawberry_django.type(
    ActionItem,
    fields=[
        "id",
        "action",
        "status",
        "due_date",
        "days_overdue",
        "enforcement_level",
        "priority",
        "reasons",
        "source",
        "completed_at",
        "created_at",
        "updated_at",
    ],
)
class ActionItemType:
    property_id: int

    @strawberry_django.field(only=["property_id"])
    def property_id(self, root: ActionItem) -> int:
        return root.property_id


@strawberry_django.type(
    Property,
    fields=[
        "id",
        "address",
        "address_key",
        "parcel_id",
        "buyer_name",
        "email",
        "organization",
        "program",
        "closing_date",
        "commitment",
        "purchase_type",
        "compliance_1st_attempt",
        "compliance_2nd_attempt",
        "latitude",
        "longitude",
        "formatted_address",
        "geocoded_at",
        "streetview_path",
        "streetview_date",
        "streetview_available",
        "streetview_historical_path",
        "streetview_historical_date",
        "historical_imagery_checked_at",
        "satellite_path",
        "imagery_fetched_at",
        "detection_score",
        "detection_label",
        "detection_details",
        "detection_ran_at",
        "finding",
        "notes",
        "reviewed_at",
        "reviewed_by",
        "compliance_status",
        "tax_status",
        "last_tax_payment",
        "assessed_value",
        "taxable_value",
        "owner_of_record",
        "property_class",
        "land_use",
        "forfeiture_status",
        "forfeiture_status_year",
        "boundary_geojson",
        "homeowner_exemption",
        "outreach_attempts",
        "last_outreach_date",
        "last_outreach_method",
        "regrid_condition",
        "portal_survey_date",
        "import_batch",
        "created_at",
        "updated_at",
    ],
)
class PropertyType:
    buyer: BuyerType | None
    program_record: ProgramType | None
    communication_count: int
    manual_compliance_outcome: str
    photos: list[PropertyPhotoType]
    documents: list[DocumentType]
    action_items: list[ActionItemType]
    tax_amount_owed: str | None
    photo_summary: JSON

    @strawberry_django.field
    def communication_count(self, root: Property) -> int:
        return getattr(root, "communication_count", root.communications.count()) or 0

    @strawberry_django.field(
        only=["program", "finding"],
    )
    def manual_compliance_outcome(self, root: Property) -> str:
        return root.manual_compliance_outcome

    @strawberry_django.field(only=["tax_amount_owed"])
    def tax_amount_owed(self, root: Property) -> str | None:
        if root.tax_amount_owed is None:
            return None
        return str(root.tax_amount_owed)

    @strawberry_django.field
    def photo_summary(self, root: Property) -> JSON:
        photos = list(root.photos.all())
        before_count = sum(photo.side == "before" for photo in photos)
        after_count = sum(photo.side == "after" for photo in photos)
        return {
            "beforeCount": before_count,
            "afterCount": after_count,
            "totalCount": len(photos),
            "hasBefore": before_count > 0,
            "hasAfter": after_count > 0,
            "isComplete": before_count > 0 and after_count > 0,
        }


@strawberry.type
class WorkflowTemplatePreview:
    subject: str
    body: str
    recipient_email: str
    recipient_name: str
    timing: JSON
    template: JSON


@strawberry.type
class ActionQueueItem:
    property_id: int
    address: str
    parcel_id: str
    buyer_name: str
    email: str
    action: str
    status: str
    due_date: str | None
    days_overdue: int
    enforcement_level: int
    priority: int
    reasons: list[str]
    source: str


@strawberry.type
class ActionQueueGroup:
    action: str
    count: int
    items: list[ActionQueueItem]


@strawberry.type
class ActionQueuePayload:
    as_of: date
    groups: list[ActionQueueGroup]
    summary: JSON


@strawberry.type
class DeploymentTopology:
    canonical_backend: str
    canonical_store: str
    graph_projection: str
    frontend_surface: str
    upload_boundary: str
    public_boundary: str


@strawberry.type
class PropertySourceFact:
    label: str
    value: str


@strawberry.type
class PropertySourceRecord:
    source_id: str
    source_name: str
    source_record_id: str
    observed_at: str
    facts: list[PropertySourceFact]


@strawberry.type
class PropertyDossier:
    parcel_id: str
    address: str
    records: list[PropertySourceRecord]


@strawberry.type
class SourceConflictType:
    id: int
    property_id: int | None
    parcel_id: str
    kind: str
    severity: str
    title: str
    plain_language: str
    evidence: list[str]
    observed_at: date
    status: str


@strawberry.type
class CandidatePropertyType:
    id: int
    property_id: int | None
    source_conflict_id: int | None
    parcel_id: str
    address: str
    reason: str
    evidence: str
    status: str


@strawberry.type
class PropertyIntelligenceParcel:
    dossier: PropertyDossier
    coverage_count: int
    conflict: SourceConflictType | None


@strawberry.type
class PropertyIntelligenceCoverage:
    tracked_property_count: int
    parcels_indexed: int
    home_count: int
    active_program_count: int
    source_count: int
    open_conflict_count: int
    candidate_count: int


@strawberry.type
class PropertyIntelligencePayload:
    coverage: PropertyIntelligenceCoverage
    conflicts: list[SourceConflictType]
    candidate_properties: list[CandidatePropertyType]
    parcels: list[PropertyIntelligenceParcel]


@strawberry.input
class PropertyPatchInput:
    id: int
    finding: str | None = None
    notes: str | None = None
    reviewed_by: str | None = None
    compliance_status: str | None = None
    tax_status: str | None = None
    outreach_attempts: int | None = None
    last_outreach_date: date | None = None
    last_outreach_method: str | None = None
    regrid_condition: str | None = None
    portal_survey_date: date | None = None


@strawberry.input
class WorkflowCommunicationInput:
    property_id: int
    method: str
    action: str
    status: str = "logged"
    template_slug: str | None = None
    date_sent: date | None = None
    subject: str = ""
    body: str = ""
    response_received: bool = False
    response_date: date | None = None
    response_notes: str = ""


@strawberry.type
class PropertyMutationPayload:
    ok: bool
    property: PropertyType | None
    errors: list[str]


@strawberry.type
class CommunicationMutationPayload:
    ok: bool
    communication: CommunicationType | None
    documents: list[DocumentType]
    errors: list[str]


@strawberry.type
class DocumentMutationPayload:
    ok: bool
    document: DocumentType | None
    errors: list[str]


def _property_queryset():
    return (
        Property.objects.select_related("buyer", "program_record")
        .annotate(communication_count=Count("communications"))
        .prefetch_related(
            Prefetch(
                "photos",
                queryset=PropertyPhoto.objects.order_by(
                    "side",
                    "-is_primary",
                    "-uploaded_at",
                ),
            ),
            "documents",
            "action_items",
        )
    )


def _queue_item(payload: dict) -> ActionQueueItem:
    return ActionQueueItem(
        property_id=payload["propertyId"],
        address=payload["address"],
        parcel_id=payload["parcelId"],
        buyer_name=payload["buyerName"],
        email=payload.get("buyerEmail", ""),
        action=payload["action"],
        status=payload["status"],
        due_date=payload.get("dueDate"),
        days_overdue=payload["daysOverdue"],
        enforcement_level=payload["enforcementLevel"],
        priority=payload["priority"],
        reasons=payload["reasons"],
        source=payload["source"],
    )


def _workflow_preview(payload: dict) -> WorkflowTemplatePreview:
    return WorkflowTemplatePreview(
        subject=payload["subject"],
        body=payload["body"],
        recipient_email=payload["recipientEmail"],
        recipient_name=payload["recipientName"],
        timing=payload["timing"],
        template=payload["template"],
    )


def _source_record(payload: dict) -> PropertySourceRecord:
    facts = [
        PropertySourceFact(
            label=str(fact.get("label") or ""),
            value=str(fact.get("value") or ""),
        )
        for fact in payload.get("facts", [])
        if isinstance(fact, dict)
    ]
    source_id = str(payload.get("sourceId") or "")
    return PropertySourceRecord(
        source_id=source_id,
        source_name=source_name(source_id),
        source_record_id=str(payload.get("sourceRecordId") or ""),
        observed_at=str(payload.get("observedAt") or ""),
        facts=facts,
    )


def _source_conflict(root: SourceConflict) -> SourceConflictType:
    return SourceConflictType(
        id=root.id,
        property_id=root.property_id,
        parcel_id=root.parcel_id,
        kind=root.kind,
        severity=root.severity,
        title=root.title,
        plain_language=root.plain_language,
        evidence=[str(item) for item in root.evidence if isinstance(item, str)],
        observed_at=root.observed_at,
        status=root.status,
    )


def _candidate_property(root: CandidateProperty) -> CandidatePropertyType:
    return CandidatePropertyType(
        id=root.id,
        property_id=root.property_id,
        source_conflict_id=root.source_conflict_id,
        parcel_id=root.parcel_id,
        address=root.address,
        reason=root.reason,
        evidence=root.evidence,
        status=root.status,
    )


def _property_intelligence_parcel(
    root: Property,
    conflict_by_parcel: dict[str, SourceConflict],
) -> PropertyIntelligenceParcel:
    records = [
        _source_record(record)
        for record in root.sources
        if isinstance(root.sources, list) and isinstance(record, dict)
    ]
    return PropertyIntelligenceParcel(
        dossier=PropertyDossier(
            parcel_id=root.parcel_id,
            address=root.address,
            records=records,
        ),
        coverage_count=len(records),
        conflict=(
            _source_conflict(conflict_by_parcel[root.parcel_id])
            if root.parcel_id in conflict_by_parcel
            else None
        ),
    )


@strawberry.type
class Query:
    @strawberry.field
    def deployment_topology(self) -> DeploymentTopology:
        return DeploymentTopology(
            canonical_backend="Django 5 + Django Ninja + Strawberry-Django",
            canonical_store="Postgres/PostGIS written only by Django",
            graph_projection="separate GCLBA RustyRed instance projected from Django",
            frontend_surface="GCLBA fork of Our Civic Atlas using urql GraphQL",
            upload_boundary="Django upload endpoints create PropertyPhoto and Document rows",
            public_boundary="Public Open Flint Atlas and civic RustyRed remain untouched",
        )

    @strawberry.field
    def property(self, id: int) -> PropertyType | None:
        return _property_queryset().filter(id=id).first()

    @strawberry.field
    def property_by_parcel(self, parcel_id: str) -> PropertyType | None:
        return _property_queryset().filter(parcel_id=parcel_id).first()

    @strawberry.field
    def properties(
        self,
        search: str | None = None,
        compliance_status: str | None = None,
        finding: str | None = None,
        program: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PropertyType]:
        qs = _property_queryset()
        if search:
            qs = qs.filter(
                Q(address__icontains=search)
                | Q(parcel_id__icontains=search)
                | Q(buyer_name__icontains=search)
                | Q(organization__icontains=search)
            )
        if compliance_status:
            qs = qs.filter(compliance_status=compliance_status)
        if finding:
            qs = qs.filter(finding=finding)
        if program:
            qs = qs.filter(program=program)

        safe_limit = max(1, min(limit, 250))
        safe_offset = max(0, offset)
        return list(qs[safe_offset:safe_offset + safe_limit])

    @strawberry.field
    def property_intelligence(
        self,
        parcel_id: str | None = None,
        limit: int = 5000,
    ) -> PropertyIntelligencePayload:
        safe_limit = max(1, min(limit, 5000))
        properties = Property.objects.order_by("parcel_id", "id")
        if parcel_id:
            properties = properties.filter(parcel_id=parcel_id)
        property_rows = list(properties[:safe_limit])
        conflict_qs = SourceConflict.objects.select_related("property").order_by(
            "-observed_at",
            "parcel_id",
            "kind",
        )
        if parcel_id:
            conflict_qs = conflict_qs.filter(parcel_id=parcel_id)
        conflict_rows = list(conflict_qs[:safe_limit])
        candidate_qs = CandidateProperty.objects.select_related(
            "property",
            "source_conflict",
        ).order_by("status", "parcel_id", "id")
        if parcel_id:
            candidate_qs = candidate_qs.filter(parcel_id=parcel_id)
        candidate_rows = list(candidate_qs[:safe_limit])
        first_open_conflict_by_parcel: dict[str, SourceConflict] = {}
        for conflict in conflict_rows:
            if conflict.status == "open" and conflict.parcel_id not in first_open_conflict_by_parcel:
                first_open_conflict_by_parcel[conflict.parcel_id] = conflict
        coverage_scope = (
            Property.objects.filter(parcel_id=parcel_id)
            if parcel_id
            else None
        )
        coverage = coverage_summary(coverage_scope)
        return PropertyIntelligencePayload(
            coverage=PropertyIntelligenceCoverage(
                tracked_property_count=coverage.tracked_property_count,
                parcels_indexed=coverage.parcels_indexed,
                home_count=coverage.home_count,
                active_program_count=coverage.active_program_count,
                source_count=coverage.source_count,
                open_conflict_count=coverage.open_conflict_count,
                candidate_count=coverage.candidate_count,
            ),
            conflicts=[_source_conflict(conflict) for conflict in conflict_rows],
            candidate_properties=[_candidate_property(candidate) for candidate in candidate_rows],
            parcels=[
                _property_intelligence_parcel(prop, first_open_conflict_by_parcel)
                for prop in property_rows
                if isinstance(prop.sources, list) and len(prop.sources) > 0
            ],
        )

    @strawberry.field
    def source_conflicts(
        self,
        status: str | None = "open",
        kind: str | None = None,
        parcel_id: str | None = None,
        limit: int = 250,
    ) -> list[SourceConflictType]:
        qs = SourceConflict.objects.select_related("property").order_by(
            "-observed_at",
            "parcel_id",
            "kind",
        )
        if status:
            qs = qs.filter(status=status)
        if kind:
            qs = qs.filter(kind=kind)
        if parcel_id:
            qs = qs.filter(parcel_id=parcel_id)
        return [_source_conflict(conflict) for conflict in qs[: max(1, min(limit, 500))]]

    @strawberry.field
    def candidate_properties(
        self,
        status: str | None = "queued",
        parcel_id: str | None = None,
        limit: int = 250,
    ) -> list[CandidatePropertyType]:
        qs = CandidateProperty.objects.select_related("property", "source_conflict").order_by(
            "status",
            "parcel_id",
            "id",
        )
        if status:
            qs = qs.filter(status=status)
        if parcel_id:
            qs = qs.filter(parcel_id=parcel_id)
        return [_candidate_property(candidate) for candidate in qs[: max(1, min(limit, 500))]]

    @strawberry.field
    def communications(self, property_id: int) -> list[CommunicationType]:
        return list(
            Communication.objects.filter(property_id=property_id)
            .select_related("buyer", "template")
            .order_by("-created_at")
        )

    @strawberry.field
    def documents(self, property_id: int) -> list[DocumentType]:
        return list(list_property_documents(property_id))

    @strawberry.field
    def photos(self, property_id: int) -> list[PropertyPhotoType]:
        return list(
            PropertyPhoto.objects.filter(property_id=property_id).order_by(
                "side",
                "-is_primary",
                "-uploaded_at",
            )
        )

    @strawberry.field
    def action_queue(
        self,
        as_of: date | None = None,
        action: str | None = None,
    ) -> ActionQueuePayload:
        properties = (
            Property.objects.select_related("buyer", "program_record")
            .prefetch_related("communications", "action_items")
            .all()
        )
        queue = build_action_queue(properties, as_of=as_of)
        groups = queue["groups"]
        if action:
            groups = [group for group in groups if group["action"] == action]

        return ActionQueuePayload(
            as_of=date.fromisoformat(queue["asOf"]),
            groups=[
                ActionQueueGroup(
                    action=group["action"],
                    count=group["count"],
                    items=[_queue_item(item) for item in group["items"]],
                )
                for group in groups
            ],
            summary={group["action"]: group["count"] for group in groups},
        )

    @strawberry.field
    def workflow_template_preview(
        self,
        property_id: int,
        action: str,
        template_slug: str | None = None,
        as_of: date | None = None,
    ) -> WorkflowTemplatePreview | None:
        prop = (
            Property.objects.select_related("buyer", "program_record")
            .prefetch_related("communications")
            .filter(id=property_id)
            .first()
        )
        if not prop:
            return None
        payload = render_template_preview(
            prop,
            action=action,
            template_slug=template_slug,
            as_of=as_of,
        )
        return _workflow_preview(payload)


@strawberry.type
class Mutation:
    @strawberry.mutation
    def update_property(self, input: PropertyPatchInput) -> PropertyMutationPayload:
        prop = Property.objects.filter(id=input.id).first()
        if not prop:
            return PropertyMutationPayload(
                ok=False,
                property=None,
                errors=[f"Property {input.id} was not found."],
            )

        editable_fields = [
            "finding",
            "notes",
            "reviewed_by",
            "compliance_status",
            "tax_status",
            "outreach_attempts",
            "last_outreach_date",
            "last_outreach_method",
            "regrid_condition",
            "portal_survey_date",
        ]
        changed_fields = []
        for field_name in editable_fields:
            value = getattr(input, field_name)
            if value is None:
                continue
            setattr(prop, field_name, value)
            changed_fields.append(field_name)

        if changed_fields:
            prop.save(update_fields=[*changed_fields, "updated_at"])

        return PropertyMutationPayload(
            ok=True,
            property=_property_queryset().get(id=prop.id),
            errors=[],
        )

    @strawberry.mutation
    def create_workflow_communication(
        self,
        input: WorkflowCommunicationInput,
    ) -> CommunicationMutationPayload:
        prop = (
            Property.objects.select_related("buyer", "program_record")
            .prefetch_related("communications")
            .filter(id=input.property_id)
            .first()
        )
        if not prop:
            return CommunicationMutationPayload(
                ok=False,
                communication=None,
                documents=[],
                errors=[f"Property {input.property_id} was not found."],
            )

        try:
            comm_data = prepare_workflow_communication(
                prop,
                method=input.method,
                direction="outbound",
                action=input.action,
                status=input.status,
                template_slug=input.template_slug,
                subject=input.subject,
                body=input.body,
                date_sent=input.date_sent,
            )
        except ValueError as exc:
            return CommunicationMutationPayload(
                ok=False,
                communication=None,
                documents=[],
                errors=[str(exc)],
            )

        template = EmailTemplate.objects.filter(
            slug=comm_data["template"],
            is_active=True,
        ).first()

        with transaction.atomic():
            comm = Communication.objects.create(
                property=prop,
                buyer=prop.buyer,
                template=template,
                method=input.method,
                direction="outbound",
                action=comm_data["action"],
                template_name=comm_data["template_name"],
                status=comm_data["status"],
                recipient_email=comm_data["recipient_email"],
                date_sent=comm_data["date_sent"],
                sent_at=comm_data["sent_at"],
                approved_at=comm_data["approved_at"],
                provider_message_id=comm_data["provider_message_id"],
                subject=comm_data["subject"],
                body=comm_data["body"],
                body_hash=comm_data["body_hash"],
                response_received=input.response_received,
                response_date=input.response_date,
                response_notes=input.response_notes,
            )
            update_fields = apply_communication_rollups(
                prop,
                action=comm.action,
                status=comm.status,
                method=comm.method,
                date_sent=comm.date_sent,
            )
            if update_fields:
                prop.save(update_fields=update_fields)
            documents = create_communication_artifacts(prop, comm)

        return CommunicationMutationPayload(
            ok=True,
            communication=comm,
            documents=list(documents),
            errors=[],
        )

    @strawberry.mutation
    def upload_property_document(
        self,
        property_id: int,
        file: Upload,
        category: str = "property_document",
        slot: str = "manual_upload",
        description: str = "",
    ) -> DocumentMutationPayload:
        prop = Property.objects.filter(id=property_id).first()
        if not prop:
            return DocumentMutationPayload(
                ok=False,
                document=None,
                errors=[f"Property {property_id} was not found."],
            )
        if not getattr(file, "name", ""):
            return DocumentMutationPayload(
                ok=False,
                document=None,
                errors=["Upload must include a filename."],
            )

        artifact = save_uploaded_property_document(
            prop,
            file,
            category=category,
            slot=slot,
            metadata={"description": description.strip()} if description.strip() else {},
        )
        return DocumentMutationPayload(
            ok=True,
            document=artifact.document,
            errors=[],
        )


# Merge the GCLBA context + compliance queries (defined in graphql_context, Claude
# lane) into the workflow Query so the fork reaches them over one schema.
CombinedQuery = merge_types("Query", (Query, ContextQuery, ComplianceQuery))

schema = strawberry.Schema(
    query=CombinedQuery,
    mutation=Mutation,
    extensions=[DjangoOptimizerExtension],
)
