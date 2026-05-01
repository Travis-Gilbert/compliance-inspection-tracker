# Generated manually for the compliance redesign on 2026-05-01.

import django.core.validators
import django.db.models.deletion
import tracker.models
from django.db import migrations, models
from django.db.models import Q


POSTGIS_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

ALTER TABLE tracker_property
ADD COLUMN IF NOT EXISTS geo_point geography(Point, 4326)
GENERATED ALWAYS AS (
    CASE
        WHEN longitude IS NOT NULL AND latitude IS NOT NULL
        THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
        ELSE NULL
    END
) STORED;

CREATE INDEX IF NOT EXISTS tracker_property_geo_point_gix
ON tracker_property USING GIST (geo_point);

ALTER TABLE tracker_propertyphoto
ADD COLUMN IF NOT EXISTS photo_point geography(Point, 4326)
GENERATED ALWAYS AS (
    CASE
        WHEN photo_longitude IS NOT NULL AND photo_latitude IS NOT NULL
        THEN ST_SetSRID(ST_MakePoint(photo_longitude, photo_latitude), 4326)::geography
        ELSE NULL
    END
) STORED;

CREATE INDEX IF NOT EXISTS tracker_propertyphoto_point_gix
ON tracker_propertyphoto USING GIST (photo_point);
"""

POSTGIS_REVERSE_SQL = """
DROP INDEX IF EXISTS tracker_propertyphoto_point_gix;
ALTER TABLE tracker_propertyphoto DROP COLUMN IF EXISTS photo_point;

DROP INDEX IF EXISTS tracker_property_geo_point_gix;
ALTER TABLE tracker_property DROP COLUMN IF EXISTS geo_point;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PropertyPhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("side", models.CharField(choices=[("before", "Before"), ("after", "After")], db_index=True, max_length=10)),
                (
                    "image",
                    models.ImageField(
                        upload_to=tracker.models.property_photo_upload_to,
                        validators=[django.core.validators.FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
                    ),
                ),
                ("original_filename", models.CharField(blank=True, default="", max_length=255)),
                ("caption", models.CharField(blank=True, default="", max_length=255)),
                ("source", models.CharField(blank=True, default="manual_upload", max_length=50)),
                ("is_primary", models.BooleanField(db_index=True, default=False)),
                ("photo_date", models.DateField(blank=True, null=True)),
                ("photo_latitude", models.FloatField(blank=True, null=True)),
                ("photo_longitude", models.FloatField(blank=True, null=True)),
                ("distance_from_property_meters", models.FloatField(blank=True, null=True)),
                (
                    "proximity_status",
                    models.CharField(
                        choices=[
                            ("unlocated", "Unlocated"),
                            ("near_property", "Near Property"),
                            ("nearby", "Nearby"),
                            ("outside_property_area", "Outside Property Area"),
                        ],
                        db_index=True,
                        default="unlocated",
                        max_length=30,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "property",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="photos",
                        to="tracker.property",
                    ),
                ),
            ],
            options={
                "ordering": ["side", "-is_primary", "-uploaded_at"],
                "indexes": [
                    models.Index(fields=["property", "side", "is_primary"], name="tracker_pro_propert_8f038d_idx"),
                    models.Index(fields=["proximity_status"], name="tracker_pro_proximi_ac1985_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=Q(is_primary=True),
                        fields=("property", "side"),
                        name="one_primary_photo_per_property_side",
                    )
                ],
            },
        ),
        migrations.RunSQL(POSTGIS_SQL, POSTGIS_REVERSE_SQL),
    ]
