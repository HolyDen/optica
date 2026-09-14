"""Tests for ``optica.server.curation``.

Covers plan § "Labeling & Curation" → *Curation Server* → *Browser UI
(curate)*: tabs for 6 or fewer classes with short names, a dropdown for 7+ or
any name over 20 characters; click-to-toggle; Select All / Deselect All; the
low-selection warning (under 30% or fewer than 10 selected) with a Fetch More
banner that is advisory only; Confirm disabled only by a class with zero
selected; and *Staging shapes* → ``curation.json`` written on every toggle, the
active class recorded, and deselections recorded rather than selections.

Runs without the web extra, so it runs in CI.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from optica.exceptions import OpticaFetchError
from optica.input.curation import load_view, open_session
from optica.input.fetch import ClassFetchReport
from optica.server.curation import (
    CurationController,
    confirm_hint,
    navigation_for,
)


def _stage(home: Path, name: str, count: int) -> list[Path]:
    folder = home / ".optica" / "staging" / name
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(1, count + 1):
        path = folder / f"{i:04d}.jpg"
        path.write_bytes(f"{name}-{i}".encode())
        paths.append(path)
    return paths


def _controller(
    home: Path,
    counts: dict[str, int] | None = None,
    *,
    per_class: int = 50,
    fetch_more: Callable[[str, int, Callable[[], None]], ClassFetchReport] | None = None,
) -> CurationController:
    for name, count in (counts or {"cat": 12, "dog": 12}).items():
        _stage(home, name, count)
    return CurationController(
        load_view(), open_session(), per_class, reload=load_view, fetch_more=fetch_more
    )


def _stored(home: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(
        (home / ".optica" / "staging" / "curation.json").read_text(encoding="utf-8")
    )
    return data


class TestNavigation:
    @pytest.mark.parametrize("count", [1, 2, 6])
    def test_tabs_for_six_or_fewer_short_names(self, count):
        assert navigation_for([f"class{i}" for i in range(count)]) == "tabs"

    def test_a_dropdown_at_seven(self):
        assert navigation_for([f"c{i}" for i in range(7)]) == "dropdown"

    def test_any_name_over_twenty_characters_is_a_dropdown(self):
        assert navigation_for(["cat", "a" * 21]) == "dropdown"

    def test_twenty_characters_exactly_is_still_short(self):
        assert navigation_for(["cat", "a" * 20]) == "tabs"


class TestToggle:
    def test_every_toggle_is_written_to_curation_json(self, fake_home):
        controller = _controller(fake_home)
        controller.toggle(0, 2, selected=False)
        path = str(controller.view.images["cat"][2])
        assert _stored(fake_home)["deselected"] == {"cat": [path]}
        controller.toggle(0, 2, selected=True)
        assert _stored(fake_home)["deselected"] == {"cat": []}

    def test_state_reflects_the_toggle(self, fake_home):
        controller = _controller(fake_home)
        state = controller.toggle(0, 0, selected=False)
        assert state["images"][0]["selected"] is False
        assert state["classes"][0]["selected"] == 11

    def test_select_all_and_deselect_all_apply_to_one_class(self, fake_home):
        controller = _controller(fake_home)
        state = controller.set_all(1, selected=False)
        assert [c["selected"] for c in state["classes"]] == [12, 0]
        state = controller.set_all(1, selected=True)
        assert [c["selected"] for c in state["classes"]] == [12, 12]
        assert _stored(fake_home)["deselected"] == {"dog": []}

    @pytest.mark.parametrize(("class_index", "image_index"), [(2, 0), (0, 12), (-1, 0)])
    def test_out_of_range_is_refused(self, fake_home, class_index, image_index):
        with pytest.raises(ValueError, match="out of range"):
            _controller(fake_home).toggle(class_index, image_index, selected=False)

    def test_images_added_later_default_to_selected(self, fake_home):
        controller = _controller(fake_home)
        controller.set_all(0, selected=False)
        _stage(fake_home, "cat", 14)  # two more arrive, as Fetch More adds them
        reloaded = CurationController(load_view(), open_session(), 50)
        assert reloaded.selected()["cat"] == 2


class TestActiveClass:
    def test_switching_is_recorded_for_a_resume(self, fake_home):
        controller = _controller(fake_home)
        state = controller.set_active(1)
        assert state["active"] == 1
        assert state["images"][0]["id"] == "1/0"
        assert _stored(fake_home)["active_class"] == "dog"
        resumed = CurationController(load_view(), open_session(), 50)
        assert resumed.state()["active"] == 1

    def test_a_stored_class_no_longer_staged_falls_back_to_the_first(self, fake_home):
        _stage(fake_home, "cat", 3)
        _stage(fake_home, "dog", 3)
        stored = fake_home / ".optica" / "staging" / "curation.json"
        stored.write_text(
            json.dumps({"version": 1, "deselected": {}, "active_class": "hamster"}),
            encoding="utf-8",
        )
        controller = CurationController(load_view(), open_session(), 50)
        assert controller.state()["active"] == 0
        assert controller.session.active_class == "cat"


class TestWarningsAndConfirm:
    def test_low_selection_warns_with_each_triggers_message(self, fake_home):
        controller = _controller(fake_home, {"cat": 40, "dog": 12})
        for i in range(35):
            controller.toggle(0, i, selected=False)
        cat = controller.state()["classes"][0]
        assert cat["selected"] == 5
        assert cat["warnings"] == [
            "cat: only 5 of 40 fetched images selected (12%, below 30%)",
            "cat: only 5 images selected (fewer than 10)",
        ]

    def test_the_warning_is_advisory_confirm_stays_enabled(self, fake_home):
        controller = _controller(fake_home)
        for i in range(10):
            controller.toggle(0, i, selected=False)
        state = controller.state()
        assert state["classes"][0]["warnings"]
        assert state["confirm"] == {"enabled": True, "hint": None}
        assert controller.confirm()["status"] == "finished"

    def test_only_a_class_with_zero_selected_disables_confirm(self, fake_home):
        controller = _controller(fake_home)
        state = controller.set_all(1, selected=False)
        assert state["confirm"] == {
            "enabled": False,
            "hint": "Select at least one image in dog to confirm.",
        }
        result = controller.confirm()
        assert result["status"] == "blocked"
        assert not controller.finished

    def test_confirm_hint(self):
        assert confirm_hint([]) is None
        assert confirm_hint(["cat", "dog"]) == (
            "Select at least one image in cat, dog to confirm."
        )


class TestImages:
    def test_served_by_class_and_image_index(self, fake_home):
        controller = _controller(fake_home)
        assert controller.image_path("1/3") == controller.view.images["dog"][3]

    @pytest.mark.parametrize("image_id", ["2/0", "0/12", "0", "a/b", "../0", "0/-1"])
    def test_anything_else_is_no_image(self, fake_home, image_id):
        assert _controller(fake_home).image_path(image_id) is None


class TestFetchMore:
    def test_not_offered_without_a_fetcher(self, fake_home):
        controller = _controller(fake_home)
        assert controller.state()["classes"][0]["fetch_more"]["available"] is False
        with pytest.raises(ValueError, match="not available"):
            controller.start_fetch_more(0)

    def test_offered_with_the_shortfall_to_images_per_class(self, fake_home):
        controller = _controller(fake_home, fetch_more=lambda *a: pytest.fail("ran"))
        offer = controller.state()["classes"][0]["fetch_more"]
        assert offer == {"available": True, "count": 38, "unavailable_reason": None}

    def test_nothing_to_request_is_refused(self, fake_home):
        controller = _controller(
            fake_home, per_class=10, fetch_more=lambda *a: pytest.fail("ran")
        )
        assert controller.state()["classes"][0]["fetch_more"]["available"] is False
        with pytest.raises(ValueError, match="already has 10 or more"):
            controller.start_fetch_more(0)

    def test_runs_in_the_background_then_reloads_staging(self, fake_home):
        release = threading.Event()
        started = threading.Event()
        calls: list[tuple[str, int]] = []

        def fetcher(
            name: str, count: int, on_image: Callable[[], None]
        ) -> ClassFetchReport:
            calls.append((name, count))
            started.set()
            release.wait(5)
            _stage(fake_home, name, 15)
            for _ in range(3):
                on_image()
            return ClassFetchReport(name, 15, existing=12, delivered=3)

        controller = _controller(fake_home, fetch_more=fetcher)
        state = controller.start_fetch_more(0)
        assert started.wait(5)
        assert state["fetching"] == {"class": "cat", "requested": 38, "delivered": 0}
        # While it runs: that class's images are not served, Confirm waits.
        assert controller.image_path("0/0") is None
        assert controller.image_path("1/0") is not None
        assert controller.state()["confirm"] == {
            "enabled": False,
            "hint": "Wait for the fetch for cat to finish.",
        }
        assert controller.confirm()["status"] == "blocked"
        with pytest.raises(ValueError, match="already running"):
            controller.start_fetch_more(1)
        release.set()
        for _ in range(100):
            if controller.fetching is None:
                break
            threading.Event().wait(0.02)
        state = controller.state()
        assert calls == [("cat", 38)]
        assert state["fetching"] is None
        assert state["last_fetch"] == {
            "class": "cat",
            "requested": 38,
            "delivered": 3,
            "error": None,
        }
        assert state["classes"][0]["fetched"] == 15
        assert state["classes"][0]["selected"] == 15

    def test_a_failed_fetch_is_shown_and_the_session_continues(self, fake_home):
        def fetcher(
            name: str, count: int, on_image: Callable[[], None]
        ) -> ClassFetchReport:
            raise OpticaFetchError("Open Images could not be reached.")

        controller = _controller(fake_home, fetch_more=fetcher)
        controller.start_fetch_more(0)
        for _ in range(100):
            if controller.fetching is None:
                break
            threading.Event().wait(0.02)
        assert controller.state()["last_fetch"]["error"] == (
            "Open Images could not be reached."
        )
        assert controller.confirm()["status"] == "finished"
