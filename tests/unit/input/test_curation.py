"""The Curation Adapter (the half that needs no browser).

Covers plan § "Labeling & Curation" → *Curation Server* (low-selection warning
at <30% or <10 selected; only zero selected disables Confirm), *Deletion,
staging, and interruption* (mass rejection: two independent triggers, each with
its own message) and *Staging shapes* (standalone curate reports an incomplete
fetch and proceeds; deselections restored from ``curation.json``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from optica.exceptions import OpticaCurationError, OpticaError, OpticaValidationError
from optica.input import curation as cur
from optica.input.sessions import CurationSession


def _stage(home: Path, name: str, count: int, *, partial: bool = False) -> list[Path]:
    folder = home / ".optica" / "staging" / (f"{name}.partial" if partial else name)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(1, count + 1):
        path = folder / f"{i:04d}.jpg"
        path.write_bytes(f"{name}-{i}".encode())
        paths.append(path)
    (folder / ".fetch.json").write_text("{}", encoding="utf-8")
    return paths


class TestThresholds:
    def test_values_transcribed_from_the_plan(self):
        assert cur.LOW_SELECTION_RATIO == 0.30
        assert cur.LOW_SELECTION_MINIMUM == 10

    def test_both_triggers_fire_independently_with_their_own_messages(self):
        warnings = cur.selection_warnings({"cat": 50}, {"cat": 5})
        assert {w.trigger for w in warnings} == {
            cur.RejectionTrigger.PERCENTAGE,
            cur.RejectionTrigger.MINIMUM,
        }
        assert len({w.message for w in warnings}) == 2

    def test_percentage_only(self):
        warnings = cur.selection_warnings({"cat": 100}, {"cat": 20})
        assert [w.trigger for w in warnings] == [cur.RejectionTrigger.PERCENTAGE]
        assert "20%" in warnings[0].message

    def test_minimum_only(self):
        warnings = cur.selection_warnings({"cat": 12}, {"cat": 9})
        assert [w.trigger for w in warnings] == [cur.RejectionTrigger.MINIMUM]

    def test_exactly_thirty_percent_and_exactly_ten_do_not_warn(self):
        assert cur.selection_warnings({"cat": 100}, {"cat": 30}) == []
        assert cur.selection_warnings({"cat": 10}, {"cat": 10}) == []

    def test_only_zero_selected_blocks_confirm(self):
        assert cur.confirm_blocked_classes({"cat": 0, "dog": 1}) == ["cat"]


class TestView:
    def test_complete_and_partial_classes_are_read_and_the_partial_reported(
        self, tmp_path
    ):
        _stage(tmp_path, "cat", 3)
        _stage(tmp_path, "dog", 2, partial=True)
        view = cur.load_view(tmp_path)
        assert view.fetched == {"cat": 3, "dog": 2}
        assert view.incomplete == ["dog"]

    def test_the_sidecar_is_not_an_image(self, tmp_path):
        _stage(tmp_path, "cat", 1)
        assert [p.name for p in cur.load_view(tmp_path).images["cat"]] == ["0001.jpg"]

    def test_empty_staging_is_a_precondition_error(self, tmp_path):
        with pytest.raises(OpticaValidationError, match="No fetched images"):
            cur.load_view(tmp_path)


class TestSession:
    def test_a_new_session_when_none_exists(self, tmp_path):
        session = cur.open_session(tmp_path)
        assert session.deselected == {}

    def test_deselections_are_restored(self, tmp_path):
        paths = _stage(tmp_path, "cat", 3)
        session = cur.open_session(tmp_path)
        session.toggle("cat", str(paths[1]), selected=False)
        session.save()
        view = cur.load_view(tmp_path)
        assert cur.selected_counts(view, cur.open_session(tmp_path)) == {"cat": 2}

    def test_a_corrupt_file_is_a_curation_error(self, tmp_path):
        path = CurationSession.at(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text("nope", encoding="utf-8")
        with pytest.raises(OpticaCurationError):
            cur.open_session(tmp_path)


class TestMaterialize:
    def test_writes_selected_images_only(self, tmp_path):
        paths = _stage(tmp_path, "cat", 3)
        _stage(tmp_path, "dog", 2)
        session = cur.open_session(tmp_path)
        session.toggle("cat", str(paths[0]), selected=False)
        report = cur.materialize_selection(
            cur.load_view(tmp_path), session, tmp_path / "dataset"
        )
        assert report.written == {"cat": 2, "dog": 2}
        assert sorted(p.name for p in (tmp_path / "dataset" / "cat").iterdir()) == [
            "0002.jpg",
            "0003.jpg",
        ]

    def test_byte_identical_selections_dedupe_within_class(self, tmp_path):
        paths = _stage(tmp_path, "cat", 2)
        paths[1].write_bytes(paths[0].read_bytes())
        report = cur.materialize_selection(
            cur.load_view(tmp_path), cur.open_session(tmp_path), tmp_path / "dataset"
        )
        assert report.written == {"cat": 1}
        assert report.duplicates == {"cat": 1}


class TestFetchMore:
    """The Curation Adapter's bridge to the Fetch Adapter.

    Covers plan § *Class imbalance and image validation*: "curation's Fetch More
    banner likewise requests enough to restore images_per_class selected".
    """

    @pytest.mark.parametrize(
        ("per_class", "selected", "count"), [(50, 12, 38), (50, 50, 0), (50, 80, 0)]
    )
    def test_requests_enough_to_restore_images_per_class_selected(
        self, per_class, selected, count
    ):
        assert cur.fetch_more_shortfall(per_class, selected) == count

    def test_an_ordinary_class_may_fetch_more(self, fake_home):
        _stage(fake_home, "cat", 3)
        assert cur.fetch_more_refusal("cat") is None

    def test_a_grouped_class_is_refused_in_this_build(self, fake_home):
        import json

        _stage(fake_home, "defective", 3)
        sidecar = fake_home / ".optica" / "staging" / "defective" / ".fetch.json"
        sidecar.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": {
                        "open-datasets": {
                            "tried": {"cracked_screen": [], "dented_case": []},
                            "delivered": {},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        reason = cur.fetch_more_refusal("defective")
        assert reason is not None
        assert "needs CLIP filtering" in reason
        with pytest.raises(OpticaError, match="Fetch More is not available"):
            cur.fetch_more("defective", 5, None, None)  # type: ignore[arg-type]

    def test_fetches_count_more_continuing_the_numbering(self, fake_home):
        from tests.unit.input.test_fetch import StubDownloader, StubSource, _pool

        candidates, bodies = _pool("cat", 12)
        source = StubSource({"cat": candidates})
        downloader = StubDownloader(bodies)
        from optica.input.classes import ResolvedClass
        from optica.input.fetch import fetch_class, staged_images

        fetch_class(ResolvedClass("cat", ["cat"], per_query=4), source, downloader)
        seen: list[int] = []
        report = cur.fetch_more(
            "cat", 3, source, downloader, on_image=lambda: seen.append(1)
        )
        folder = fake_home / ".optica" / "staging" / "cat"
        assert report.delivered == 3
        assert len(seen) == 3
        assert [p.name for p in staged_images(folder)] == [
            f"{i:04d}.jpg" for i in range(1, 8)
        ]
        # Candidates the first fetch tried are not downloaded again.
        assert len(downloader.calls) == len(set(downloader.calls)) == 7


class TestDeselectionsSurviveAFolderRename:
    """A class directory renamed under a curation session keeps its deselections.

    ``fetch_class`` renames ``<class>.partial/`` to ``<class>/`` when a fetch
    completes. ``curation.json`` stores full paths, so matching on the full path
    would silently reselect every image the user deselected before the rename.
    Entries are matched by class and file name instead (``notes/build-log.md``,
    option B — provisional, pending the amendment session); what is written is
    unchanged.
    """

    def test_an_interrupted_fetch_completing_does_not_reselect(self, fake_home):
        _stage(fake_home, "cat", 12, partial=True)
        _stage(fake_home, "dog", 12)
        view = cur.load_view()
        assert view.incomplete == ["cat"]
        session = cur.open_session()
        deselected = view.images["cat"][2]
        assert deselected.parent.name == "cat.partial"
        session.toggle("cat", str(deselected), selected=False)
        session.save()

        # The rename fetch_class performs when the interrupted fetch completes.
        staging = fake_home / ".optica" / "staging"
        (staging / "cat.partial").rename(staging / "cat")

        view = cur.load_view()
        resumed = cur.open_session()
        moved = view.images["cat"][2]
        assert moved.parent.name == "cat"
        assert moved.name == deselected.name
        assert resumed.is_selected("cat", str(moved)) is False
        assert cur.selected_counts(view, resumed) == {"cat": 11, "dog": 12}

    def test_the_file_written_is_unchanged_full_paths(self, fake_home):
        paths = _stage(fake_home, "cat", 3)
        session = cur.open_session()
        session.toggle("cat", str(paths[0]), selected=False)
        session.save()
        stored = (fake_home / ".optica" / "staging" / "curation.json").read_text(
            encoding="utf-8"
        )
        import json

        data = json.loads(stored)
        assert data["version"] == 1
        assert data["deselected"] == {"cat": [str(paths[0])]}

    def test_reselecting_after_the_rename_clears_the_old_entry(self, fake_home):
        _stage(fake_home, "cat", 3, partial=True)
        view = cur.load_view()
        session = cur.open_session()
        session.toggle("cat", str(view.images["cat"][0]), selected=False)
        session.save()
        staging = fake_home / ".optica" / "staging"
        (staging / "cat.partial").rename(staging / "cat")
        view = cur.load_view()
        session = cur.open_session()
        session.toggle("cat", str(view.images["cat"][0]), selected=True)
        assert session.deselected == {"cat": []}
        assert cur.selected_counts(view, session) == {"cat": 3}

    def test_deselecting_after_the_rename_does_not_duplicate_the_entry(self, fake_home):
        _stage(fake_home, "cat", 3, partial=True)
        view = cur.load_view()
        session = cur.open_session()
        session.toggle("cat", str(view.images["cat"][1]), selected=False)
        staging = fake_home / ".optica" / "staging"
        (staging / "cat.partial").rename(staging / "cat")
        view = cur.load_view()
        session.toggle("cat", str(view.images["cat"][1]), selected=False)
        assert len(session.deselected["cat"]) == 1

    def test_a_file_written_by_the_pass_2_code_reads_as_it_did(self, fake_home):
        # Existing curation.json files — absolute paths, one layout — are read
        # correctly with no conversion and no version change.
        import json

        cats = _stage(fake_home, "cat", 4)
        (fake_home / ".optica" / "staging" / "curation.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "created": "2026-09-13T10:00:00+00:00",
                    "updated": "2026-09-13T10:05:00+00:00",
                    "deselected": {"cat": [str(cats[1]), str(cats[3])]},
                    "active_class": "cat",
                }
            ),
            encoding="utf-8",
        )
        view = cur.load_view()
        session = cur.open_session()
        assert cur.selected_counts(view, session) == {"cat": 2}
        assert [session.is_selected("cat", str(p)) for p in cats] == [
            True,
            False,
            True,
            False,
        ]

    def test_a_windows_style_stored_path_matches_by_file_name(self, fake_home):
        cats = _stage(fake_home, "cat", 2)
        session = cur.open_session()
        stored = r"C:\Users\someone\.optica\staging\cat\0002.jpg"
        session.deselected = {"cat": [stored]}
        assert session.is_selected("cat", str(cats[1])) is False
        assert session.is_selected("cat", str(cats[0])) is True

    def test_the_class_still_scopes_the_match(self, fake_home):
        cats = _stage(fake_home, "cat", 2)
        dogs = _stage(fake_home, "dog", 2)
        session = cur.open_session()
        session.toggle("cat", str(cats[0]), selected=False)
        assert session.is_selected("dog", str(dogs[0])) is True
