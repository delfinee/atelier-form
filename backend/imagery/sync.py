"""Sync and serve curated custom assets."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .models import SiteImage
from .resolver import invalidate_index

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

CUSTOM_IMAGES: dict[str, dict] = {
    "maker-chen-meilin": {
        "filename": "maker-chen-meilin.jpg",
        "ratio": "tall",
        "alt_text": "Chen Meilin, Ceramicist",
        "content_type": "image/jpeg",
        "width": 750,
        "height": 1000,
    },
    "maker-lu-wenjing": {
        "filename": "maker-lu-wenjing.jpg",
        "ratio": "tall",
        "alt_text": "Lu Wenjing, Weaver & natural dyer",
        "content_type": "image/jpeg",
        "width": 750,
        "height": 1000,
    },
}


@dataclass
class CustomImage:
    data: bytes
    checksum: str
    content_type: str
    width: int
    height: int


_CUSTOM_CACHE: dict[str, CustomImage] = {}


def get_custom_image(name: str) -> CustomImage | None:
    """Retrieve custom image asset in memory if configured and present on disk."""
    if name not in CUSTOM_IMAGES:
        return None
    cached = _CUSTOM_CACHE.get(name)
    if cached is not None:
        return cached

    meta = CUSTOM_IMAGES[name]
    asset_file = ASSETS_DIR / meta["filename"]
    if not asset_file.exists():
        return None

    data = asset_file.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    image = CustomImage(
        data=data,
        checksum=checksum,
        content_type=meta.get("content_type", "image/jpeg"),
        width=meta.get("width", 750),
        height=meta.get("height", 1000),
    )
    _CUSTOM_CACHE[name] = image
    return image


def get_custom_checksum(name: str) -> str | None:
    img = get_custom_image(name)
    return img.checksum if img else None


def sync_custom_images() -> int:
    """Ensure curated custom assets exist in SiteImage with current bytes."""
    updated = 0
    for name, meta in CUSTOM_IMAGES.items():
        custom = get_custom_image(name)
        if custom is None:
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
