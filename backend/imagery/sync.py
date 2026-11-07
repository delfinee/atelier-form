"""Sync and serve curated custom assets."""
from __future__ import annotations

from dataclasses import dataclass

from .custom_assets import get_asset_bytes, get_asset_meta
from .models import SiteImage
from .resolver import invalidate_index


@dataclass
class CustomImage:
    data: bytes
    checksum: str
    content_type: str
    width: int
    height: int


_CUSTOM_CACHE: dict[str, CustomImage] = {}


def get_custom_image(name: str) -> CustomImage | None:
    """Retrieve custom image asset in memory."""
    meta = get_asset_meta(name)
    if meta is None:
        return None
    cached = _CUSTOM_CACHE.get(name)
    if cached is not None:
        return cached

    data = get_asset_bytes(name)
    if data is None:
        return None

    image = CustomImage(
        data=data,
        checksum=meta["checksum"],
        content_type=meta.get("content_type", "image/jpeg"),
        width=meta.get("width", 750),
        height=meta.get("height", 1000),
    )
    _CUSTOM_CACHE[name] = image
    return image


def get_custom_checksum(name: str) -> str | None:
    meta = get_asset_meta(name)
    return meta["checksum"] if meta else None


def sync_custom_images() -> int:
    """Ensure curated custom assets exist in SiteImage with current bytes."""
    updated = 0
    for name in ("maker-chen-meilin", "maker-lu-wenjing"):
        meta = get_asset_meta(name)
        custom = get_custom_image(name)
        if meta is None or custom is None:
            continue

        SiteImage.objects.update_or_create(
            name=name,
            defaults={
                "ratio": meta.get("ratio", "tall"),
                "alt_text": meta.get("alt_text", ""),
                "data": custom.data,
                "content_type": custom.content_type,
                "width": custom.width,
                "height": custom.height,
                "byte_size": len(custom.data),
                "checksum": custom.checksum,
            },
        )
        updated += 1

    if updated:
        invalidate_index()
    return updated
