"""
Ingestion services for the GCLBA / compliance backend.

Sibling to the existing `enrichment.py` (pure scoring/clustering) and
`pipeline.py`; ingestion pulls external parcel/assessment/infrastructure data
into the tracker's models. The clean, always-on spine is the Genesee County
ArcGIS open-data feed (`arcgis_client` + `arcgis_sync`), configured by
`sources`. The attended BS&A path is intentionally NOT present (out of scope
for this build; see docs/GCLBA PLAN 6-5/MASTER-PLAN-AND-LANES.md).
"""
