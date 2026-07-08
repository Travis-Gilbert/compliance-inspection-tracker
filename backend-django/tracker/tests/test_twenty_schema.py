from __future__ import annotations

from django.test import SimpleTestCase

from tracker.services.twenty_schema import GCLBA_OBJECTS, bootstrap_twenty_schema


class FakeTwentyMetadataClient:
    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.fields: dict[str, dict[str, dict]] = {}
        self.views: dict[str, list[dict]] = {}
        self.view_fields: dict[str, list[dict]] = {}
        self.nav_items: list[dict] = []
        self.roles: list[dict] = []
        self.permission_upserts = []

    def close(self):
        pass

    def rest_get(self, path: str):
        if path == "/rest/metadata/objects":
            return {"data": list(self.objects.values())}
        if path.startswith("/rest/metadata/fields?objectMetadataId="):
            object_id = path.rsplit("=", 1)[1]
            return {"data": list(self.fields.get(object_id, {}).values())}
        raise AssertionError(f"unexpected REST path {path}")

    def metadata_graphql(self, query: str, variables: dict | None = None):
        variables = variables or {}
        if "createOneObject" in query:
            payload = variables["input"]["object"]
            object_id = f"object-{payload['nameSingular']}"
            row = {
                "id": object_id,
                "nameSingular": payload["nameSingular"],
                "namePlural": payload["namePlural"],
                "labelSingular": payload["labelSingular"],
                "labelPlural": payload["labelPlural"],
                "description": payload.get("description", ""),
                "icon": payload.get("icon", ""),
            }
            self.objects[payload["nameSingular"]] = row
            self.fields[object_id] = {
                "name": {
                    "id": f"field-{payload['nameSingular']}-name",
                    "name": "name",
                    "type": "TEXT",
                    "isSystem": False,
                    "objectMetadataId": object_id,
                }
            }
            return {"createOneObject": row}
        if "createOneField" in query:
            payload = variables["input"]["field"]
            object_id = payload["objectMetadataId"]
            row = {
                "id": f"field-{object_id}-{payload['name']}",
                "name": payload["name"],
                "type": payload["type"],
                "options": payload.get("options", []),
                "settings": payload.get("settings"),
                "isNullable": payload.get("isNullable", False),
                "isSystem": False,
                "objectMetadataId": object_id,
            }
            self.fields.setdefault(object_id, {})[payload["name"]] = row
            return {"createOneField": row}
        if "updateOneObject" in query:
            object_id = variables["input"]["id"]
            update = variables["input"]["update"]
            for row in self.objects.values():
                if row["id"] == object_id:
                    row.update(update)
                    return {"updateOneObject": row}
            raise AssertionError(f"missing object id {object_id}")
        if "updateOneField" in query:
            field_id = variables["input"]["id"]
            update = variables["input"]["update"]
            for object_fields in self.fields.values():
                for row in object_fields.values():
                    if row["id"] == field_id:
                        row.update(update)
                        return {"updateOneField": row}
            raise AssertionError(f"missing field id {field_id}")
        if "fields(paging:" in query:
            object_id = variables["filter"]["objectMetadataId"]["eq"]
            return {
                "fields": {
                    "edges": [
                        {"node": row}
                        for row in self.fields.get(object_id, {}).values()
                    ]
                }
            }
        if "getViews" in query:
            return {"getViews": self.views.get(variables["objectMetadataId"], [])}
        if "createView(" in query:
            payload = variables["input"]
            row = {
                "id": f"view-{payload['objectMetadataId']}-{payload['name']}",
                "name": payload["name"],
                "type": payload["type"],
            }
            self.views.setdefault(payload["objectMetadataId"], []).append(row)
            return {"createView": row}
        if "updateView(" in query:
            view_id = variables.get("id") or variables["input"]["id"]
            update = {
                key: value
                for key, value in variables["input"].items()
                if key != "id"
            }
            for rows in self.views.values():
                for row in rows:
                    if row["id"] == view_id:
                        row.update(update)
                        return {"updateView": {"id": view_id}}
            raise AssertionError(f"missing view id {view_id}")
        if "getViewFields" in query:
            return {"getViewFields": self.view_fields.get(variables["viewId"], [])}
        if "createViewField" in query:
            payload = variables["input"]
            row = {
                "id": f"view-field-{payload['viewId']}-{payload['fieldMetadataId']}",
                "fieldMetadataId": payload["fieldMetadataId"],
                "isVisible": payload["isVisible"],
                "position": payload["position"],
            }
            self.view_fields.setdefault(payload["viewId"], []).append(row)
            return {"createViewField": {"id": row["id"]}}
        if "updateViewField" in query:
            view_field_id = variables["input"]["id"]
            update = variables["input"]["update"]
            for rows in self.view_fields.values():
                for row in rows:
                    if row["id"] == view_field_id:
                        row.update(update)
                        return {"updateViewField": {"id": view_field_id}}
            raise AssertionError(f"missing view field id {view_field_id}")
        if "createViewGroup" in query:
            return {"createViewGroup": {"id": "view-group"}}
        if "createViewFilter" in query:
            return {"createViewFilter": {"id": "view-filter"}}
        if "createViewSort" in query:
            return {"createViewSort": {"id": "view-sort"}}
        if "navigationMenuItems" in query:
            return {"navigationMenuItems": self.nav_items}
        if "createNavigationMenuItem" in query:
            payload = variables["input"]
            nav_id = f"nav-{payload.get('targetObjectMetadataId') or payload['name']}"
            self.nav_items.append(
                {
                    "id": nav_id,
                    "name": payload["name"],
                    "type": payload["type"],
                    "link": payload.get("link"),
                    "targetObjectMetadataId": payload.get("targetObjectMetadataId"),
                }
            )
            return {"createNavigationMenuItem": {"id": self.nav_items[-1]["id"]}}
        if "updateNavigationMenuItem" in query:
            nav_id = variables["input"]["id"]
            update = variables["input"]["update"]
            for item in self.nav_items:
                if item["id"] == nav_id:
                    item.update(update)
                    return {"updateNavigationMenuItem": {"id": nav_id}}
            raise AssertionError(f"missing nav id {nav_id}")
        if "deleteNavigationMenuItem" in query:
            self.nav_items = [item for item in self.nav_items if item["id"] != variables["id"]]
            return {"deleteNavigationMenuItem": True}
        if "getRoles" in query:
            return {"getRoles": self.roles}
        if "createOneRole" in query:
            payload = variables["input"]
            row = {"id": "role-gclba-sales-read-only", "label": payload["label"]}
            self.roles.append(row)
            return {"createOneRole": row}
        if "upsertObjectPermissions" in query:
            self.permission_upserts.append(variables["input"])
            return {"upsertObjectPermissions": {"id": "permissions"}}
        raise AssertionError(f"unexpected GraphQL query {query}")


class TwentySchemaBootstrapTests(SimpleTestCase):
    def test_bootstrap_creates_schema_workspace_polish_and_role(self):
        client = FakeTwentyMetadataClient()

        result = bootstrap_twenty_schema(client=client)

        self.assertEqual(result.objects_created, len(GCLBA_OBJECTS))
        self.assertEqual(result.objects_existing, 0)
        self.assertGreater(result.fields_created, 0)
        self.assertGreaterEqual(result.views_created, len(GCLBA_OBJECTS))
        self.assertEqual(result.navigation_created, len(GCLBA_OBJECTS) + 1)
        self.assertEqual(result.roles_created, 1)
        self.assertEqual(len(client.permission_upserts), 1)
        self.assertIn("gclbaSourceConflict", client.objects)
        property_object_id = client.objects["gclbaProperty"]["id"]
        property_table_view_id = f"view-{property_object_id}-GCLBA Properties table"
        property_view_field_ids = {
            row["fieldMetadataId"]
            for row in client.view_fields[property_table_view_id]
        }
        property_field_ids = {
            row["name"]: row["id"]
            for row in client.fields[property_object_id].values()
        }
        self.assertIn(property_field_ids["contactEmail"], property_view_field_ids)
        self.assertIn(property_field_ids["saleDate"], property_view_field_ids)
        self.assertIn(property_field_ids["taxAmountOwed"], property_view_field_ids)
        property_all_view_id = f"view-{property_object_id}-All GCLBA Properties"
        all_view_fields = {
            row["fieldMetadataId"]: row
            for row in client.view_fields[property_all_view_id]
        }
        self.assertEqual(all_view_fields[property_field_ids["name"]]["position"], 0)
        self.assertEqual(all_view_fields[property_field_ids["buyerName"]]["position"], 1)
        self.assertEqual(all_view_fields[property_field_ids["propertyAddress"]]["position"], 2)
        self.assertNotIn(property_field_ids["tenantId"], all_view_fields)
        self.assertIn(
            "https://www.gclbamaps.org/gclba/context",
            {item.get("link") for item in client.nav_items},
        )
        quality_object_id = client.objects["gclbaHomeQualityObservation"]["id"]
        quality_field_ids = {
            row["name"]: row["id"]
            for row in client.fields[quality_object_id].values()
        }
        quality_all_view_id = (
            f"view-{quality_object_id}-All GCLBA Home Quality Observations"
        )
        quality_all_view_fields = {
            row["fieldMetadataId"]: row
            for row in client.view_fields[quality_all_view_id]
        }
        self.assertEqual(quality_all_view_fields[quality_field_ids["name"]]["position"], 0)
        self.assertEqual(
            quality_all_view_fields[quality_field_ids["propertyAddress"]]["position"],
            1,
        )
        self.assertEqual(
            quality_all_view_fields[quality_field_ids["detectionLabel"]]["position"],
            3,
        )
        self.assertEqual(
            quality_all_view_fields[quality_field_ids["streetviewAvailable"]]["position"],
            5,
        )
        image_object_id = client.objects["gclbaImageEvidence"]["id"]
        image_field_ids = {
            row["name"]: row["id"]
            for row in client.fields[image_object_id].values()
        }
        self.assertEqual(client.objects["gclbaImageEvidence"]["labelPlural"], "GCLBA Images")
        self.assertEqual(client.fields[image_object_id]["imageFile"]["type"], "FILES")
        self.assertEqual(
            client.fields[image_object_id]["imageFile"]["settings"],
            {"maxNumberOfValues": 1},
        )
        image_all_view_id = f"view-{image_object_id}-All GCLBA Images"
        image_all_view_fields = {
            row["fieldMetadataId"]: row
            for row in client.view_fields[image_all_view_id]
        }
        self.assertEqual(image_all_view_fields[image_field_ids["name"]]["position"], 0)
        self.assertEqual(
            image_all_view_fields[image_field_ids["imageFile"]]["position"],
            1,
        )
        self.assertEqual(
            image_all_view_fields[image_field_ids["imageSource"]]["position"],
            3,
        )
        self.assertEqual(
            image_all_view_fields[image_field_ids["imageUrl"]]["position"],
            6,
        )
        self.assertEqual(
            image_all_view_fields[image_field_ids["thumbnailUrl"]]["position"],
            5,
        )

    def test_bootstrap_second_run_reuses_existing_schema(self):
        client = FakeTwentyMetadataClient()
        bootstrap_twenty_schema(client=client)
        property_object_id = client.objects["gclbaProperty"]["id"]
        contact_field_id = client.fields[property_object_id]["contactEmail"]["id"]
        tenant_field_id = client.fields[property_object_id]["tenantId"]["id"]
        property_all_view_id = f"view-{property_object_id}-All GCLBA Properties"
        client.view_fields[property_all_view_id].append(
            {
                "id": "view-field-extra-tenant",
                "fieldMetadataId": tenant_field_id,
                "isVisible": True,
                "position": 1,
            }
        )
        buyer_field_id = client.fields[property_object_id]["buyerName"]["id"]
        buyer_row = next(
            row
            for row in client.view_fields[property_all_view_id]
            if row["fieldMetadataId"] == buyer_field_id
        )
        buyer_row["position"] = 99
        hidden_contact_row = next(
            row
            for rows in client.view_fields.values()
            for row in rows
            if row["fieldMetadataId"] == contact_field_id
        )
        hidden_contact_row["isVisible"] = False
        counts_before = {
            view_id: len(rows)
            for view_id, rows in client.view_fields.items()
        }

        second = bootstrap_twenty_schema(client=client)

        self.assertEqual(second.objects_created, 0)
        self.assertEqual(second.objects_existing, len(GCLBA_OBJECTS))
        self.assertEqual(second.fields_created, 0)
        self.assertGreater(second.fields_existing, 0)
        self.assertGreater(second.views_existing, 0)
        self.assertEqual(second.navigation_existing, len(GCLBA_OBJECTS) + 1)
        self.assertEqual(second.roles_existing, 1)
        self.assertEqual(
            counts_before,
            {view_id: len(rows) for view_id, rows in client.view_fields.items()},
        )
        self.assertTrue(hidden_contact_row["isVisible"])
        self.assertEqual(buyer_row["position"], 1)
        self.assertFalse(client.view_fields[property_all_view_id][-1]["isVisible"])
