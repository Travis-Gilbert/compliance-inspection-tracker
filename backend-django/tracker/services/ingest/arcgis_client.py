"""
ArcGIS REST FeatureServer incremental query client for the County spine.

Pulls features from an ArcGIS Online FeatureServer layer with keyset (OBJECTID
high-water) pagination, which is the spec's fallback when the layer has no
edit-date field (the resolved CountyRealProperty layer has none). Keyset paging
is naturally resumable: WHERE OBJECTID > {cursor} ORDER BY OBJECTID ASC, with the
page max becoming the next cursor, so a failed run re-pulls from the last
committed high-water instead of skipping rows.

This module returns parsed feature dicts; arcgis_sync.py maps them onto models.
It performs no DB work and is unit-testable directly against the live layer.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx

from . import sources


class ArcGisError(RuntimeError):
    """Raised on transport failure or an ArcGIS REST {"error": ...} payload."""


class ArcGisClient:
    def __init__(
        self,
        base_url: str,
        layer_id: int | str,
        *,
        object_id_field: str = "OBJECTID",
        edit_date_field: str = "",
        max_record_count: int = 2000,
        out_sr: int = 4326,
        out_fields: str = "*",
        user_agent: str = sources.USER_AGENT,
        delay_seconds: float = sources.REQUEST_DELAY_SECONDS,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.layer_id = layer_id
        self.object_id_field = object_id_field
        self.edit_date_field = edit_date_field
        self.max_record_count = max_record_count
        self.out_sr = out_sr
        self.out_fields = out_fields
        self.delay_seconds = delay_seconds
        self.query_url = f"{self.base_url}/{layer_id}/query"
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )

    # -- lifecycle --------------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ArcGisClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- internals --------------------------------------------------------------
    def _get(self, params: dict) -> dict:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        try:
            resp = self._client.get(self.query_url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ArcGisError(f"ArcGIS request failed: {exc}") from exc
        except ValueError as exc:  # JSON decode
            raise ArcGisError(f"ArcGIS returned non-JSON: {exc}") from exc
        if isinstance(data, dict) and data.get("error"):
            raise ArcGisError(f"ArcGIS error: {data['error']}")
        return data

    def _where(self, cursor: int, where_extra: str = "") -> str:
        if self.edit_date_field:
            # No resolved source uses an edit-date field yet; implement deliberately
            # (timestamp formatting + epoch-ms cursor handling) when one appears.
            raise NotImplementedError(
                "edit-date diffing not implemented; resolved sources use OBJECTID high-water"
            )
        base = f"{self.object_id_field} > {int(cursor or 0)}"
        return f"({base}) AND ({where_extra})" if where_extra else base

    # -- public API -------------------------------------------------------------
    def count_since(self, cursor: int | str = 0, where_extra: str = "") -> int:
        """Cheap pre-check: how many rows are newer than the cursor."""
        data = self._get(
            {
                "where": self._where(int(cursor or 0), where_extra),
                "returnCountOnly": "true",
                "f": "json",
            }
        )
        return int(data.get("count", 0))

    def iter_features(
        self,
        cursor: int | str = 0,
        *,
        where_extra: str = "",
        page_limit: int | None = None,
        record_count: int | None = None,
    ) -> Iterator[dict]:
        """Yield parsed feature dicts (attributes + geometry) across all pages.

        cursor: starting OBJECTID high-water (exclusive). record_count caps the
        page size (e.g. small for a smoke test). page_limit caps total pages.
        """
        oid = int(cursor or 0)
        page_size = record_count or self.max_record_count
        pages = 0
        while True:
            data = self._get(
                {
                    "where": self._where(oid, where_extra),
                    "outFields": self.out_fields,
                    "returnGeometry": "true",
                    "outSR": self.out_sr,
                    "orderByFields": f"{self.object_id_field} ASC",
                    "resultRecordCount": page_size,
                    "f": "json",
                }
            )
            features = data.get("features", [])
            if not features:
                break
            for feature in features:
                yield feature
            oids = [
                feature["attributes"].get(self.object_id_field)
                for feature in features
                if feature.get("attributes")
            ]
            oids = [value for value in oids if isinstance(value, int)]
            if not oids:
                break
            oid = max(oids)
            pages += 1
            if page_limit is not None and pages >= page_limit:
                break
            if len(features) < page_size and not data.get("exceededTransferLimit"):
                break
