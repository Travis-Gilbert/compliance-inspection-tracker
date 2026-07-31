"""
Owned-pixel storage for photo intake.

Writes to Cloudflare R2 when configured; otherwise falls back to local
IMAGE_CACHE_DIR under the parcels/ prefix so intake stays testable offline.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from django.conf import settings


_PARCEL_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredObject:
    storage_key: str
    sha256: str
    public_url: str
    bytes_written: int
    reused_existing: bool = False


def normalize_parcel_id(parcel_id: str) -> str:
    raw = (parcel_id or "").strip() or "unknown"
    return _PARCEL_SAFE.sub("_", raw)


def build_storage_key(*, parcel_id: str, source: str, capture_date: str, ext: str = "jpg") -> str:
    date_part = (capture_date or "undated").strip().replace("/", "-")
    return f"parcels/{normalize_parcel_id(parcel_id)}/{source}/{date_part}.{ext.lstrip('.')}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _r2_configured() -> bool:
    return bool(
        getattr(settings, "R2_ACCOUNT_ID", "")
        and getattr(settings, "R2_ACCESS_KEY_ID", "")
        and getattr(settings, "R2_SECRET_ACCESS_KEY", "")
        and getattr(settings, "R2_BUCKET_NAME", "")
    )


def _local_root() -> Path:
    root = Path(getattr(settings, "IMAGE_CACHE_DIR", settings.MEDIA_ROOT))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _public_url_for_key(storage_key: str) -> str:
    public_base = (getattr(settings, "R2_PUBLIC_URL", "") or "").strip().rstrip("/")
    if public_base and _r2_configured():
        return f"{public_base}/{storage_key}"

    backend = (getattr(settings, "GCLBA_BACKEND_PUBLIC_URL", "") or "").strip().rstrip("/")
    media_url = (getattr(settings, "MEDIA_URL", "/images/") or "/images/").rstrip("/")
    if backend:
        return f"{backend}{media_url}/{storage_key}"
    return f"{media_url}/{storage_key}"


def _s3_client():
    import boto3

    account_id = settings.R2_ACCOUNT_ID
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name=getattr(settings, "R2_REGION", "auto") or "auto",
    )


def object_exists(storage_key: str) -> bool:
    if _r2_configured():
        client = _s3_client()
        try:
            client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=storage_key)
            return True
        except Exception:
            return False
    return (_local_root() / storage_key).is_file()


def find_by_sha256(sha256: str) -> Optional[str]:
    """Return an existing storage_key for this hash if one is known in Django."""
    if not sha256:
        return None
    from tracker.models import PropertyImageEvidence

    row = (
        PropertyImageEvidence.objects.filter(sha256=sha256)
        .exclude(storage_key="")
        .order_by("id")
        .values_list("storage_key", flat=True)
        .first()
    )
    return row or None


def store_owned_bytes(
    data: bytes,
    *,
    parcel_id: str,
    source: str,
    capture_date: str,
    content_type: str = "image/jpeg",
    force: bool = False,
) -> StoredObject:
    digest = sha256_bytes(data)
    existing_key = find_by_sha256(digest)
    if existing_key and not force:
        return StoredObject(
            storage_key=existing_key,
            sha256=digest,
            public_url=_public_url_for_key(existing_key),
            bytes_written=0,
            reused_existing=True,
        )

    storage_key = build_storage_key(
        parcel_id=parcel_id,
        source=source,
        capture_date=capture_date,
    )

    if _r2_configured():
        if not force and object_exists(storage_key):
            return StoredObject(
                storage_key=storage_key,
                sha256=digest,
                public_url=_public_url_for_key(storage_key),
                bytes_written=0,
                reused_existing=True,
            )
        client = _s3_client()
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=storage_key,
            Body=data,
            ContentType=content_type,
        )
    else:
        path = _local_root() / storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            return StoredObject(
                storage_key=storage_key,
                sha256=digest,
                public_url=_public_url_for_key(storage_key),
                bytes_written=0,
                reused_existing=True,
            )
        path.write_bytes(data)

    return StoredObject(
        storage_key=storage_key,
        sha256=digest,
        public_url=_public_url_for_key(storage_key),
        bytes_written=len(data),
        reused_existing=False,
    )
