"""Open Images: the class list, and a per-class index of candidate image URLs.

Implements plan § "Input & Acquisition" → *Fetch sources* (Open Datasets), and
Implementation Notes 5 and 13. The strategy is Optica's own — the plan leaves it
open on purpose — and is logged with its reasoning and cost model in
``notes/build-log.md`` § "Open Images image-URL acquisition strategy". The facts
it rests on are in ``notes/verified.md`` § "Open Images — which files map a class
to image URLs".

In short:

- **Class list.** ``oidv7-class-descriptions.csv`` (20,931 classes) is cached in
  ``~/.optica/openimages/`` beside the MD5 GCS reported for it, and verified on
  every load; a mismatch deletes and re-downloads it.
- **Candidates.** The V7 human-verified train label file is sorted by
  ``ImageID``, so it is read in byte ranges spread over 64 stripes rather than
  from the top, where it is sparsest. ``Confidence == 1`` rows for the wanted
  classes become candidate image IDs.
- **URLs.** The V6 train metadata file is in no order, so the only way to find
  an image's URLs is to read it. It is streamed, matching each line's leading
  ``ImageID`` against the unresolved candidates, until enough are resolved.
- **Cache.** What a class's search found — stripe cursors, candidates, resolved
  URLs, the metadata cursor — is kept per class and keyed to both files' ETags,
  so a later fetch of the same class continues rather than starting again.

No API key is involved anywhere, and nothing here downloads an image: the image
bytes come from the URLs this module yields, which point at Flickr's CDN.
"""

from __future__ import annotations

import base64
import csv
import difflib
import hashlib
import io
import json
import math
import re
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import httpx

from optica.exceptions import OpticaFetchError, OpticaValidationError
from optica.input.sessions import atomic_write_json

__all__ = [
    "CHUNK_BYTES",
    "LABELS_URL",
    "LABEL_MAP_URL",
    "METADATA_URL",
    "STRIPES",
    "ClassIndex",
    "LabelMap",
    "OpenImagesIndex",
    "ResolvedImage",
    "cache_dir",
    "gcs_md5",
    "load_label_map",
]

GCS_BASE: Final = "https://storage.googleapis.com/openimages"
LABEL_MAP_URL: Final = f"{GCS_BASE}/v7/oidv7-class-descriptions.csv"
LABELS_URL: Final = f"{GCS_BASE}/v7/oidv7-train-annotations-human-imagelabels.csv"
METADATA_URL: Final = f"{GCS_BASE}/v6/oidv6-train-images-with-labels-with-rotation.csv"

STRIPES: Final = 64
CHUNK_BYTES: Final = 1 << 20
POSITIVE_FLOOR_FACTOR: Final = 4
"""Never search the metadata with fewer than this many candidates per URL
needed: below it, the join would read most of a 2.5 GiB file to find them."""

INDEX_VERSION: Final = 1
_ID_LENGTH: Final = 16
_HEX_ID: Final = re.compile(rb"^[0-9a-f]{16},")
_RETRIES: Final = 3

ProgressCallback = Callable[[str], None]


def cache_dir(home: Path | None = None) -> Path:
    """``~/.optica/openimages/``. A verified cache, not session state."""
    return (home or Path.home()) / ".optica" / "openimages"


def gcs_md5(headers: httpx.Headers) -> str | None:
    """The base64 MD5 GCS reports in ``x-goog-hash``, or None.

    GCS sends ``crc32c`` and ``md5`` either as two headers or comma-joined in one.
    """
    for value in headers.get_list("x-goog-hash"):
        for part in value.split(","):
            key, _, digest = part.strip().partition("=")
            if key == "md5" and digest:
                return digest
    return None


def _md5_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode()


def _network_error(what: str, exc: Exception) -> OpticaFetchError:
    return OpticaFetchError(
        f"Could not download {what} from Open Images.",
        why=f"{type(exc).__name__}: {exc}",
        fix="Check your internet connection and run the same command again; "
        "anything already fetched is kept.",
    )


def _get(
    client: httpx.Client, url: str, what: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    """GET with a small retry for transient failures."""
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            response = client.get(url, headers=headers)
        except httpx.TransportError as exc:
            last = exc
        else:
            if response.status_code < 500 and response.status_code != 429:
                if response.status_code >= 400:
                    raise OpticaFetchError(
                        f"Open Images returned HTTP {response.status_code} for {what}.",
                        why=f"URL: {url}",
                        fix="The dataset files may have moved; see notes on the Open "
                        "Images download page, or use --source flickr.",
                    )
                return response
            last = httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        time.sleep(0.5 * (2**attempt))
    assert last is not None
    raise _network_error(what, last)


# ----------------------------------------------------------------- class list


@dataclass(frozen=True)
class LabelMap:
    """Open Images display names and their MIDs.

    Attributes:
        by_name: Case-folded display name to ``(mid, display name)``.
        path: Where the verified cache lives.
    """

    by_name: dict[str, tuple[str, str]]
    path: Path

    @classmethod
    def parse(cls, data: bytes, path: Path) -> LabelMap:
        """Build the map from the CSV's bytes (header ``LabelName,DisplayName``)."""
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        by_name: dict[str, tuple[str, str]] = {}
        for row in reader:
            if len(row) != 2 or row[0] == "LabelName":
                continue
            mid, display = row[0].strip(), row[1].strip()
            by_name.setdefault(display.casefold(), (mid, display))
        return cls(by_name, path)

    @staticmethod
    def _key(name: str) -> str:
        return re.sub(r"\s+", " ", name.replace("_", " ")).strip().casefold()

    def lookup(self, name: str) -> tuple[str, str] | None:
        """``(mid, display name)`` for a class name, or None.

        Matched case-insensitively, with ``_`` read as a space:
        ``golden_retriever`` finds ``Golden retriever``.
        """
        return self.by_name.get(name.strip().casefold()) or self.by_name.get(
            self._key(name)
        )

    def suggestions(self, name: str, limit: int = 3) -> list[str]:
        """Close display names, for an error about an unknown class."""
        matches = difflib.get_close_matches(
            self._key(name), self.by_name, n=limit, cutoff=0.6
        )
        return [self.by_name[match][1] for match in matches]

    def require(self, names: Sequence[str]) -> dict[str, tuple[str, str]]:
        """Map every name, or raise naming every one that is unknown.

        Raises:
            OpticaValidationError: Listing each unknown name with close matches.
        """
        found: dict[str, tuple[str, str]] = {}
        unknown: list[str] = []
        for name in names:
            hit = self.lookup(name)
            if hit is None:
                close = self.suggestions(name)
                hint = f" (did you mean {', '.join(close)}?)" if close else ""
                unknown.append(f"{name}{hint}")
            else:
                found[name] = hit
        if unknown:
            raise OpticaValidationError(
                f"Open Images has no class named: {', '.join(unknown)}",
                why=f"Open Images labels images with a fixed list of "
                f"{len(self.by_name):,} classes, matched by name.",
                fix=[
                    "Use a class name from that list, or search Flickr instead: "
                    "--source flickr",
                    f"The list is cached at {self.path}",
                ],
            )
        return found


def load_label_map(
    client: httpx.Client, home: Path | None = None, report: ProgressCallback | None = None
) -> LabelMap:
    """Load the class list, verifying the cache and repairing it if needed.

    Verified on **every** load against the MD5 GCS reported when it was
    downloaded. A corrupt cache is deleted and downloaded again automatically,
    with a status line naming the path — a cache Optica populated is Optica's to
    repair (Implementation Note 13).

    Raises:
        OpticaFetchError: When the download fails or arrives corrupt.
    """
    say = report or (lambda _message: None)
    folder = cache_dir(home)
    path = folder / "oidv7-class-descriptions.csv"
    digest_path = path.with_name(path.name + ".md5")

    if path.exists() or digest_path.exists():
        try:
            data = path.read_bytes()
            expected = digest_path.read_text(encoding="ascii").strip()
        except OSError:
            data, expected = b"", ""
        if expected and _md5_b64(data) == expected:
            return LabelMap.parse(data, path)
        say(
            f"The cached Open Images class list at {path} is corrupt — "
            "downloading it again."
        )
        path.unlink(missing_ok=True)
        digest_path.unlink(missing_ok=True)
    else:
        say(f"Downloading the Open Images class list to {folder} (first use only).")

    response = _get(client, LABEL_MAP_URL, "the class list")
    data = response.content
    reported = gcs_md5(response.headers)
    actual = _md5_b64(data)
    if reported is not None and reported != actual:
        raise OpticaFetchError(
            "The Open Images class list arrived corrupt.",
            why=f"GCS reported MD5 {reported}; the download hashed to {actual}.",
            fix="Run the same command again.",
        )
    folder.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    temp.replace(path)
    digest_path.write_text(reported or actual, encoding="ascii")
    return LabelMap.parse(data, path)


# ---------------------------------------------------------------- the index


@dataclass(frozen=True)
class ResolvedImage:
    """One candidate image and its URLs.

    Attributes:
        image_id: The Open Images ``ImageID``.
        thumbnail_url: ``Thumbnail300KURL``, possibly empty.
        original_url: ``OriginalURL``.
    """

    image_id: str
    thumbnail_url: str
    original_url: str

    @property
    def url(self) -> str:
        """The URL to fetch first.

        ``Thumbnail300KURL`` is preferred, with ``OriginalURL`` as the fallback
        **where that value is empty** — a per-row test on the value, since the
        column is never absent (plan l.759 as amended; 2.47% of rows are empty).
        """
        return self.thumbnail_url or self.original_url


@dataclass
class ClassIndex:
    """Everything the search has found for one class, as cached.

    Attributes:
        mid: The class MID.
        labels_etag: ETag of the label file this state was read from.
        metadata_etag: ETag of the metadata file.
        stripes: Per stripe, ``[position, aligned]``. Aligned (1): ``position``
            is the start of the next unread line. Not aligned (0): the read
            starts at ``position`` and skips through the first newline — that
            partial line belongs to the stripe before.
        labels_read: Label bytes read so far, for the positive-count estimate.
        positives: Candidate ``ImageID`` to ``metadata_read`` at the moment it
            was found. It is ruled out once the metadata has been read one full
            file-length past that point without finding it.
        resolved: ``ImageID`` to ``[thumbnail, original]``, in discovery order.
        metadata_read: Metadata bytes read so far, monotone across wraps; the
            stream cursor is this modulo the file size.
    """

    mid: str
    labels_etag: str = ""
    metadata_etag: str = ""
    stripes: list[list[int]] = field(default_factory=list)
    labels_read: int = 0
    positives: dict[str, int] = field(default_factory=dict)
    resolved: dict[str, list[str]] = field(default_factory=dict)
    metadata_read: int = 0

    def to_json(self) -> dict[str, Any]:
        """The cache file's shape."""
        return {
            "version": INDEX_VERSION,
            "mid": self.mid,
            "labels_etag": self.labels_etag,
            "metadata_etag": self.metadata_etag,
            "stripes": self.stripes,
            "labels_read": self.labels_read,
            "positives": self.positives,
            "resolved": self.resolved,
            "metadata_read": self.metadata_read,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ClassIndex:
        """Rebuild from the cache file.

        Raises:
            ValueError: On any shape problem, including an unknown version.
        """
        if data.get("version") != INDEX_VERSION:
            raise ValueError("unrecognized index version")
        index = cls(
            mid=str(data["mid"]),
            labels_etag=str(data["labels_etag"]),
            metadata_etag=str(data["metadata_etag"]),
            stripes=[[int(a), int(b)] for a, b in data["stripes"]],
            labels_read=int(data["labels_read"]),
            positives={str(k): int(v) for k, v in data["positives"].items()},
            resolved={str(k): [str(u) for u in v] for k, v in data["resolved"].items()},
            metadata_read=int(data["metadata_read"]),
        )
        if any(len(urls) != 2 for urls in index.resolved.values()):
            raise ValueError("resolved entries must hold two URLs")
        return index

    def exhausted(self, bounds: Sequence[tuple[int, int]]) -> bool:
        """Whether every stripe of the label file has been read to its end."""
        return all(
            aligned and position >= end
            for (position, aligned), (_, end) in zip(self.stripes, bounds, strict=True)
        )

    def pending(self, metadata_size: int) -> list[str]:
        """Candidates not yet resolved and not yet ruled out by a full pass."""
        return [
            image_id
            for image_id, found_at in self.positives.items()
            if image_id not in self.resolved
            and self.metadata_read < found_at + metadata_size
        ]


def _stripe_bounds(size: int, stripes: int) -> list[tuple[int, int]]:
    edges = [size * i // stripes for i in range(stripes + 1)]
    return [(edges[i], edges[i + 1]) for i in range(stripes)]


def _parse_label_line(line: bytes) -> tuple[str, str] | None:
    """``(ImageID, MID)`` for a ``Confidence == 1`` label row, else None."""
    parts = line.rstrip(b"\r").split(b",")
    if len(parts) != 4 or parts[3] not in (b"1", b"1.0") or not _HEX_ID.match(line):
        return None
    return parts[0].decode("ascii"), parts[2].decode("ascii", "replace")


def _parse_metadata_line(line: bytes) -> tuple[str, str] | None:
    """``(Thumbnail300KURL, OriginalURL)`` from one metadata row, or None."""
    try:
        row = next(csv.reader([line.rstrip(b"\r").decode("utf-8")]))
    except (UnicodeDecodeError, csv.Error, StopIteration):
        return None
    # ImageID,Subset,OriginalURL,OriginalLandingURL,License,AuthorProfileURL,
    # Author,Title,OriginalSize,OriginalMD5,Thumbnail300KURL,Rotation
    if len(row) != 12:
        return None
    return row[10].strip(), row[2].strip()


class OpenImagesIndex:
    """Find candidate image URLs for Open Images classes.

    Args:
        client: The HTTP client. Tests pass one over ``httpx.MockTransport``.
        home: The home directory holding ``.optica/``.
        report: Receives short progress lines, in the user's vocabulary.
        chunk_bytes: Bytes per label range read. Tests shrink it.
        stripes: Stripes over the label file. Tests shrink it.
    """

    def __init__(
        self,
        client: httpx.Client,
        home: Path | None = None,
        report: ProgressCallback | None = None,
        *,
        chunk_bytes: int = CHUNK_BYTES,
        stripes: int = STRIPES,
    ) -> None:
        self.client = client
        self.home = home
        self.report = report or (lambda _message: None)
        self.chunk_bytes = chunk_bytes
        self.stripe_count = stripes
        self._facts: dict[str, tuple[int, str]] = {}
        self._label_map: LabelMap | None = None

    @property
    def label_map(self) -> LabelMap:
        """The verified class list, loaded on first use."""
        if self._label_map is None:
            self._label_map = load_label_map(self.client, self.home, self.report)
        return self._label_map

    def _probe(self, url: str, what: str) -> tuple[int, str]:
        """``(size, etag)`` of a remote file, from a one-byte range request."""
        if url not in self._facts:
            response = _get(self.client, url, what, headers={"Range": "bytes=0-0"})
            try:
                size = int(response.headers.get("content-range", "").rsplit("/", 1)[1])
            except (IndexError, ValueError) as exc:
                raise OpticaFetchError(
                    f"Open Images did not answer a byte-range request for {what}.",
                    why="Optica reads these multi-gigabyte files in ranges, never whole.",
                    fix="Run the same command again later, or use --source flickr.",
                ) from exc
            self._facts[url] = (size, response.headers.get("etag", ""))
        return self._facts[url]

    @property
    def _labels_size(self) -> int:
        return self._probe(LABELS_URL, "the image labels")[0]

    @property
    def _metadata_size(self) -> int:
        return self._probe(METADATA_URL, "the image metadata")[0]

    # -- cache ---------------------------------------------------------------

    def _cache_path(self, mid: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", mid.strip("/"))
        return cache_dir(self.home) / "classes" / f"{safe}.json"

    def load_class(self, mid: str) -> ClassIndex:
        """The cached state for ``mid`` — fresh if absent, stale, or corrupt.

        A corrupt or stale cache is replaced silently: all it held was search
        progress, and a cache Optica populated is Optica's to repair.
        """
        _, labels_etag = self._probe(LABELS_URL, "the image labels")
        _, metadata_etag = self._probe(METADATA_URL, "the image metadata")
        bounds = _stripe_bounds(self._labels_size, self.stripe_count)
        path = self._cache_path(mid)
        state: ClassIndex | None
        try:
            state = ClassIndex.from_json(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            state = None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            path.unlink(missing_ok=True)
            state = None
        if (
            state is None
            or state.mid != mid
            or state.labels_etag != labels_etag
            or state.metadata_etag != metadata_etag
            or len(state.stripes) != len(bounds)
        ):
            state = ClassIndex(
                mid=mid,
                labels_etag=labels_etag,
                metadata_etag=metadata_etag,
                stripes=[
                    [max(0, start - 1), 1 if start == 0 else 0] for start, _ in bounds
                ],
            )
        return state

    def save_class(self, state: ClassIndex) -> None:
        """Persist ``state`` atomically."""
        atomic_write_json(self._cache_path(state.mid), state.to_json())

    # -- phase A: candidates from the label file -------------------------------

    def _read_round(
        self, group: Sequence[ClassIndex], bounds: list[tuple[int, int]]
    ) -> None:
        """Read one chunk from every unfinished stripe, for a group sharing cursors."""
        by_mid = {state.mid: state for state in group}
        stripes = [list(stripe) for stripe in group[0].stripes]
        read = 0
        for number, (_, end) in enumerate(bounds):
            position, aligned = stripes[number]
            if aligned and position >= end:
                continue
            requested = self.chunk_bytes
            response = _get(
                self.client,
                LABELS_URL,
                "the image labels",
                headers={"Range": f"bytes={position}-{position + requested - 1}"},
            )
            if response.status_code != 206:
                raise OpticaFetchError(
                    "Open Images ignored a byte-range request for the image labels.",
                    why="Optica reads the 2.6 GB label file in ranges, never whole.",
                    fix="Run the same command again later, or use --source flickr.",
                )
            body = response.content
            read += len(body)
            at_eof = len(body) < requested
            base = position
            if not aligned:
                newline = body.find(b"\n")
                if newline < 0:
                    stripes[number] = [end, 1] if at_eof else [position + len(body), 0]
                    continue
                base = position + newline + 1
                body = body[newline + 1 :]
            last = body.rfind(b"\n")
            if last < 0 and not at_eof and base < end:
                raise OpticaFetchError(
                    "An Open Images label row was longer than a read chunk.",
                    why="The label file is not in the format Optica expects.",
                    fix="Use --source flickr, and report this as a bug.",
                )
            complete = body if at_eof else body[: last + 1]
            line_start = base
            finished = at_eof
            for line in complete.split(b"\n"):
                if line_start >= end:
                    finished = True
                    break
                line_start += len(line) + 1
                parsed = _parse_label_line(line)
                if parsed is not None and parsed[1] in by_mid:
                    state = by_mid[parsed[1]]
                    state.positives.setdefault(parsed[0], state.metadata_read)
            stripes[number] = [end, 1] if finished else [base + last + 1, 1]
        for state in group:
            state.stripes = [list(stripe) for stripe in stripes]
            state.labels_read += read

    def _positive_goal(self, state: ClassIndex, needed: int) -> int:
        """How many candidates to gather before searching metadata for URLs.

        ``s = min(P, max(4n, sqrt(n*P*M/L)))`` for ``n`` URLs needed, estimated
        positives ``P``, and file sizes ``M`` and ``L``: more candidates make the
        metadata join shorter, and total bytes are least where the two reads
        balance. Before any label has been read ``P`` is unknown and the floor
        stands in.
        """
        floor = max(1, needed * POSITIVE_FLOOR_FACTOR)
        if state.labels_read == 0:
            return floor
        fraction = min(1.0, state.labels_read / self._labels_size)
        estimate = len(state.positives) / fraction
        balanced = math.ceil(
            math.sqrt(needed * estimate * self._metadata_size / self._labels_size)
        )
        ceiling = max(math.ceil(estimate), len(state.positives) + 1)
        return min(max(floor, balanced), ceiling)

    # -- phase B: URLs from the metadata file ----------------------------------

    def _join(self, group: Sequence[ClassIndex], needed: dict[str, int]) -> None:
        """Stream metadata until each state has its URLs or its candidates are out."""
        size = self._metadata_size
        lead = group[0]
        owner: dict[str, list[ClassIndex]] = {}
        rule_out_at: dict[str, int] = {}
        for state in group:
            pending = state.pending(size)
            for image_id in pending:
                owner.setdefault(image_id, []).append(state)
            if pending:
                rule_out_at[state.mid] = max(state.positives[i] for i in pending) + size

        def done() -> bool:
            # O(classes), not O(candidates): this runs once per streamed chunk.
            return all(
                len(state.resolved) >= needed[state.mid]
                or state.metadata_read >= rule_out_at.get(state.mid, 0)
                for state in group
            )

        started = lead.metadata_read
        last_report = started
        while owner and not done():
            cycle_start = lead.metadata_read - lead.metadata_read % size
            cursor = lead.metadata_read - cycle_start
            position = lead.metadata_read
            try:
                with self.client.stream(
                    "GET", METADATA_URL, headers={"Range": f"bytes={cursor}-"}
                ) as response:
                    if response.status_code != 206 and not (
                        cursor == 0 and response.status_code == 200
                    ):
                        raise OpticaFetchError(
                            f"Open Images returned HTTP {response.status_code} for the "
                            "image metadata.",
                            fix="Run the same command again later, or use "
                            "--source flickr.",
                        )
                    carry = b""
                    stopped = False
                    for chunk in response.iter_bytes(1 << 16):
                        lines = (carry + chunk).split(b"\n")
                        carry = lines.pop()
                        for line in lines:
                            position += len(line) + 1
                            self._match(line, owner)
                        for state in group:
                            state.metadata_read = position
                        if done():
                            stopped = True
                            break
                        if position - last_report >= 64 << 20:
                            last_report = position
                            self.report(
                                "Matching image URLs — "
                                f"{(position - started) / (1 << 20):,.0f} MiB of "
                                "metadata read"
                            )
                    if not stopped:
                        self._match(carry, owner)
                        for state in group:
                            state.metadata_read = cycle_start + size
            except httpx.TransportError as exc:
                raise _network_error("the image metadata", exc) from exc

    @staticmethod
    def _match(line: bytes, owner: dict[str, list[ClassIndex]]) -> None:
        if not _HEX_ID.match(line):
            return
        image_id = line[:_ID_LENGTH].decode("ascii")
        holders = owner.pop(image_id, None)
        if not holders:
            return
        urls = _parse_metadata_line(line)
        if urls is None or not any(urls):
            return
        for state in holders:
            state.resolved[image_id] = list(urls)

    # -- the public operations -------------------------------------------------

    def ensure(
        self, mids: Sequence[str], needed: dict[str, int]
    ) -> dict[str, ClassIndex]:
        """Extend each class's search until it has ``needed`` URLs or is exhausted.

        Classes whose cursors agree — every class searched for the first time,
        above all — share one read of each file, so a fetch costs roughly its
        rarest class rather than the sum of its classes.

        Returns:
            The updated state for every MID, already saved.
        """
        states = {mid: self.load_class(mid) for mid in mids}
        bounds = _stripe_bounds(self._labels_size, self.stripe_count)
        size = self._metadata_size

        groups: dict[tuple[Any, ...], list[ClassIndex]] = {}
        for state in states.values():
            key = (tuple(map(tuple, state.stripes)), state.metadata_read)
            groups.setdefault(key, []).append(state)

        for group in groups.values():
            names = ", ".join(self._display(state.mid) for state in group)
            while True:
                short = [s for s in group if len(s.resolved) < needed[s.mid]]
                if not short:
                    break
                # Phase A: gather enough candidates to make the join cheap.
                while not group[0].exhausted(bounds) and any(
                    len(s.resolved) + len(s.pending(size))
                    < self._positive_goal(s, needed[s.mid])
                    for s in short
                ):
                    self._read_round(group, bounds)
                    self.report(
                        f"Searching Open Images for {names} — "
                        f"{group[0].labels_read / (1 << 20):,.0f} MiB of labels read"
                    )
                    for state in group:
                        self.save_class(state)
                # Phase B: resolve URLs for the candidates found.
                self._join(group, needed)
                for state in group:
                    self.save_class(state)
                short = [s for s in group if len(s.resolved) < needed[s.mid]]
                if not short or group[0].exhausted(bounds):
                    break
                # Every candidate was resolved or ruled out and more are needed:
                # read on, so the next pass has new candidates to join.
                self._read_round(group, bounds)
        return states

    def _display(self, mid: str) -> str:
        if self._label_map is not None:
            for found_mid, display in self._label_map.by_name.values():
                if found_mid == mid:
                    return display
        return mid

    def candidates(self, mid: str, batch: int) -> Iterator[ResolvedImage]:
        """Yield resolved images for ``mid``, extending the search on demand.

        The consumer pulls until it has enough valid images. Each time the
        resolved list runs out the search is extended by ``batch`` more URLs, and
        the iterator ends only when the class's candidate pool is exhausted —
        every stripe read and every candidate's URL looked for.
        """
        yielded = 0
        state = self.ensure([mid], {mid: batch})[mid]
        while True:
            items = list(state.resolved.items())
            for image_id, (thumbnail, original) in items[yielded:]:
                yield ResolvedImage(image_id, thumbnail, original)
            yielded = len(items)
            state = self.ensure([mid], {mid: yielded + batch})[mid]
            if len(state.resolved) <= yielded:
                return
