"""Sync curated or local custom assets into the database SiteImage table."""
from __future__ import annotations

import hashlib
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


def sync_custom_images() -> int:
    """Ensure curated custom assets exist in SiteImage with current bytes."""
    updated = 0
    for name, meta in CUSTOM_IMAGES.items():
        asset_file = ASSETS_DIR / meta["filename"]
        if not asset_file.exists():
            continue
        data = asset_file.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()

        # Update or create the record with the latest bytes and dimensions
        SiteImage.objects.update_or_create(
            name=name,
            defaults={
                "ratio": meta.get("ratio", "tall"),
                "alt_text": meta.get("alt_text", ""),
                "data": data,
                "content_type": meta.get("content_type", "image/jpeg"),
                "width": meta.get("width", 750),
                "height": meta.get("height", 1000),
                "byte_size": len(data),
                "checksum": checksum,
            },
        )
        updated += 1

    if updated:
        invalidate_index()
    return updated

