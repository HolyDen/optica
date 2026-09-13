"""The Fetch Adapter: sources, downloads, and auto-fetch staging.

Implements plan § "Input & Acquisition" → *Input Manager* (Fetch Adapter),
*Fetch sources*, *Class imbalance and image validation* (fetched-image naming,
validation at the write into staging), and § "Labeling & Curation" → *Staging
shapes* (fetch completion via ``.partial``) and *Deletion, staging, and
interruption*.

**Registry dispatch.** ``--source`` routes through :data:`SOURCES`, a dictionary
keyed on source name with one registration point (:func:`register_source`), so a
post-V1 source touches one file and nothing branches on source names elsewhere.

**Fill to target.** Dead URLs are expected rather than exceptional, so a class
draws candidates until ``images_per_class`` valid images are staged or its
candidate pool is exhausted. An exhausted pool is a *completed* fetch with a
shortfall, not a failure: the shortfall reaches the imbalance warning and the
floor re-check like any other short class.

**Staging.** A class fetches into ``~/.optica/staging/<class>.partial/`` and is
renamed to ``<class>/`` when its fetch completes, so a ``.partial`` directory
means interrupted and nothing else. Files are named by zero-padded sequence
index — ``0001.jpg`` — never by URL basename, and numbering continues from the
highest index already present, which is what makes resuming safe.

The Flickr adapter is written against ``notes/verified.md`` § "Flickr API" and
has **never been run against a real key**: ``.env`` holds none, and Flickr issues
keys to Pro subscribers only.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Final, Protocol

import httpx

from optica.exceptions import OpticaFetchError, OpticaValidationError
from optica.input.classes import ResolvedClass
from optica.input.openimages import OpenImagesIndex
from optica.input.sessions import atomic_write_json, staging_root
from optica.input.validation import RejectReason, md5_of, process_owned

__all__ = [
    "CANDIDATE_SLACK",
    "FLICKR_MAX_RESULTS",
    "FLICKR_REST_URL",
    "SOURCES",
    "Candidate",
    "ClassFetchReport",
    "Downloader",
    "FetchSource",
    "FlickrSource",
    "ImageGetter",
    "OpenImagesSource",
    "SourceContext",
    "StagedClass",
    "create_source",
    "fetch_class",
    "make_client",
    "register_source",
    "staged_classes",
    "staged_images",
]

CANDIDATE_SLACK: Final = 1.5
"""Candidates requested per image wanted. ~18% of Open Images thumbnails are dead
(``notes/verified.md``), and validation rejects some of the rest."""

FLICKR_REST_URL: Final = "https://www.flickr.com/services/rest/"
FLICKR_MAX_PER_PAGE: Final = 500
FLICKR_MAX_RESULTS: Final = 4000
"""Flickr returns at most the first 4,000 results for any search query."""
FLICKR_MIN_INTERVAL: Final = 1.0
"""Seconds between API calls: 3,600 queries per hour per key, evenly spent."""
FLICKR_RETRYABLE: Final = frozenset({10, 105})
_FLICKR_EXTRAS: Final = ("url_z", "url_c", "url_m")

_MAX_IMAGE_BYTES: Final = 30 << 20
_DOWNLOAD_RETRIES: Final = 3
_STAGED_NAME: Final = re.compile(r"^(\d+)\.(jpg|png|webp)$")
_SIDECAR: Final = ".fetch.json"

Report = Callable[[str], None]


def make_client() -> httpx.Client:
    """The HTTP client every fetch uses. Identifies Optica to the hosts it calls."""
    try:
        version = importlib_metadata.version("optica")
    except importlib_metadata.PackageNotFoundError:
        version = "unknown"
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        headers={"User-Agent": f"optica/{version} (+https://github.com/HolyDen/optica)"},
    )


# ------------------------------------------------------------------ sources


@dataclass(frozen=True)
class Candidate:
    """One image a source offers for a query.

    Attributes:
        key: Stable within the source — a Flickr photo ID, an Open Images
            ``ImageID`` — so a later fetch does not retry it.
        url: Where the bytes are.
    """

    key: str
    url: str


@dataclass
class SourceContext:
    """What a source is constructed with.

    Attributes:
        client: The shared HTTP client.
        api_key: ``flickr_api_key`` from the resolved config, if any.
        home: The home directory holding ``.optica/``.
        report: Receives short status lines.
        sleep: Injected for tests.
    """

    client: httpx.Client
    api_key: str | None = None
    home: Path | None = None
    report: Report = field(default=lambda _message: None)
    sleep: Callable[[float], None] = time.sleep


class FetchSource(Protocol):
    """A remote image source."""

    name: str
    display_name: str

    def prepare(self, queries: Sequence[str]) -> None:
        """Check everything knowable before any prompt or download.

        A missing key or an unknown class name fails here, at entry.
        """
        ...

    def warm(self, needed: dict[str, int]) -> None:
        """Optionally search several queries at once before per-class fetching."""
        ...

    def candidates(self, query: str, batch: int) -> Iterator[Candidate]:
        """Yield candidates for ``query``, extending lazily; end when exhausted."""
        ...


SourceFactory = Callable[[SourceContext], FetchSource]
SOURCES: dict[str, SourceFactory] = {}
"""The source registry. :func:`register_source` is its one registration point."""


def register_source(name: str) -> Callable[[SourceFactory], SourceFactory]:
    """Register a source factory under its ``--source`` name."""

    def decorator(factory: SourceFactory) -> SourceFactory:
        SOURCES[name] = factory
        return factory

    return decorator


def create_source(name: str, context: SourceContext) -> FetchSource:
    """Construct the source ``--source`` names.

    Raises:
        OpticaValidationError: For an unknown name, listing the valid ones.
    """
    factory = SOURCES.get(name)
    if factory is None:
        raise OpticaValidationError(
            f"--source {name} is not a known source.",
            options=sorted(SOURCES),
            default="open-datasets",
        )
    return factory(context)


def _query_text(query: str) -> str:
    return re.sub(r"[_\s]+", " ", query).strip()


@register_source("open-datasets")
class OpenImagesSource:
    """Google Open Images — no API key; image bytes come from Flickr's CDN."""

    name = "open-datasets"
    display_name = "Open Images"

    def __init__(self, context: SourceContext) -> None:
        self.index = OpenImagesIndex(context.client, context.home, context.report)
        self._mids: dict[str, str] = {}

    def prepare(self, queries: Sequence[str]) -> None:
        """Map every query to an Open Images class, or fail naming each unknown one."""
        found = self.index.label_map.require(list(queries))
        self._mids.update({query: mid for query, (mid, _) in found.items()})

    def warm(self, needed: dict[str, int]) -> None:
        """Search every class's candidates in one shared read."""
        mids = [self._mids[query] for query in needed]
        self.index.ensure(mids, {self._mids[q]: n for q, n in needed.items()})

    def candidates(self, query: str, batch: int) -> Iterator[Candidate]:
        """Yield resolved Open Images URLs for ``query``.

        Per image, ``Thumbnail300KURL`` is preferred, with ``OriginalURL`` where
        that **value** is empty.
        """
        if query not in self._mids:
            self.prepare([query])
        for image in self.index.candidates(self._mids[query], batch):
            if image.url:
                yield Candidate(image.image_id, image.url)


@register_source("flickr")
class FlickrSource:
    """Flickr's official ``flickr.photos.search``.

    Written against ``notes/verified.md`` § "Flickr API"; never exercised with a
    real key.
    """

    name = "flickr"
    display_name = "Flickr"

    def __init__(self, context: SourceContext) -> None:
        self.client = context.client
        self.api_key = context.api_key
        self.report = context.report
        self.sleep = context.sleep
        self._last_call = 0.0

    def prepare(self, queries: Sequence[str]) -> None:
        """Refuse to start without a key.

        Raises:
            OpticaFetchError: When no ``FLICKR_API_KEY`` is configured.
        """
        if not self.api_key:
            raise OpticaFetchError(
                "Flickr needs an API key, and none is set.",
                why="Flickr issues API keys to Flickr Pro subscribers only.",
                fix=[
                    "Run: optica config --set flickr_api_key <your-key>",
                    "Or export FLICKR_API_KEY in your environment.",
                    "Or fetch without a key: --source open-datasets",
                ],
            )

    def warm(self, needed: dict[str, int]) -> None:
        """Nothing to share between Flickr searches."""

    def _call(self, params: dict[str, str | int]) -> dict[str, Any]:
        for attempt in range(_DOWNLOAD_RETRIES + 1):
            wait = self._last_call + FLICKR_MIN_INTERVAL - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._last_call = time.monotonic()
            try:
                response = self.client.get(FLICKR_REST_URL, params=params)
            except httpx.TransportError as exc:
                if attempt == _DOWNLOAD_RETRIES:
                    raise OpticaFetchError(
                        "Could not reach Flickr.",
                        why=f"{type(exc).__name__}: {exc}",
                        fix="Check your internet connection and run the same command "
                        "again; anything already fetched is kept.",
                    ) from exc
                self.sleep(2.0**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                pause = _retry_after(response, default=30.0 * (attempt + 1))
                self.report(f"Flickr rate limit reached — pausing {pause:.0f} s.")
                self.sleep(pause)
                continue
            # A failed call returns HTTP 200: only `stat` in the body tells.
            try:
                data = response.json()
            except ValueError as exc:
                raise OpticaFetchError(
                    "Flickr returned a response Optica could not read.",
                    why=f"HTTP {response.status_code}, not JSON.",
                    fix="Run the same command again later.",
                ) from exc
            if data.get("stat") == "ok":
                return dict(data)
            code = int(data.get("code", 0) or 0)
            message = str(data.get("message", "unknown error"))
            if code == 100:
                raise OpticaFetchError(
                    "Flickr rejected the API key.",
                    why=f"Flickr says: {message}",
                    fix=[
                        "Check the key: optica config --view",
                        "Set a new one: optica config --set flickr_api_key <your-key>",
                    ],
                )
            if code in FLICKR_RETRYABLE and attempt < _DOWNLOAD_RETRIES:
                self.report(
                    f"Flickr search is temporarily unavailable — retrying ({message})."
                )
                self.sleep(10.0 * (attempt + 1))
                continue
            raise OpticaFetchError(
                f"Flickr search failed (error {code}).",
                why=f"Flickr says: {message}",
                fix="Run the same command again later, or use --source open-datasets.",
            )
        raise OpticaFetchError(
            "Flickr kept refusing requests.",
            why="Retries were exhausted.",
            fix="Wait a while and run the same command again; anything already "
            "fetched is kept.",
        )

    def candidates(self, query: str, batch: int) -> Iterator[Candidate]:
        """Page through ``flickr.photos.search`` for ``query``."""
        per_page = max(1, min(FLICKR_MAX_PER_PAGE, batch))
        page = 1
        while (page - 1) * per_page < FLICKR_MAX_RESULTS:
            data = self._call(
                {
                    "method": "flickr.photos.search",
                    "api_key": self.api_key or "",
                    "text": _query_text(query),
                    "sort": "relevance",
                    "content_types": 0,
                    "media": "photos",
                    "safe_search": 1,
                    "extras": ",".join(_FLICKR_EXTRAS),
                    "per_page": per_page,
                    "page": page,
                    "format": "json",
                    "nojsoncallback": 1,
                }
            )
            photos = data.get("photos", {})
            for photo in photos.get("photo", []):
                url = next((photo[k] for k in _FLICKR_EXTRAS if photo.get(k)), None)
                if url:
                    yield Candidate(str(photo.get("id", url)), str(url))
            pages = int(photos.get("pages", 0) or 0)
            if page >= pages:
                return
            page += 1


def _retry_after(response: httpx.Response, *, default: float) -> float:
    try:
        return max(1.0, float(response.headers.get("retry-after", "")))
    except ValueError:
        return default


# ---------------------------------------------------------------- downloads


class ImageGetter(Protocol):
    """Anything that can fetch image bytes, returning None for a dead URL."""

    def get(self, url: str) -> bytes | None:
        """The body at ``url``, or None."""
        ...


class Downloader:
    """Fetch image bytes, treating dead URLs as expected.

    Args:
        client: The shared HTTP client.
        sleep: Injected for tests.
    """

    def __init__(
        self, client: httpx.Client, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.client = client
        self.sleep = sleep

    def get(self, url: str) -> bytes | None:
        """The body at ``url``, or None when the URL is dead or unreachable.

        404, 410 and 403 are dead immediately. 429 and 5xx retry with backoff, as
        do transport errors; a URL still failing afterwards is treated as dead,
        because a fetch fills to target from the rest of the pool rather than
        stopping on one host. A body over 30 MB is not a plausible image and is
        abandoned.
        """
        for attempt in range(_DOWNLOAD_RETRIES):
            try:
                with self.client.stream("GET", url) as response:
                    if response.status_code in (403, 404, 410):
                        return None
                    if response.status_code == 429 or response.status_code >= 500:
                        pause = _retry_after(response, default=2.0**attempt)
                    elif response.status_code != 200:
                        return None
                    else:
                        chunks: list[bytes] = []
                        size = 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > _MAX_IMAGE_BYTES:
                                return None
                            chunks.append(chunk)
                        return b"".join(chunks)
            except httpx.TransportError:
                pause = 2.0**attempt
            if attempt < _DOWNLOAD_RETRIES - 1:
                self.sleep(min(pause, 30.0))
        return None


# ------------------------------------------------------------------ staging


@dataclass(frozen=True)
class StagedClass:
    """One class directory in auto-fetch staging.

    Attributes:
        name: The class name.
        path: The directory.
        partial: Whether it is a ``.partial`` directory — an interrupted fetch.
        images: How many images it holds.
    """

    name: str
    path: Path
    partial: bool
    images: int


def _index_of(path: Path) -> int:
    match = _STAGED_NAME.match(path.name)
    return int(match.group(1)) if match else 0


def staged_images(folder: Path) -> list[Path]:
    """The sequence-named images in one staging class directory, sorted."""
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir() if p.is_file() and _STAGED_NAME.match(p.name)
    )


def staged_classes(home: Path | None = None) -> list[StagedClass]:
    """Every class directory in staging, complete and ``.partial``, name-sorted."""
    root = staging_root(home)
    if not root.is_dir():
        return []
    found: list[StagedClass] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name == "labeling":
            continue
        partial = entry.name.endswith(".partial")
        name = entry.name.removesuffix(".partial")
        found.append(StagedClass(name, entry, partial, len(staged_images(entry))))
    return found


@dataclass
class ClassFetchReport:
    """What one class's fetch did. Nothing is silent.

    Attributes:
        name: The class.
        target: Images the class aims for.
        existing: Valid images already staged when this run began.
        delivered: Valid images staged by this run.
        dead: Candidates whose URL was dead or unreachable.
        unreadable: Downloads that failed validation — deleted, reported as a
            count, since the user never chose those files.
        duplicates: Downloads byte-identical to an image already staged.
        resized: Images upscaled to the size threshold (a quality warning).
        converted: Images converted to a targeted format.
        exhausted: Whether the candidate pool ran out before the target.
    """

    name: str
    target: int
    existing: int = 0
    delivered: int = 0
    dead: int = 0
    unreadable: int = 0
    duplicates: int = 0
    resized: int = 0
    converted: int = 0
    exhausted: bool = False

    @property
    def staged(self) -> int:
        """Images in the class's staging directory now."""
        return self.existing + self.delivered

    @property
    def shortfall(self) -> int:
        """How far below target the class finished."""
        return max(0, self.target - self.staged)


def _read_sidecar(folder: Path, source: str) -> dict[str, Any]:
    try:
        data = json.loads((folder / _SIDECAR).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError
    except (OSError, ValueError):
        data = {"version": 1, "sources": {}}
    record = data.setdefault("sources", {}).setdefault(source, {})
    record.setdefault("tried", {})
    record.setdefault("delivered", {})
    return data


def fetch_class(
    cls: ResolvedClass,
    source: FetchSource,
    downloader: ImageGetter,
    home: Path | None = None,
    *,
    on_image: Callable[[], None] | None = None,
) -> ClassFetchReport:
    """Fetch one class into staging, filling to target.

    Writes into ``<class>.partial/``, continuing numbering and skipping
    candidates already tried there. A class already complete in staging is
    topped up: it is moved back to ``.partial`` for the duration, so an interrupt
    leaves the same signal as any other. Every download passes the per-file
    stages at the write — this *is* the pre-flight for auto-fetched images — and
    MD5 deduplication within the class. On completion, including an exhausted
    pool, the directory is renamed to ``<class>/``.

    ``KeyboardInterrupt`` is deliberately not caught: the ``.partial`` directory
    is the interrupted state, and deleting nothing is how it is preserved.
    """
    root = staging_root(home)
    final = root / cls.name
    partial = root / f"{cls.name}.partial"
    root.mkdir(parents=True, exist_ok=True)
    if final.is_dir() and not partial.exists():
        final.rename(partial)
    partial.mkdir(exist_ok=True)

    existing = staged_images(partial)
    hashes = {md5_of(path.read_bytes()) for path in existing}
    # Numbering continues from the highest index already present.
    next_index = max((_index_of(path) for path in existing), default=0) + 1
    report = ClassFetchReport(cls.name, cls.target, existing=len(existing))

    sidecar = _read_sidecar(partial, source.name)
    record = sidecar["sources"][source.name]

    for query in cls.queries:
        tried: set[str] = set(record["tried"].get(query, []))
        if len(cls.queries) == 1:
            needed = cls.target - report.staged
        else:
            needed = cls.per_query - int(record["delivered"].get(query, 0))
        if needed <= 0:
            continue
        batch = max(1, math.ceil(needed * CANDIDATE_SLACK))
        got = 0
        exhausted = True
        for candidate in source.candidates(query, batch):
            if candidate.key in tried:
                continue
            tried.add(candidate.key)
            record["tried"][query] = sorted(tried)
            data = downloader.get(candidate.url)
            if data is None:
                report.dead += 1
                continue
            processed = process_owned(data)
            if isinstance(processed, RejectReason):
                report.unreadable += 1
                continue
            digest = md5_of(processed.data)
            if digest in hashes:
                report.duplicates += 1
                continue
            hashes.add(digest)
            name = f"{next_index:04d}{processed.extension}"
            temp = partial / f".{name}.tmp"
            temp.write_bytes(processed.data)
            temp.replace(partial / name)
            next_index += 1
            got += 1
            report.delivered += 1
            report.resized += int(processed.resized)
            report.converted += int(processed.converted)
            record["delivered"][query] = int(record["delivered"].get(query, 0)) + 1
            atomic_write_json(partial / _SIDECAR, sidecar)
            if on_image is not None:
                on_image()
            if got >= needed:
                exhausted = False
                break
        atomic_write_json(partial / _SIDECAR, sidecar)
        if exhausted and got < needed:
            report.exhausted = True

    if final.exists():
        # Only reachable if something else created it mid-fetch; never merge.
        raise OpticaFetchError(
            f"{final} appeared while its fetch was running.",
            why="Staging is single-session, and another process wrote to it.",
            fix="Clear it and fetch again: optica config --clear-staging",
        )
    partial.rename(final)
    return report
