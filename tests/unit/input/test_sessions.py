"""Staging session stores.

Covers plan § "Labeling & Curation" → *Staging shapes* (the labeling session
file and ``curation.json``, their fields, version checking, and the
adopt-the-new-list rule), *Deletion, staging, and interruption* (session ID),
and Implementation Note 14.
"""

from __future__ import annotations

import json

import pytest

from optica.exceptions import OpticaCurationError, OpticaLabelingError
from optica.input import sessions as s


@pytest.fixture
def labeling(tmp_path):
    source = tmp_path / "images"
    source.mkdir()
    return s.LabelingSession.new(
        tmp_path / "home", source, s.SourceType.FOLDER, ["cat", "dog"]
    )


class TestSessionId:
    def test_a_folder_digest_is_stable(self, tmp_path):
        assert s.session_id(tmp_path) == s.session_id(tmp_path)

    def test_relative_and_absolute_spellings_are_one_session(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "images").mkdir()
        from pathlib import Path

        assert s.session_id(Path("images")) == s.session_id(tmp_path / "images")

    def test_a_modified_manifest_starts_a_fresh_session(self, tmp_path):
        manifest = tmp_path / "m.csv"
        assert s.session_id(manifest, "aaa") != s.session_id(manifest, "bbb")

    def test_classes_are_not_part_of_it(self, tmp_path):
        a = s.LabelingSession.new(tmp_path, tmp_path, s.SourceType.FOLDER, ["cat", "dog"])
        b = s.LabelingSession.new(
            tmp_path, tmp_path, s.SourceType.FOLDER, ["cat", "bird"]
        )
        assert a.path == b.path


class TestLabelingFileShape:
    def test_round_trip_matches_the_plans_fields(self, labeling):
        labeling.assign("/imgs/IMG_0001.jpg", "cat")
        labeling.skip("/imgs/IMG_0002.jpg")
        labeling.save()
        raw = json.loads(labeling.path.read_text(encoding="utf-8"))
        assert raw["version"] == 1
        assert set(raw) == {
            "version", "source", "source_type", "created", "updated",
            "classes", "auto_advance", "position", "entries",
        }  # fmt: skip
        assert raw["entries"]["/imgs/IMG_0001.jpg"] == {
            "state": "labeled",
            "class": "cat",
        }
        assert raw["entries"]["/imgs/IMG_0002.jpg"] == {"state": "skipped"}
        assert raw["position"] == "/imgs/IMG_0002.jpg"
        loaded = s.load_labeling(labeling.path)
        assert loaded.entries == labeling.entries
        assert loaded.classes == ["cat", "dog"]

    def test_the_write_is_atomic_and_leaves_no_temp_file(self, labeling):
        labeling.save()
        labeling.save()
        assert [p.name for p in labeling.path.parent.iterdir()] == [labeling.path.name]

    def test_assigning_an_unknown_class_is_a_bug_not_a_state(self, labeling):
        with pytest.raises(ValueError, match="not one of"):
            labeling.assign("/x.jpg", "bird")


class TestLabelingErrors:
    def test_unparseable_file_is_a_labeling_error_naming_the_path(self, tmp_path):
        path = tmp_path / "abc.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(OpticaLabelingError) as info:
            s.load_labeling(path)
        assert str(path) in info.value.message
        assert "Delete" in info.value.fix[0]

    def test_version_mismatch_is_the_same_hard_error(self, tmp_path):
        path = tmp_path / "abc.json"
        path.write_text(json.dumps({"version": 2}), encoding="utf-8")
        with pytest.raises(OpticaLabelingError, match="unrecognized version"):
            s.load_labeling(path)

    def test_missing_version_is_rejected(self, tmp_path):
        path = tmp_path / "abc.json"
        path.write_text(json.dumps({"source": "x"}), encoding="utf-8")
        with pytest.raises(OpticaLabelingError):
            s.load_labeling(path)

    def test_a_bad_shape_is_corrupt(self, tmp_path):
        path = tmp_path / "abc.json"
        path.write_text(
            json.dumps(
                {"version": 1, "source": "x", "source_type": "folder", "classes": "cat"}
            ),
            encoding="utf-8",
        )
        with pytest.raises(OpticaLabelingError, match="corrupt"):
            s.load_labeling(path)

    def test_unreadable_is_a_labeling_error(self, tmp_path):
        with pytest.raises(OpticaLabelingError):
            s.load_labeling(tmp_path / "missing.json")


class TestAdoptNewList:
    def test_departing_class_entries_return_to_the_queue(self, labeling):
        labeling.assign("/a.jpg", "cat")
        labeling.assign("/b.jpg", "dog")
        labeling.skip("/c.jpg")
        departed = labeling.adopt_classes(["cat", "puppy"])
        assert departed == 1
        assert "/b.jpg" not in labeling.entries
        assert labeling.entries["/a.jpg"]["class"] == "cat"
        # Skips are decisions about images, not classes, and stay.
        assert labeling.entries["/c.jpg"] == {"state": "skipped"}
        assert labeling.classes == ["cat", "puppy"]

    def test_disagreement_is_detected(self, labeling):
        assert labeling.classes_disagree(["cat", "bird"])
        assert not labeling.classes_disagree(["cat", "dog"])


class TestResumePosition:
    def test_first_unlabeled_at_or_after_position(self, labeling):
        images = ["/1.jpg", "/2.jpg", "/3.jpg", "/4.jpg"]
        labeling.assign("/1.jpg", "cat")
        labeling.assign("/2.jpg", "cat")
        labeling.entries["/3.jpg"] = {"state": "labeled", "class": "dog"}
        labeling.position = "/2.jpg"
        assert labeling.resume_index(images) == 3

    def test_a_removed_position_file_resumes_at_the_next(self, labeling):
        labeling.position = "/2.jpg"
        assert labeling.resume_index(["/1.jpg", "/3.jpg"]) == 1

    def test_nothing_left_means_complete(self, labeling):
        labeling.assign("/1.jpg", "cat")
        assert labeling.resume_index(["/1.jpg"]) is None

    def test_no_position_starts_at_the_beginning(self, labeling):
        assert labeling.resume_index(["/b.jpg", "/a.jpg"]) == 0


class TestFinishSplit:
    def test_skipped_and_not_reached_are_counted_separately(self, labeling):
        images = [f"/{i}.jpg" for i in range(6)]
        labeling.assign(images[0], "cat")
        labeling.skip(images[1])
        labeling.skip(images[2])
        assert labeling.unlabeled_split(images) == (2, 3)

    def test_counts_by_class(self, labeling):
        labeling.assign("/a.jpg", "cat")
        labeling.assign("/b.jpg", "cat")
        assert labeling.counts() == {"cat": 2, "dog": 0}


class TestCurationFile:
    def test_round_trip(self, tmp_path):
        session = s.CurationSession(s.CurationSession.at(tmp_path))
        session.toggle("cat", "/s/cat/0007.jpg", selected=False)
        session.active_class = "cat"
        session.save()
        raw = json.loads(session.path.read_text(encoding="utf-8"))
        assert set(raw) == {"version", "created", "updated", "deselected", "active_class"}
        assert raw["deselected"] == {"cat": ["/s/cat/0007.jpg"]}
        loaded = s.load_curation(session.path)
        assert not loaded.is_selected("cat", "/s/cat/0007.jpg")
        # Fetch More images are selected by default, with no special case.
        assert loaded.is_selected("cat", "/s/cat/0051.jpg")

    def test_reselecting_removes_the_deselection(self, tmp_path):
        session = s.CurationSession(tmp_path / "curation.json")
        session.toggle("cat", "/x.jpg", selected=False)
        session.toggle("cat", "/x.jpg", selected=True)
        assert session.deselected == {"cat": []}

    def test_corrupt_is_a_curation_error(self, tmp_path):
        path = tmp_path / "curation.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(OpticaCurationError):
            s.load_curation(path)

    def test_version_mismatch(self, tmp_path):
        path = tmp_path / "curation.json"
        path.write_text(json.dumps({"version": 0}), encoding="utf-8")
        with pytest.raises(OpticaCurationError, match="unrecognized version"):
            s.load_curation(path)

    def test_bad_deselected_shape(self, tmp_path):
        path = tmp_path / "curation.json"
        path.write_text(
            json.dumps({"version": 1, "deselected": {"cat": 3}}), encoding="utf-8"
        )
        with pytest.raises(OpticaCurationError, match="corrupt"):
            s.load_curation(path)


class TestPaths:
    def test_staging_layout(self, tmp_path):
        assert s.staging_root(tmp_path) == tmp_path / ".optica" / "staging"
        assert s.labeling_dir(tmp_path) == tmp_path / ".optica" / "staging" / "labeling"
        assert s.CurationSession.at(tmp_path).name == "curation.json"
