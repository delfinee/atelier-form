"""Openverse search, image download and crop-to-box encoding.

Openverse aggregates openly licensed media and needs no API key, which keeps
the project inside its budget rule -- no paid service, so nothing to approve.
The anonymous quota is 200 requests a day and 20 a minute, so every search
response is cached on disk: a re-run, a retry or a `--refresh` of one product
costs nothing.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from dataclasses import dataclass, replace
from pathlib import Path

import requests
from django.conf import settings
from PIL import Image, ImageOps

from .models import RATIOS

API = "https://api.openverse.org/v1/images/"
USER_AGENT = "AtelierForm/1.0 (NTU EE3180 DIP E006; educational project)"

# Request licences that permit commercial use and modification.
DEFAULT_LICENCE_FILTER = "commercial,modification"

# Route usage filters and licence names to the correct Openverse parameter.
_LICENCE_TYPE_WORDS = {"all", "all-cc", "commercial", "modification"}

CACHE_DIR = Path(settings.BASE_DIR) / ".imagery-cache"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
TIMEOUT = 30
JPEG_QUALITY = 82


@dataclass
class Candidate:
    """One Openverse result, flattened to what selection and storage need."""

    source_id: str
    url: str
    thumbnail: str
    width: int
    height: int
    title: str
    creator: str
    creator_url: str
    provider: str
    source_url: str
    license: str
    license_version: str
    license_url: str
    attribution: str
    tags: tuple[str, ...] = ()
    # Store the query ladder tier that produced this result.
    tier: int = 0
    query: str = ""

    @classmethod
    def from_result(cls, result: dict) -> "Candidate":
        return cls(
            source_id=result.get("id", ""),
            url=result.get("url", ""),
            thumbnail=result.get("thumbnail", ""),
            width=int(result.get("width") or 0),
            height=int(result.get("height") or 0),
            title=(result.get("title") or "")[:300],
            creator=(result.get("creator") or "")[:200],
            creator_url=(result.get("creator_url") or "")[:500],
            provider=(result.get("provider") or "")[:60],
            source_url=(result.get("foreign_landing_url") or "")[:500],
            license=(result.get("license") or "")[:40],
            license_version=(result.get("license_version") or "")[:20],
            license_url=(result.get("license_url") or "")[:500],
            attribution=result.get("attribution") or "",
            tags=tuple(
                (tag.get("name") or "").lower()
                for tag in (result.get("tags") or [])
                if isinstance(tag, dict)
            )[:40],
        )

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def fingerprint(self) -> str:
        """Identity for de-duplication within a group.

        Aggregators carry the same photograph under several ids -- five near
        identical museum shots of one bowl -- so matching on id alone would
        still put the same picture in all three views of a product.
        """
        return f"{self.creator.strip().lower()}|{self.title.strip().lower()[:60]}"

    def relevance(self) -> float:
        """How much of the query the result actually depicts, from 0 to 1.

        Openverse matches terms anywhere in a record, so `cotton throw` happily
        returns a photograph of a junk drawer that mentions cotton in its
        description and "throw" in a comment. Requiring the words to show up in
        the title or the tags is what separates a subject from a coincidence.
        """
        # Ignore very short query words when scoring relevance.
        words = [w for w in self.query.lower().split() if len(w) >= 3]
        if not words:
            return 1.0
        haystack = f"{self.title.lower()} {' '.join(self.tags)}"
        return sum(1 for word in words if word in haystack) / len(words)


class RateLimiter:
    """Space requests out to stay under the 20-per-minute burst allowance."""

    def __init__(self, per_minute: int = 15):
        self._interval = 60.0 / max(per_minute, 1)
        self._last = 0.0

    def wait(self) -> None:
        gap = self._interval - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()


class Openverse:
    def __init__(self, licence_filter: str = DEFAULT_LICENCE_FILTER, use_cache: bool = True):
        self.licence_filter = licence_filter
        self.use_cache = use_cache
        self.limiter = RateLimiter()
        # Give downloads a separate rate limit from searches.
        self.download_limiter = RateLimiter(per_minute=40)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.requests_made = 0
        self.cache_hits = 0
        self.throttled = 0

    # -- search -----------------------------------------------------------
    def _licence_params(self) -> dict[str, str]:
        tokens = [token.strip() for token in self.licence_filter.split(",") if token.strip()]
        if tokens and all(token in _LICENCE_TYPE_WORDS for token in tokens):
            return {"license_type": ",".join(tokens)}
        return {"license": ",".join(tokens)}

    def _cache_path(self, query: str, page_size: int) -> Path:
        key = hashlib.sha256(
            f"{query}|{page_size}|{self.licence_filter}".encode()
        ).hexdigest()[:20]
        return CACHE_DIR / f"{key}.json"

    def search(self, query: str, page_size: int = 20) -> list[Candidate]:
        path = self._cache_path(query, page_size)
        payload = None
        if self.use_cache and path.exists():
            try:
                payload = json.loads(path.read_text())
                self.cache_hits += 1
            except (OSError, json.JSONDecodeError):
                # Ignore incomplete cache files and fetch fresh results.
                payload = None
        if payload is None:
            payload = self._request(query, page_size)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            # Write through a temporary file so the cache is always complete.
            temporary = path.with_suffix(".partial")
            temporary.write_text(json.dumps(payload))
            temporary.replace(path)

        return [replace(Candidate.from_result(r), query=query)
                for r in payload.get("results", [])]

    def _request(self, query: str, page_size: int) -> dict:
        """One search, retrying while Openverse is throttling us.

        Exceeding the burst allowance answers 403 or 429 rather than queueing.
        Losing a whole group's slots to a transient limit would leave permanent
        placeholders, so the backoff is worth the wait.
        """
        delay = 20.0
        last: Exception | None = None
        # Retry throttled requests and let refused queries fall through the ladder.
        attempts = {403: 2, 429: 4}
        limit = 4
        for attempt in range(limit):
            self.limiter.wait()
            response = self.session.get(API, timeout=TIMEOUT, params={
                "q": query,
                "page_size": page_size,
                "mature": "false",
                "extension": "jpg,jpeg,png",
                **self._licence_params(),
            })
            self.requests_made += 1
            if response.status_code in attempts:
                last = requests.HTTPError(f"{response.status_code} from Openverse")
                self.throttled += 1
                limit = attempts[response.status_code]
                if attempt < limit - 1:
                    time.sleep(delay)
                    delay *= 2
                continue
            response.raise_for_status()
            return response.json()
        raise last or RuntimeError("search failed")

    def search_ladder(self, queries: list[str], needed: int) -> list[Candidate]:
        """Walk a query ladder from most specific to broadest.

        Openverse ANDs every term, so `ceramicist artisan craftsperson workshop`
        matches nothing at all while `ceramicist` matches hundreds. Rather than
        guess the one phrase that is both specific and non-empty, each group
        offers several in descending specificity; this stops at the first that
        supplies enough candidates, and records how far down it had to go.
        """
        found: list[Candidate] = []
        seen: set[str] = set()
        refused: list[str] = []
        for tier, query in enumerate(queries):
            try:
                results = self.search(query)
            except Exception as exc:  # noqa: BLE001
                # Record a refused rung and continue with broader queries.
                refused.append(f"{query!r}: {exc}")
                continue
            for candidate in results:
                if candidate.source_id in seen:
                    continue
                seen.add(candidate.source_id)
                found.append(replace(candidate, tier=tier))
            if len(found) >= needed:
                break
        if not found and refused:
            raise RuntimeError("; ".join(refused))
        return found

    # -- download ---------------------------------------------------------
    def download(self, candidate: Candidate) -> bytes:
        """Fetch the full image, falling back to the Openverse thumbnail proxy.

        Aggregated links go to Flickr, museums and the like, and a fair number
        are dead or hotlink-blocked; the proxy is the reliable second try.
        """
        errors = []
        for url in (candidate.url, candidate.thumbnail):
            if not url:
                continue
            try:
                return self._get_bytes(url)
            except Exception as exc:  # noqa: BLE001 -- any failure means "try the next source"
                errors.append(f"{url}: {exc}")
        raise RuntimeError("; ".join(errors) or "no downloadable URL")

    def _get_bytes(self, url: str) -> bytes:
        # Rate-limit thumbnail proxy downloads like searches.
        if url.startswith(API.rsplit("/v1/", 1)[0]):
            self.limiter.wait()
        else:
            self.download_limiter.wait()
        with self.session.get(url, timeout=TIMEOUT, stream=True) as response:
            response.raise_for_status()
            chunks, total = [], 0
            for chunk in response.iter_content(64 * 1024):
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError("image exceeds the size cap")
                chunks.append(chunk)
        return b"".join(chunks)


# -- selection ------------------------------------------------------------

def score(candidate: Candidate, ratio: str) -> float:
    """Higher is better. Penalises heavy cropping and thin source resolution.

    Aspect distance dominates: a photograph whose shape already matches the box
    keeps its subject when cropped, whereas a panorama forced into a 4:5 tile
    loses whatever made it worth choosing.
    """
    target_w, target_h = RATIOS[ratio]
    if not candidate.width or not candidate.height or not candidate.url:
        return -1.0

    target_aspect = target_w / target_h
    aspect_penalty = abs(candidate.aspect - target_aspect) / target_aspect

    # Reject sources that would need heavy upscaling.
    coverage = min(candidate.width / target_w, candidate.height / target_h, 1.0)
    if coverage < 0.5:
        return -1.0

    # Penalize broad query tiers so specific matches rank higher.
    value = coverage * 2.0 - aspect_penalty - 0.4 * candidate.tier

    # Penalize results whose title and tags do not match the query.
    relevance = candidate.relevance()
    return value + 1.2 * relevance - (1.5 if relevance == 0 else 0.0)


def rank(candidates: list[Candidate], ratio: str) -> list[Candidate]:
    scored = [(score(c, ratio), c) for c in candidates]
    return [c for value, c in sorted(scored, key=lambda pair: pair[0], reverse=True) if value > 0]


# -- encoding -------------------------------------------------------------

def to_jpeg(raw: bytes, ratio: str) -> tuple[bytes, int, int]:
    """Centre-crop to the layout's box and encode a progressive JPEG.

    `ImageOps.fit` crops rather than letterboxes, which is what the templates
    already assume -- every `<img>` is styled `object-fit: cover`.
    """
    target = RATIOS[ratio]
    with Image.open(io.BytesIO(raw)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            # Flatten transparency onto white rather than letting RGBA -> RGB
            # turn the alpha channel into black fringing.
            background = Image.new("RGB", image.size, (255, 255, 255))
            converted = image.convert("RGBA")
            background.paste(converted, mask=converted.split()[-1])
            image = background
        else:
            image = image.convert("RGB")

        fitted = ImageOps.fit(image, target, method=Image.LANCZOS, centering=(0.5, 0.45))
        buffer = io.BytesIO()
        fitted.save(buffer, format="JPEG", quality=JPEG_QUALITY,
                    optimize=True, progressive=True)
        return buffer.getvalue(), fitted.width, fitted.height
