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

from optica.exceptions import OpticaCurationError, OpticaValidationError
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
