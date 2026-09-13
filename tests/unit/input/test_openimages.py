"""Open Images class list and candidate index, against a fake GCS.

Covers plan § "Input & Acquisition" → *Fetch sources* (Open Datasets: label map
cached and verified on every load, deleted and re-downloaded if corrupt; the
per-row ``Thumbnail300KURL`` → ``OriginalURL`` fallback where the value is
empty; fill to target from a pool that can be exhausted) and Implementation
Notes 5 and 13. The acquisition strategy itself is logged in
``notes/build-log.md`` § "Open Images image-URL acquisition strategy".

No test here touches the network: every request goes to an in-memory server
that honours ``Range`` the way GCS was measured to (``notes/verified.md``).
"""

from __future__ import annotations

import base64
import hashlib
import random
from dataclasses import dataclass, field

import httpx
import pytest

from optica.exceptions import OpticaFetchError, OpticaValidationError
from optica.input import openimages as oi

CAT = "/m/01yrx"
DOG = "/m/0bt9lr"
RARE = "/m/0rare1"

LABEL_MAP = (
    "LabelName,DisplayName\r\n"
    f"{CAT},Cat\r\n"
    f"{DOG},Dog\r\n"
    "/m/01t032,Golden retriever\r\n"
    f"{RARE},Screwdriver\r\n"
    '/m/0comma,"Paper, glue"\r\n'
).encode()


def _md5(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data).digest()).decode()


@dataclass
class FakeGCS:
    """Serves the three Open Images files, honouring Range like GCS does."""

    files: dict[str, bytes]
    etags: dict[str, str] = field(default_factory=dict)
    requests: list[tuple[str, str | None]] = field(default_factory=list)
    ignore_range: bool = False
    corrupt_label_map: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        header = request.headers.get("range")
        self.requests.append((url, header))
        data = self.files.get(url)
        if data is None:
            return httpx.Response(404)
        headers = {
            "etag": self.etags.get(url, '"v1"'),
            "x-goog-hash": f"crc32c=AAAA==,md5={_md5(data)}",
            "accept-ranges": "bytes",
        }
        body = data
        if url == oi.LABEL_MAP_URL and self.corrupt_label_map:
            body = data[:-3]
        if header and not self.ignore_range:
            spec = header.removeprefix("bytes=")
            first_s, _, last_s = spec.partition("-")
            first = int(first_s)
            last = int(last_s) if last_s else len(data) - 1
            last = min(last, len(data) - 1)
            body = data[first : last + 1]
            headers["content-range"] = f"bytes {first}-{last}/{len(data)}"
            return httpx.Response(206, headers=headers, content=body)
        return httpx.Response(200, headers=headers, content=body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def count(self, url: str) -> int:
        return sum(1 for requested, _ in self.requests if requested == url)


def _dataset(seed: int = 3, images: int = 400, rare: int = 3):
    """Synthetic label and metadata files with a known truth.

    Labels are sorted by ImageID, as the real file is; metadata is shuffled, as
    the real file is. Some thumbnails are empty, as 2.47% of real rows are.
    """
    rng = random.Random(seed)
    ids = sorted({f"{rng.getrandbits(64):016x}" for _ in range(images)})
    truth: dict[str, set[str]] = {CAT: set(), DOG: set(), RARE: set()}
    label_lines = ["ImageID,Source,LabelName,Confidence"]
    rare_ids = set(rng.sample(ids, rare))
    for image_id in ids:
        for mid in (CAT, DOG):
            confidence = rng.choice(["1.0", "0.0", "1.0"])
            label_lines.append(f"{image_id},verification,{mid},{confidence}")
            if confidence == "1.0":
                truth[mid].add(image_id)
        label_lines.append(f"{image_id},verification,/m/0other,1.0")
        if image_id in rare_ids:
            label_lines.append(f"{image_id},crowdsource-verification,{RARE},1")
            truth[RARE].add(image_id)
    labels = ("\n".join(label_lines) + "\n").encode()

    header = (
        "ImageID,Subset,OriginalURL,OriginalLandingURL,License,AuthorProfileURL,"
        "Author,Title,OriginalSize,OriginalMD5,Thumbnail300KURL,Rotation"
    )
    rows = []
    empty_thumbs: set[str] = set()
    for image_id in ids:
        original = f"https://farm1.staticflickr.com/1/{image_id}_o.jpg"
        thumb = f"https://c1.staticflickr.com/1/{image_id}_z.jpg"
        if rng.random() < 0.1:
            thumb = ""
            empty_thumbs.add(image_id)
        title = '"A title, with a comma"'
        rows.append(
            f"{image_id},train,{original},https://www.flickr.com/photos/x/1,"
            f"https://creativecommons.org/licenses/by/2.0/,https://www.flickr.com/people/x/,"
            f"Someone,{title},1000,abc==,{thumb},0.0"
        )
    rng.shuffle(rows)
    metadata = ("\n".join([header, *rows]) + "\n").encode()
    return labels, metadata, truth, empty_thumbs


@pytest.fixture
def world():
    labels, metadata, truth, empty = _dataset()
    gcs = FakeGCS(
        files={
            oi.LABEL_MAP_URL: LABEL_MAP,
            oi.LABELS_URL: labels,
            oi.METADATA_URL: metadata,
        }
    )
    return gcs, truth, empty


def _index(gcs: FakeGCS, home, **kwargs) -> oi.OpenImagesIndex:
    kwargs.setdefault("chunk_bytes", 512)
    kwargs.setdefault("stripes", 7)
    return oi.OpenImagesIndex(gcs.client(), home, **kwargs)


class TestGcsMd5:
    def test_comma_joined_header(self):
        headers = httpx.Headers(
            {"x-goog-hash": "crc32c=GjifFg==,md5=Kqy5GbIHxQ8qCEgipcJzbA=="}
        )
        assert oi.gcs_md5(headers) == "Kqy5GbIHxQ8qCEgipcJzbA=="

    def test_repeated_headers(self):
        headers = httpx.Headers(
            [("x-goog-hash", "crc32c=GjifFg=="), ("x-goog-hash", "md5=abc=")]
        )
        assert oi.gcs_md5(headers) == "abc="

    def test_absent(self):
        assert oi.gcs_md5(httpx.Headers({})) is None


class TestUrls:
    def test_the_verified_file_locations(self):
        # notes/verified.md § "Open Images — which files map a class to image URLs".
        base = "https://storage.googleapis.com/openimages"
        assert f"{base}/v7/oidv7-class-descriptions.csv" == oi.LABEL_MAP_URL
        assert f"{base}/v7/oidv7-train-annotations-human-imagelabels.csv" == oi.LABELS_URL
        assert (
            f"{base}/v6/oidv6-train-images-with-labels-with-rotation.csv"
            == oi.METADATA_URL
        )


class TestLabelMap:
    def test_first_use_downloads_and_announces(self, world, tmp_path):
        gcs, _, _ = world
        said: list[str] = []
        label_map = oi.load_label_map(gcs.client(), tmp_path, said.append)
        assert label_map.lookup("cat") == (CAT, "Cat")
        assert "first use only" in said[0]
        assert (oi.cache_dir(tmp_path) / "oidv7-class-descriptions.csv").exists()

    def test_verified_on_every_load_without_downloading_again(self, world, tmp_path):
        gcs, _, _ = world
        oi.load_label_map(gcs.client(), tmp_path)
        oi.load_label_map(gcs.client(), tmp_path)
        assert gcs.count(oi.LABEL_MAP_URL) == 1

    def test_a_corrupt_cache_is_deleted_and_downloaded_again(self, world, tmp_path):
        gcs, _, _ = world
        oi.load_label_map(gcs.client(), tmp_path)
        path = oi.cache_dir(tmp_path) / "oidv7-class-descriptions.csv"
        path.write_bytes(path.read_bytes()[:-5])
        said: list[str] = []
        label_map = oi.load_label_map(gcs.client(), tmp_path, said.append)
        assert gcs.count(oi.LABEL_MAP_URL) == 2
        assert "corrupt" in said[0]
        assert str(path) in said[0]
        assert label_map.lookup("Dog") == (DOG, "Dog")

    def test_a_download_that_does_not_match_gcs_md5_is_refused(self, world, tmp_path):
        gcs, _, _ = world
        gcs.corrupt_label_map = True
        with pytest.raises(OpticaFetchError, match="arrived corrupt"):
            oi.load_label_map(gcs.client(), tmp_path)
        assert not (oi.cache_dir(tmp_path) / "oidv7-class-descriptions.csv").exists()

    def test_lookup_is_case_insensitive_and_reads_underscores_as_spaces(self, tmp_path):
        label_map = oi.LabelMap.parse(LABEL_MAP, tmp_path)
        assert label_map.lookup("GOLDEN_RETRIEVER") == ("/m/01t032", "Golden retriever")
        assert label_map.lookup("golden retriever") == ("/m/01t032", "Golden retriever")
        assert label_map.lookup("Paper, glue") == ("/m/0comma", "Paper, glue")

    def test_unknown_names_are_all_reported_with_suggestions(self, tmp_path):
        label_map = oi.LabelMap.parse(LABEL_MAP, tmp_path)
        with pytest.raises(OpticaValidationError) as info:
            label_map.require(["cat", "dgo", "unicorn"])
        assert "dgo (did you mean Dog?)" in info.value.message
        assert "unicorn" in info.value.message
        # Known names are not reported.
        assert info.value.message.startswith("Open Images has no class named: dgo")

    def test_network_failure_is_a_fetch_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("optica.input.openimages.time.sleep", lambda _s: None)

        def refuse(request):
            raise httpx.ConnectError("offline", request=request)

        client = httpx.Client(transport=httpx.MockTransport(refuse))
        with pytest.raises(OpticaFetchError, match="Could not download"):
            oi.load_label_map(client, tmp_path)


class TestStripes:
    @pytest.mark.parametrize(
        ("chunk", "stripes"), [(97, 1), (256, 5), (512, 7), (4096, 13)]
    )
    def test_every_positive_is_found_exactly_once_across_stripe_edges(
        self, world, tmp_path, chunk, stripes
    ):
        gcs, truth, _ = world
        index = _index(gcs, tmp_path, chunk_bytes=chunk, stripes=stripes)
        states = index.ensure([CAT, DOG, RARE], {CAT: 10**6, DOG: 10**6, RARE: 10**6})
        for mid in (CAT, DOG, RARE):
            assert set(states[mid].positives) == truth[mid]
        # Exhaustion: every stripe read to its end, every URL resolved.
        bounds = oi._stripe_bounds(len(gcs.files[oi.LABELS_URL]), stripes)
        assert states[CAT].exhausted(bounds)
        assert set(states[CAT].resolved) == truth[CAT]

    def test_only_confidence_one_rows_become_candidates(self, world, tmp_path):
        gcs, truth, _ = world
        index = _index(gcs, tmp_path)
        states = index.ensure([CAT], {CAT: 10**6})
        labels = gcs.files[oi.LABELS_URL].decode()
        negatives = {
            line.split(",")[0] for line in labels.splitlines() if f",{CAT},0.0" in line
        }
        assert not (set(states[CAT].positives) & (negatives - truth[CAT]))

    def test_a_server_that_ignores_range_is_refused(self, world, tmp_path):
        gcs, _, _ = world
        index = _index(gcs, tmp_path)
        index._probe(oi.LABELS_URL, "labels")
        index._probe(oi.METADATA_URL, "metadata")
        gcs.ignore_range = True
        with pytest.raises(OpticaFetchError, match="ignored a byte-range request"):
            index.ensure([CAT], {CAT: 5})


class TestJoinAndFallback:
    def test_thumbnail_preferred_original_where_the_value_is_empty(self, world, tmp_path):
        gcs, truth, empty = world
        index = _index(gcs, tmp_path)
        images = list(index.candidates(CAT, batch=1000))
        assert {image.image_id for image in images} == truth[CAT]
        for image in images:
            if image.image_id in empty:
                assert image.thumbnail_url == ""
                assert image.url == image.original_url
            else:
                assert image.url == image.thumbnail_url
        assert any(image.image_id in empty for image in images)

    def test_the_join_stops_once_enough_urls_are_resolved(self, world, tmp_path):
        gcs, _, _ = world
        streamed: list[int] = []
        original = gcs.handler

        def counting(request):
            response = original(request)
            if (
                str(request.url) == oi.METADATA_URL
                and request.headers.get("range", "") != "bytes=0-0"
            ):
                streamed.append(len(response.content))
            return response

        client = httpx.Client(transport=httpx.MockTransport(counting))
        index = oi.OpenImagesIndex(client, tmp_path, chunk_bytes=512, stripes=7)
        state = index.ensure([CAT], {CAT: 3})[CAT]
        assert len(state.resolved) >= 3
        assert state.metadata_read < len(gcs.files[oi.METADATA_URL])


class TestCache:
    def test_a_later_search_continues_rather_than_restarting(self, world, tmp_path):
        gcs, _, _ = world
        first = _index(gcs, tmp_path)
        state = first.ensure([CAT], {CAT: 5})[CAT]
        found = dict(state.resolved)
        labels_read = state.labels_read
        second = _index(gcs, tmp_path)
        again = second.load_class(CAT)
        assert again.resolved == found
        assert again.labels_read == labels_read
        more = second.ensure([CAT], {CAT: len(found) + 10})[CAT]
        assert set(found) <= set(more.resolved)
        assert len(more.resolved) >= len(found) + 10 or more.exhausted(
            oi._stripe_bounds(len(gcs.files[oi.LABELS_URL]), 7)
        )

    def test_an_etag_change_discards_the_cache(self, world, tmp_path):
        gcs, _, _ = world
        _index(gcs, tmp_path).ensure([CAT], {CAT: 5})
        gcs.etags[oi.LABELS_URL] = '"v2"'
        fresh = _index(gcs, tmp_path).load_class(CAT)
        assert fresh.resolved == {}
        assert fresh.labels_read == 0

    def test_a_corrupt_cache_file_is_replaced_silently(self, world, tmp_path):
        gcs, _, _ = world
        index = _index(gcs, tmp_path)
        index.ensure([CAT], {CAT: 2})
        path = index._cache_path(CAT)
        path.write_text("{broken", encoding="utf-8")
        assert index.load_class(CAT).resolved == {}

    def test_classes_searched_together_share_one_read(self, world, tmp_path):
        gcs, _, _ = world
        together = _index(gcs, tmp_path / "a")
        together.ensure([CAT, DOG], {CAT: 20, DOG: 20})
        shared = gcs.count(oi.LABELS_URL)
        gcs.requests.clear()
        apart = _index(gcs, tmp_path / "b")
        apart.ensure([CAT], {CAT: 20})
        apart.ensure([DOG], {DOG: 20})
        separate = gcs.count(oi.LABELS_URL)
        assert shared < separate


class TestCandidatesPool:
    def test_a_rare_class_exhausts_its_pool_and_the_iterator_ends(self, world, tmp_path):
        gcs, truth, _ = world
        index = _index(gcs, tmp_path)
        images = list(index.candidates(RARE, batch=10))
        assert {image.image_id for image in images} == truth[RARE]
        assert len(images) == 3

    def test_candidates_are_yielded_once_each(self, world, tmp_path):
        gcs, _, _ = world
        index = _index(gcs, tmp_path)
        ids = [image.image_id for image in index.candidates(DOG, batch=7)]
        assert len(ids) == len(set(ids))
