"""Tests for ``optica.server.labeling``.

Covers plan § "Labeling & Curation" → *Labeling UI* (radio 2-5 / dropdown 6+,
"Finish" gating on both conditions with both shown at once, the hint text),
*The labeling interaction* (Assign commits; auto-advance; Next always enabled
and how a skip is recorded; Back shows the assignment and re-assigning returns
to where the user came from), *Finish with images left unlabeled* (the split
message), and *Staging shapes* → the labeling session file (written on every
decision; ``position`` is a path; resume at the first unlabeled image at or
after it).

Runs without the web extra, so it runs in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optica.input.sessions import LabelingSession, SourceType, load_labeling
from optica.input.validation import InPlaceReport, RejectReason
from optica.server.labeling import (
    LabelingController,
    finish_hint,
    unlabeled_message,
    widget_for,
)


def _images(folder: Path, count: int) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        path = folder / f"IMG_{i:04d}.jpg"
        path.write_bytes(b"not decoded by the controller")
        paths.append(path.resolve())
    return paths


def _controller(
    tmp_path: Path, count: int = 12, classes: tuple[str, ...] = ("cat", "dog")
) -> LabelingController:
    images = _images(tmp_path / "images", count)
    session = LabelingSession.new(
        tmp_path / "home", tmp_path / "images", SourceType.FOLDER, list(classes)
    )
    return LabelingController(session, images)


def _on_disk(controller: LabelingController) -> dict[str, object]:
    data: dict[str, object] = json.loads(
        controller.session.path.read_text(encoding="utf-8")
    )
    return data


class TestWidget:
    @pytest.mark.parametrize("count", [2, 3, 4, 5])
    def test_radio_buttons_for_two_to_five_classes(self, count):
        assert widget_for(count) == "radio"

    @pytest.mark.parametrize("count", [6, 7, 20])
    def test_a_dropdown_for_six_or_more(self, count):
        assert widget_for(count) == "dropdown"

    def test_the_state_carries_it(self, tmp_path):
        controller = _controller(tmp_path, classes=("a", "b", "c", "d", "e", "f"))
        assert controller.state()["widget"] == "dropdown"


class TestFinishGate:
    def test_the_plans_example_hint(self):
        # Plan: "Classes: cat (12 images), dog (2 images)  [Finish — disabled]
        #        Every class needs at least 5 images. dog needs 3 more."
        assert (
            finish_hint(["cat", "dog"], {"cat": 12, "dog": 2})
            == "Every class needs at least 5 images. dog needs 3 more."
        )

    def test_the_counts_row_matches_the_plan(self, tmp_path):
        controller = _controller(tmp_path, count=14)
        for i in range(12):
            controller.assign(i, "cat")
        controller.assign(12, "dog")
        controller.assign(13, "dog")
        state = controller.state()
        assert state["counts_line"] == "Classes: cat (12 images), dog (2 images)"
        assert state["finish"] == {
            "enabled": False,
            "hint": "Every class needs at least 5 images. dog needs 3 more.",
        }

    def test_every_short_class_is_named(self):
        hint = finish_hint(["cat", "dog", "bird"], {"cat": 5, "dog": 1})
        assert hint == (
            "Every class needs at least 5 images. dog needs 4 more, bird needs 5 more."
        )

    def test_both_conditions_are_shown_together_not_in_turn(self):
        hint = finish_hint(["cat"], {"cat": 2})
        assert hint == (
            "Labeling needs at least 2 classes. "
            "Every class needs at least 5 images. cat needs 3 more."
        )

    def test_enabled_at_the_floor(self):
        assert finish_hint(["cat", "dog"], {"cat": 5, "dog": 5}) is None

    def test_a_class_with_no_images_blocks_like_any_other(self):
        assert "dog needs 5 more" in (finish_hint(["cat", "dog"], {"cat": 9}) or "")

    def test_finish_is_refused_while_gated(self, tmp_path):
        controller = _controller(tmp_path)
        result = controller.finish(confirmed=True)
        assert result["status"] == "blocked"
        assert not controller.finished


class TestUnlabeledSplit:
    def test_the_plans_example(self):
        assert (
            unlabeled_message(4, 28)
            == "32 images will not be included: 4 skipped, 28 not yet reached."
        )

    def test_one_image(self):
        assert unlabeled_message(0, 1) == (
            "1 image will not be included: 0 skipped, 1 not yet reached."
        )

    def test_nothing_left_out_needs_no_confirmation(self):
        assert unlabeled_message(0, 0) is None

    def test_finish_asks_then_finishes_once_confirmed(self, tmp_path):
        controller = _controller(tmp_path, count=14)
        for i in range(5):
            controller.assign(i, "cat")
        for i in range(5, 10):
            controller.assign(i, "dog")
        controller.next(10)  # skipped; 11, 12, 13 never reached
        first = controller.finish(confirmed=False)
        assert first["status"] == "confirm"
        assert first["message"] == (
            "4 images will not be included: 1 skipped, 3 not yet reached."
        )
        assert not controller.finished
        assert controller.finish(confirmed=True)["status"] == "finished"
        assert controller.finished

    def test_finish_needs_no_confirmation_when_everything_is_labeled(self, tmp_path):
        controller = _controller(tmp_path, count=10)
        for i in range(10):
            controller.assign(i, "cat" if i < 5 else "dog")
        assert controller.finish(confirmed=False)["status"] == "finished"


class TestAssign:
    def test_commits_to_the_session_file_immediately(self, tmp_path):
        controller = _controller(tmp_path)
        controller.assign(0, "cat")
        stored = _on_disk(controller)
        image = controller.images[0]
        assert stored["entries"] == {image: {"state": "labeled", "class": "cat"}}

    def test_auto_advance_moves_to_the_next_image(self, tmp_path):
        controller = _controller(tmp_path)
        state = controller.assign(0, "cat")
        assert state["index"] == 1
        assert state["position"] == "2 of 12"

    def test_without_auto_advance_it_stays(self, tmp_path):
        controller = _controller(tmp_path)
        controller.set_auto_advance(False)
        assert controller.assign(0, "cat")["index"] == 0

    def test_an_unknown_class_is_refused(self, tmp_path):
        controller = _controller(tmp_path)
        with pytest.raises(ValueError, match="bird"):
            controller.assign(0, "bird")

    def test_an_index_out_of_range_is_refused(self, tmp_path):
        controller = _controller(tmp_path)
        with pytest.raises(ValueError, match="out of range"):
            controller.assign(99, "cat")

    def test_assigning_at_the_last_image_stays_there(self, tmp_path):
        controller = _controller(tmp_path, count=3)
        state = controller.assign(2, "cat")
        assert state["index"] == 2
        assert state["at_end"]


class TestNextAndBack:
    def test_next_records_a_skip(self, tmp_path):
        controller = _controller(tmp_path)
        controller.next(0)
        expected = {controller.images[0]: {"state": "skipped"}}
        assert _on_disk(controller)["entries"] == expected

    def test_next_never_overwrites_a_label(self, tmp_path):
        controller = _controller(tmp_path)
        controller.set_auto_advance(False)
        controller.assign(0, "dog")
        controller.next(0)
        assert controller.session.entries[controller.images[0]] == {
            "state": "labeled",
            "class": "dog",
        }

    def test_back_shows_the_previous_assignment(self, tmp_path):
        controller = _controller(tmp_path)
        controller.assign(0, "dog")
        state = controller.back(1)
        assert state["index"] == 0
        assert state["image"]["state"] == "labeled"
        assert state["image"]["class"] == "dog"

    def test_reassigning_after_back_returns_to_where_the_user_came_from(self, tmp_path):
        controller = _controller(tmp_path)
        controller.assign(0, "dog")
        controller.assign(1, "cat")
        controller.back(2)
        state = controller.assign(1, "dog")
        assert state["index"] == 2
        assert controller.session.entries[controller.images[1]]["class"] == "dog"

    def test_back_at_the_first_image_stays(self, tmp_path):
        assert _controller(tmp_path).back(0)["index"] == 0

    def test_position_is_saved_as_a_path_not_an_index(self, tmp_path):
        controller = _controller(tmp_path)
        controller.next(0)
        controller.next(1)
        controller.back(2)
        assert _on_disk(controller)["position"] == controller.images[1]

    def test_auto_advance_is_written_to_the_session_not_config(self, tmp_path):
        controller = _controller(tmp_path)
        controller.set_auto_advance(False)
        assert _on_disk(controller)["auto_advance"] is False
        assert not (tmp_path / "home" / ".optica" / "config.toml").exists()


class TestResume:
    def test_resumes_at_the_first_unlabeled_image_at_or_after_position(self, tmp_path):
        first = _controller(tmp_path)
        first.assign(0, "cat")
        first.assign(1, "cat")
        first.next(2)
        first.back(3)
        first.back(2)  # position is now image 1
        reloaded = load_labeling(first.session.path)
        resumed = LabelingController(reloaded, [Path(p) for p in first.images])
        # 1 and 2 have decisions; 3 is the first with none.
        assert resumed.index == 3

    def test_a_session_with_nothing_left_shows_where_it_was_left(self, tmp_path):
        first = _controller(tmp_path, count=3)
        for i in range(3):
            first.next(i)
        reloaded = load_labeling(first.session.path)
        resumed = LabelingController(reloaded, [Path(p) for p in first.images])
        assert resumed.index == 2

    def test_counts_ignore_entries_for_images_no_longer_in_the_run(self, tmp_path):
        controller = _controller(tmp_path, count=4)
        controller.assign(0, "cat")
        controller.assign(1, "cat")
        remaining = [Path(p) for p in controller.images[1:]]
        again = LabelingController(load_labeling(controller.session.path), remaining)
        assert again.counts() == {"cat": 1, "dog": 0}
        assert again.labeled_items() == [(remaining[0], "cat")]


class TestImagesAndNotice:
    def test_images_are_path_sorted_and_served_by_index(self, tmp_path):
        images = _images(tmp_path / "images", 3)
        session = LabelingSession.new(
            tmp_path / "home", tmp_path / "images", SourceType.FOLDER, ["cat", "dog"]
        )
        controller = LabelingController(session, list(reversed(images)))
        assert controller.image_path("0") == images[0]
        assert controller.image_path("2") == images[2]

    @pytest.mark.parametrize("image_id", ["3", "-1", "../x", "", "1.0"])
    def test_anything_but_a_valid_index_is_no_image(self, tmp_path, image_id):
        assert _controller(tmp_path, count=3).image_path(image_id) is None

    def test_unreadable_files_are_listed_individually_and_truncated_past_ten(
        self, tmp_path
    ):
        images = _images(tmp_path / "images", 2)
        bad = [
            InPlaceReport(tmp_path / f"bad{i}.jpg", RejectReason.TRUNCATED)
            for i in range(12)
        ]
        session = LabelingSession.new(
            tmp_path / "home", tmp_path / "images", SourceType.FOLDER, ["cat", "dog"]
        )
        notice = LabelingController(session, images, bad).state()["unreadable"]
        assert notice["count"] == 12
        assert len(notice["lines"]) == 10
        assert notice["lines"][0] == f"{tmp_path / 'bad0.jpg'}: truncated file"
        assert notice["more"] == 2

    def test_no_readable_images_is_refused(self, tmp_path):
        session = LabelingSession.new(
            tmp_path / "home", tmp_path / "images", SourceType.FOLDER, ["cat", "dog"]
        )
        with pytest.raises(ValueError):
            LabelingController(session, [])
