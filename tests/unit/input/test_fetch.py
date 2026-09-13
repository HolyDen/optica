"""The Fetch Adapter.

Covers plan § "Input & Acquisition" → *Input Manager* (registry dispatch on
``--source``, rate-limit aware), *Fetch sources* (Flickr ``flickr.photos.search``
with ``FLICKR_API_KEY``; dead URLs expected, fill to target, exhausted pool as a
completed fetch), *Class imbalance and image validation* (fetched images named
by zero-padded sequence index, extension from the validated format, numbering
continuing from the highest index), and § "Labeling & Curation" → *Staging
shapes* (``.partial`` until complete) and *Deletion, staging, and interruption*.

The Flickr tests pin the adapter to ``notes/verified.md`` § "Flickr API" —
including that a failed call returns HTTP 200 — because no real key exists to
exercise it against.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from PIL import Image

from optica.exceptions import OpticaFetchError, OpticaValidationError
from optica.input import fetch as f
from optica.input.classes import ResolvedClass


def _image(color: str, fmt: str = "JPEG", size=(200, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt)
    return buffer.getvalue()


COLORS = [
    "red",
    "green",
    "blue",
    "yellow",
    "purple",
    "orange",
    "pink",
    "gray",
    "navy",
    "teal",
]


class TestRegistry:
    def test_both_v1_sources_are_registered(self):
        assert set(f.SOURCES) == {"flickr", "open-datasets"}

    def test_unknown_source_lists_the_valid_ones_and_the_default(self):
        with pytest.raises(OpticaValidationError) as info:
            f.create_source("bing", f.SourceContext(client=httpx.Client()))
        assert info.value.options == ["flickr", "open-datasets"]
        assert info.value.default == "open-datasets"

    def test_registration_is_a_single_point(self, monkeypatch):
        monkeypatch.setattr(f, "SOURCES", dict(f.SOURCES))

        def example(context: f.SourceContext) -> f.FetchSource:
            return StubSource({})

        assert f.register_source("example")(example) is example
        assert f.SOURCES["example"] is example


# ------------------------------------------------------------------- Flickr


@dataclass
class FakeFlickr:
    responses: list[httpx.Response]
    seen: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return self.responses.pop(0)

    def source(self, key: str | None = "k3y", sleeps: list[float] | None = None):
        client = httpx.Client(transport=httpx.MockTransport(self.handler))
        recorder = sleeps if sleeps is not None else []
        context = f.SourceContext(client=client, api_key=key, sleep=recorder.append)
        return f.FlickrSource(context)


def _page(photos: list[dict[str, str]], page: int = 1, pages: int = 1) -> httpx.Response:
    body = {
        "photos": {"page": page, "pages": pages, "perpage": 100, "photo": photos},
        "stat": "ok",
    }
    return httpx.Response(200, json=body)


class TestFlickrSource:
    def test_no_key_fails_at_entry_and_names_the_keyless_route(self):
        source = FakeFlickr([]).source(key=None)
        with pytest.raises(OpticaFetchError) as info:
            source.prepare(["cat"])
        assert "Pro" in (info.value.why or "")
        joined = " ".join(info.value.fix)
        assert "optica config --set flickr_api_key" in joined
        assert "--source open-datasets" in joined

    def test_request_parameters_match_the_verified_api(self):
        fake = FakeFlickr(
            [_page([{"id": "1", "url_z": "https://live.staticflickr.com/1/1_z.jpg"}])]
        )
        list(fake.source().candidates("golden_retriever", batch=900))
        request = fake.seen[0]
        assert str(request.url).startswith("https://www.flickr.com/services/rest/")
        params = request.url.params
        assert params["method"] == "flickr.photos.search"
        assert params["api_key"] == "k3y"
        assert params["text"] == "golden retriever"
        assert params["per_page"] == "500"  # the documented maximum
        assert params["format"] == "json"
        assert params["nojsoncallback"] == "1"
        assert params["extras"] == "url_z,url_c,url_m"
        assert params["content_types"] == "0"

    def test_url_preference_is_z_then_c_then_m(self):
        photos = [
            {"id": "1", "url_c": "c1", "url_z": "z1", "url_m": "m1"},
            {"id": "2", "url_c": "c2", "url_m": "m2"},
            {"id": "3", "url_m": "m3"},
            {"id": "4"},
        ]
        fake = FakeFlickr([_page(photos)])
        got = [(c.key, c.url) for c in fake.source().candidates("cat", batch=10)]
        assert got == [("1", "z1"), ("2", "c2"), ("3", "m3")]

    def test_a_failure_with_http_200_is_still_a_failure(self):
        # Verified 2026-09-13: stat=fail arrives with HTTP 200.
        body = {
            "stat": "fail",
            "code": 100,
            "message": "Invalid API Key (Key has invalid format)",
        }
        fake = FakeFlickr([httpx.Response(200, json=body)])
        with pytest.raises(OpticaFetchError, match="rejected the API key"):
            list(fake.source().candidates("cat", batch=10))

    def test_temporarily_unavailable_is_retried(self):
        unavailable = {
            "stat": "fail",
            "code": 105,
            "message": "Service currently unavailable",
        }
        fake = FakeFlickr(
            [httpx.Response(200, json=unavailable), _page([{"id": "9", "url_z": "z"}])]
        )
        sleeps: list[float] = []
        got = list(fake.source(sleeps=sleeps).candidates("cat", batch=10))
        assert [c.key for c in got] == ["9"]
        assert any(s >= 10 for s in sleeps)

    def test_other_errors_are_fetch_errors(self):
        body = {
            "stat": "fail",
            "code": 3,
            "message": "Parameterless searches have been disabled",
        }
        fake = FakeFlickr([httpx.Response(200, json=body)])
        with pytest.raises(OpticaFetchError, match="error 3"):
            list(fake.source().candidates("cat", batch=10))

    def test_429_pauses_for_retry_after_then_resumes(self):
        fake = FakeFlickr(
            [
                httpx.Response(429, headers={"retry-after": "42"}),
                _page([{"id": "1", "url_z": "z"}]),
            ]
        )
        sleeps: list[float] = []
        messages: list[str] = []
        source = fake.source(sleeps=sleeps)
        source.report = messages.append
        assert [c.key for c in source.candidates("cat", batch=1)] == ["1"]
        assert 42.0 in sleeps
        assert "rate limit" in messages[0]

    def test_pages_until_the_last_page(self):
        fake = FakeFlickr(
            [
                _page([{"id": "1", "url_z": "a"}], page=1, pages=2),
                _page([{"id": "2", "url_z": "b"}], page=2, pages=2),
            ]
        )
        assert [c.key for c in fake.source().candidates("cat", batch=1)] == ["1", "2"]
        assert [r.url.params["page"] for r in fake.seen] == ["1", "2"]

    def test_never_pages_past_the_4000_result_ceiling(self):
        pages = [
            _page([{"id": str(i), "url_z": "u"}], page=i + 1, pages=999)
            for i in range(20)
        ]
        fake = FakeFlickr(pages)
        list(fake.source().candidates("cat", batch=500))
        assert len(fake.seen) == 8  # 8 x 500 = 4,000
        assert f.FLICKR_MAX_RESULTS == 4000

    def test_calls_are_spaced_for_3600_per_hour(self):
        assert f.FLICKR_MIN_INTERVAL == 1.0


# --------------------------------------------------------------- downloader


def _downloader(
    handler: Callable[[httpx.Request], httpx.Response],
    sleeps: list[float] | None = None,
) -> f.Downloader:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return f.Downloader(client, sleep=(sleeps if sleeps is not None else []).append)


class TestDownloader:
    def test_200_returns_the_body(self):
        assert (
            _downloader(lambda r: httpx.Response(200, content=b"img")).get("https://x/a")
            == b"img"
        )

    @pytest.mark.parametrize("status", [403, 404, 410])
    def test_dead_urls_are_none_without_retrying(self, status):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(status)

        assert _downloader(handler).get("https://x/a") is None
        assert len(calls) == 1

    def test_server_errors_retry_then_succeed(self):
        responses = [httpx.Response(503), httpx.Response(200, content=b"ok")]
        sleeps: list[float] = []
        assert _downloader(lambda r: responses.pop(0), sleeps).get("https://x/a") == b"ok"
        assert sleeps

    def test_persistent_transport_errors_become_dead(self):
        def handler(request):
            raise httpx.ConnectError("down", request=request)

        assert _downloader(handler).get("https://x/a") is None


# ------------------------------------------------------------ fill to target


@dataclass
class StubSource:
    """Yields scripted candidates per query and records what was asked."""

    pools: dict[str, list[f.Candidate]]
    name: str = "stub"
    display_name: str = "Stub"
    batches: list[int] = field(default_factory=list)

    def prepare(self, queries):
        pass

    def warm(self, needed):
        pass

    def candidates(self, query: str, batch: int) -> Iterator[f.Candidate]:
        self.batches.append(batch)
        yield from self.pools.get(query, [])


class StubDownloader:
    def __init__(
        self, bodies: dict[str, bytes | None], interrupt_after: int | None = None
    ) -> None:
        self.bodies = bodies
        self.calls: list[str] = []
        self.interrupt_after = interrupt_after

    def get(self, url: str) -> bytes | None:
        if self.interrupt_after is not None and len(self.calls) >= self.interrupt_after:
            raise KeyboardInterrupt
        self.calls.append(url)
        return self.bodies.get(url)


def _pool(prefix: str, n: int) -> tuple[list[f.Candidate], dict[str, bytes | None]]:
    candidates = [
        f.Candidate(f"{prefix}{i}", f"https://cdn/{prefix}{i}.jpg") for i in range(n)
    ]
    bodies: dict[str, bytes | None] = {
        c.url: _image(COLORS[i % len(COLORS)], size=(200 + i, 200))
        for i, c in enumerate(candidates)
    }
    return candidates, bodies


def _staging(home: Path) -> Path:
    return home / ".optica" / "staging"


class TestFillToTarget:
    def test_names_are_zero_padded_sequence_indexes_with_validated_extensions(
        self, tmp_path
    ):
        candidates, bodies = _pool("c", 3)
        bodies[candidates[1].url] = _image("blue", "PNG")
        report = f.fetch_class(
            ResolvedClass("cat", ["cat"], 3),
            StubSource({"cat": candidates}),
            StubDownloader(bodies),
            tmp_path,
        )
        names = sorted(
            p.name
            for p in (_staging(tmp_path) / "cat").iterdir()
            if not p.name.startswith(".")
        )
        assert names == ["0001.jpg", "0002.png", "0003.jpg"]
        assert report.delivered == 3
        assert not report.exhausted

    def test_dead_and_unreadable_are_counted_and_the_fetch_fills_past_them(
        self, tmp_path
    ):
        candidates, bodies = _pool("c", 6)
        bodies[candidates[0].url] = None  # dead
        bodies[candidates[1].url] = b"<html>gone</html>"  # unreadable
        bodies[candidates[2].url] = bodies[candidates[3].url]  # duplicate of the next
        downloader = StubDownloader(bodies)
        report = f.fetch_class(
            ResolvedClass("cat", ["cat"], 3),
            StubSource({"cat": candidates}),
            downloader,
            tmp_path,
        )
        assert report.dead == 1
        assert report.unreadable == 1
        assert report.duplicates == 1
        assert report.delivered == 3
        assert len(downloader.calls) == 6
        # Unreadable downloads are never written.
        assert (
            len(
                [
                    p
                    for p in (_staging(tmp_path) / "cat").iterdir()
                    if not p.name.startswith(".")
                ]
            )
            == 3
        )

    def test_stops_at_target(self, tmp_path):
        candidates, bodies = _pool("c", 10)
        downloader = StubDownloader(bodies)
        f.fetch_class(
            ResolvedClass("cat", ["cat"], 4),
            StubSource({"cat": candidates}),
            downloader,
            tmp_path,
        )
        assert len(downloader.calls) == 4

    def test_candidates_are_requested_with_slack(self, tmp_path):
        candidates, bodies = _pool("c", 10)
        source = StubSource({"cat": candidates})
        f.fetch_class(
            ResolvedClass("cat", ["cat"], 4), source, StubDownloader(bodies), tmp_path
        )
        assert source.batches == [6]  # ceil(4 x 1.5)

    def test_an_exhausted_pool_is_a_completed_fetch_with_a_shortfall(self, tmp_path):
        candidates, bodies = _pool("c", 2)
        report = f.fetch_class(
            ResolvedClass("cat", ["cat"], 5),
            StubSource({"cat": candidates}),
            StubDownloader(bodies),
            tmp_path,
        )
        assert report.exhausted
        assert report.shortfall == 3
        # Complete, not partial: renamed to its final name.
        assert (_staging(tmp_path) / "cat").is_dir()
        assert not (_staging(tmp_path) / "cat.partial").exists()


class TestInterruptionAndResume:
    def test_an_interrupt_leaves_partial_with_what_was_fetched(self, tmp_path):
        candidates, bodies = _pool("c", 6)
        with pytest.raises(KeyboardInterrupt):
            f.fetch_class(
                ResolvedClass("cat", ["cat"], 6),
                StubSource({"cat": candidates}),
                StubDownloader(bodies, interrupt_after=2),
                tmp_path,
            )
        partial = _staging(tmp_path) / "cat.partial"
        assert partial.is_dir()
        assert sorted(p.name for p in partial.glob("*.jpg")) == ["0001.jpg", "0002.jpg"]
        assert not (_staging(tmp_path) / "cat").exists()

    def test_resume_continues_numbering_and_skips_tried_candidates(self, tmp_path):
        candidates, bodies = _pool("c", 6)
        with pytest.raises(KeyboardInterrupt):
            f.fetch_class(
                ResolvedClass("cat", ["cat"], 5),
                StubSource({"cat": candidates}),
                StubDownloader(bodies, interrupt_after=2),
                tmp_path,
            )
        downloader = StubDownloader(bodies)
        report = f.fetch_class(
            ResolvedClass("cat", ["cat"], 5),
            StubSource({"cat": candidates}),
            downloader,
            tmp_path,
        )
        assert report.existing == 2
        assert report.delivered == 3
        assert candidates[0].url not in downloader.calls
        assert candidates[1].url not in downloader.calls
        names = sorted(p.name for p in (_staging(tmp_path) / "cat").glob("*.jpg"))
        assert names == ["0001.jpg", "0002.jpg", "0003.jpg", "0004.jpg", "0005.jpg"]

    def test_numbering_continues_from_the_highest_index_not_the_count(self, tmp_path):
        partial = _staging(tmp_path) / "cat.partial"
        partial.mkdir(parents=True)
        (partial / "0007.jpg").write_bytes(_image("black", size=(300, 300)))
        candidates, bodies = _pool("c", 1)
        f.fetch_class(
            ResolvedClass("cat", ["cat"], 2),
            StubSource({"cat": candidates}),
            StubDownloader(bodies),
            tmp_path,
        )
        assert sorted(p.name for p in (_staging(tmp_path) / "cat").glob("*.jpg")) == [
            "0007.jpg",
            "0008.jpg",
        ]

    def test_a_complete_class_is_topped_up_not_refetched(self, tmp_path):
        candidates, bodies = _pool("c", 8)
        source = StubSource({"cat": candidates})
        f.fetch_class(
            ResolvedClass("cat", ["cat"], 3), source, StubDownloader(bodies), tmp_path
        )
        downloader = StubDownloader(bodies)
        report = f.fetch_class(
            ResolvedClass("cat", ["cat"], 5), source, downloader, tmp_path
        )
        assert report.existing == 3
        assert report.delivered == 2
        assert len(downloader.calls) == 2
        assert (_staging(tmp_path) / "cat").is_dir()

    def test_an_already_satisfied_class_downloads_nothing(self, tmp_path):
        candidates, bodies = _pool("c", 4)
        source = StubSource({"cat": candidates})
        f.fetch_class(
            ResolvedClass("cat", ["cat"], 3), source, StubDownloader(bodies), tmp_path
        )
        downloader = StubDownloader(bodies)
        f.fetch_class(ResolvedClass("cat", ["cat"], 3), source, downloader, tmp_path)
        assert downloader.calls == []


class TestGroupedClass:
    def test_sub_terms_pool_into_one_folder_with_per_query_counts(self, tmp_path):
        a, bodies_a = _pool("a", 5)
        b, bodies_b = _pool("b", 5)
        cls = ResolvedClass(
            "defective", ["cracked_screen", "dented_case"], 2, "defective", True
        )
        report = f.fetch_class(
            cls,
            StubSource({"cracked_screen": a, "dented_case": b}),
            StubDownloader({**bodies_a, **bodies_b}),
            tmp_path,
        )
        # Pools a and b reuse colours, so identical bytes across queries dedupe;
        # the fetch fills past them.
        assert report.delivered == 4
        assert report.target == 4
        assert len(list((_staging(tmp_path) / "defective").glob("0*.*"))) == 4


class TestStagedClasses:
    def test_lists_complete_and_partial_with_counts(self, tmp_path):
        root = _staging(tmp_path)
        (root / "cat").mkdir(parents=True)
        (root / "cat" / "0001.jpg").write_bytes(b"x")
        (root / "dog.partial").mkdir()
        (root / "labeling").mkdir()
        (root / "curation.json").write_text("{}", encoding="utf-8")
        found = f.staged_classes(tmp_path)
        assert [(s.name, s.partial, s.images) for s in found] == [
            ("cat", False, 1),
            ("dog", True, 0),
        ]

    def test_no_staging_is_empty(self, tmp_path):
        assert f.staged_classes(tmp_path) == []
