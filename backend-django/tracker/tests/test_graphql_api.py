import json
from datetime import date
from io import StringIO
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from tracker.models import ActionItem, Communication, Document, Property
from tracker.services.compliance_timing import ACTION_ATTEMPT_1


def graphql_query(client, query: str, variables: dict | None = None):
    return client.post(
        "/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}),
        content_type="application/json",
    )


class GraphqlApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workflow_defaults", stdout=StringIO())

    def test_properties_query_exposes_tracker_records_and_topology(self):
        Property.objects.create(
            address="1234 W Court St",
            parcel_id="41-11-234-012",
            buyer_name="Maria Santos",
            email="maria@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        response = graphql_query(
            self.client,
            """
            query Properties($search: String!) {
              deploymentTopology {
                canonicalBackend
                canonicalStore
                graphProjection
                frontendSurface
                publicBoundary
              }
              properties(search: $search, limit: 5) {
                id
                address
                parcelId
                buyerName
                communicationCount
                manualComplianceOutcome
                photoSummary
              }
            }
            """,
            {"search": "Court"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        self.assertEqual(
            payload["data"]["deploymentTopology"]["canonicalStore"],
            "Postgres/PostGIS written only by Django",
        )
        self.assertEqual(len(payload["data"]["properties"]), 1)
        prop = payload["data"]["properties"][0]
        self.assertEqual(prop["parcelId"], "41-11-234-012")
        self.assertEqual(prop["manualComplianceOutcome"], "pending")

    def test_update_property_mutation_supports_write_through_edits(self):
        prop = Property.objects.create(
            address="456 E Kearsley St",
            parcel_id="41-06-102-008",
            buyer_name="James Wilson",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        response = graphql_query(
            self.client,
            """
            mutation UpdateProperty($input: PropertyPatchInput!) {
              updateProperty(input: $input) {
                ok
                errors
                property {
                  id
                  finding
                  notes
                  complianceStatus
                  manualComplianceOutcome
                }
              }
            }
            """,
            {
                "input": {
                    "id": prop.id,
                    "finding": "partial_progress",
                    "notes": "Roof work visible from street imagery.",
                    "complianceStatus": "in_progress",
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        mutation = payload["data"]["updateProperty"]
        self.assertTrue(mutation["ok"])
        self.assertEqual(mutation["errors"], [])
        self.assertEqual(mutation["property"]["finding"], "partial_progress")
        self.assertEqual(mutation["property"]["complianceStatus"], "in_progress")

        prop.refresh_from_db()
        self.assertEqual(prop.finding, "partial_progress")
        self.assertEqual(prop.compliance_status, "in_progress")

    def test_create_workflow_communication_reuses_workflow_services(self):
        prop = Property.objects.create(
            address="789 Saginaw St",
            parcel_id="41-06-441-015",
            buyer_name="Keisha Thompson",
            email="keisha@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        response = graphql_query(
            self.client,
            """
            mutation CreateCommunication($input: WorkflowCommunicationInput!) {
              createWorkflowCommunication(input: $input) {
                ok
                errors
                communication {
                  id
                  propertyId
                  action
                  method
                  status
                  recipientEmail
                  dateSent
                }
                documents {
                  filename
                  category
                }
              }
            }
            """,
            {
                "input": {
                    "propertyId": prop.id,
                    "method": "email",
                    "action": ACTION_ATTEMPT_1,
                    "status": "sent",
                    "templateSlug": "monthly-compliance",
                    "dateSent": date(2026, 2, 5).isoformat(),
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        mutation = payload["data"]["createWorkflowCommunication"]
        self.assertTrue(mutation["ok"])
        self.assertEqual(mutation["communication"]["propertyId"], prop.id)
        self.assertEqual(mutation["communication"]["recipientEmail"], "keisha@example.com")
        self.assertGreaterEqual(len(mutation["documents"]), 1)
        self.assertEqual(Communication.objects.count(), 1)

    def test_upload_property_document_mutation_writes_document_metadata(self):
        prop = Property.objects.create(
            address="222 GraphQL Upload St",
            parcel_id="41-06-222-010",
            buyer_name="GraphQL Upload",
            email="graphql-upload@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )

        operations = {
            "query": """
            mutation UploadPropertyDocument(
              $propertyId: Int!
              $file: Upload!
              $category: String!
              $slot: String!
              $description: String!
            ) {
              uploadPropertyDocument(
                propertyId: $propertyId
                file: $file
                category: $category
                slot: $slot
                description: $description
              ) {
                ok
                errors
                document {
                  id
                  propertyId
                  filename
                  storageKey
                  storageUrl
                  mimeType
                  sizeBytes
                  category
                  slot
                  metadata
                }
              }
            }
            """,
            "variables": {
                "propertyId": prop.id,
                "file": None,
                "category": "closing_packet",
                "slot": "signed_docs",
                "description": "Closing packet from staff review.",
            },
        }
        upload = SimpleUploadedFile(
            "closing packet.txt",
            b"closing packet bytes",
            content_type="text/plain",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.settings(MEDIA_ROOT=Path(tmpdir), MEDIA_URL="/images/"):
                response = self.client.post(
                    "/graphql",
                    data={
                        "operations": json.dumps(operations),
                        "map": json.dumps({"0": ["variables.file"]}),
                        "0": upload,
                    },
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertNotIn("errors", payload)
                mutation = payload["data"]["uploadPropertyDocument"]
                self.assertTrue(mutation["ok"])
                self.assertEqual(mutation["errors"], [])
                document = mutation["document"]
                self.assertEqual(document["propertyId"], prop.id)
                self.assertEqual(document["filename"], "closing packet.txt")
                self.assertEqual(document["category"], "closing_packet")
                self.assertEqual(document["slot"], "signed_docs")
                self.assertEqual(document["mimeType"], "text/plain")
                self.assertEqual(document["sizeBytes"], len(b"closing packet bytes"))
                self.assertEqual(
                    document["metadata"]["description"],
                    "Closing packet from staff review.",
                )

                saved = Document.objects.get(pk=document["id"])
                self.assertEqual(saved.property_id, prop.id)
                self.assertEqual((Path(tmpdir) / document["storageKey"]).read_bytes(), b"closing packet bytes")

    def test_action_queue_query_exposes_filtered_grouped_items(self):
        prop = Property.objects.create(
            address="12 Audit Lane",
            parcel_id="41-07-001-001",
            buyer_name="Manual Queue",
            email="queue@example.com",
            program="Featured Homes",
            closing_date="2026-01-01",
        )
        ActionItem.objects.create(
            property=prop,
            action="TAX_VERIFICATION",
            status="in_progress",
            due_date=date(2026, 3, 1),
            days_overdue=4,
            enforcement_level=2,
            priority=77,
            reasons=["Tax status docs need verification."],
            source="staff",
        )

        response = graphql_query(
            self.client,
            """
            query {
              actionQueue(asOf: "2026-03-05", action: "TAX_VERIFICATION") {
                asOf
                summary
                groups {
                  action
                  count
                  items {
                    propertyId
                    address
                    parcelId
                    buyerName
                    email
                    action
                    status
                    dueDate
                    daysOverdue
                    enforcementLevel
                    priority
                    reasons
                    source
                  }
                }
              }
            }
            """
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("errors", payload)
        queue = payload["data"]["actionQueue"]
        self.assertEqual(queue["asOf"], "2026-03-05")
        self.assertEqual(queue["summary"], {"TAX_VERIFICATION": 1})
        self.assertEqual(len(queue["groups"]), 1)

        group = queue["groups"][0]
        self.assertEqual(group["action"], "TAX_VERIFICATION")
        self.assertEqual(group["count"], 1)

        item = group["items"][0]
        self.assertEqual(item["propertyId"], prop.id)
        self.assertEqual(item["address"], "12 Audit Lane")
        self.assertEqual(item["status"], "in_progress")
        self.assertEqual(item["dueDate"], "2026-03-01")
        self.assertEqual(item["daysOverdue"], 4)
        self.assertEqual(item["enforcementLevel"], 2)
        self.assertEqual(item["priority"], 77)
        self.assertEqual(item["reasons"], ["Tax status docs need verification."])
        self.assertEqual(item["source"], "staff")
