"""The Input Manager.

Covers plan § "Input & Acquisition" → *Label mode — detection order* (cases
1 to 5, the explicit ``--dataset`` never falling through, contextual mode defaults
and per-invocation legality of ``default_mode``, the acquisition short-circuit,
exactly one input source), *Class-count validation* (the no-prompt error text),
*``--classes`` against an already-organized dataset* (asymmetric validation,
order of evaluation, the subset prompt text), *Fetch sources* (soft cap),
*``dataset/`` conflict* (keyed to the destination; replace, never merge), *CLIP
Adapter* (the seven ``clip_threshold`` bands), and § "Configuration" →
``--clear-staging`` (all three staging shapes).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optica.exceptions import OpticaCLIPError, OpticaConfigError, OpticaValidationError
from optica.input import manager as m


class TestSingleInputSource:
    def test_folder_and_manifest_together_are_unsupported_not_invalid(self, tmp_path):
        with pytest.raises(OpticaValidationError) as info:
            m.require_single_input_source(tmp_path, tmp_path / "m.csv")
        assert "unsupported in V1" in info.value.message

    @pytest.mark.parametrize(
        ("folder", "manifest", "expected"),
        [
            (Path("x"), None, m.InputSource.FOLDER),
            (None, Path("m.csv"), m.InputSource.MANIFEST),
            (None, None, m.InputSource.FETCH),
        ],
    )
    def test_each_single_source(self, folder, manifest, expected):
        assert m.require_single_input_source(folder, manifest) is expected


class TestModeResolution:
    def test_curate_is_the_default_when_fetching(self):
        resolved = m.resolve_mode(
            command="run", explicit=None, configured=None, local_input=False
        )
        assert resolved.line == "Mode: curate (default)"

    def test_label_is_the_default_for_local_input(self):
        resolved = m.resolve_mode(
            command="run", explicit=None, configured=None, local_input=True
        )
        assert resolved.line == "Mode: label (default for local input)"

    def test_configured_value_applies_where_legal(self):
        resolved = m.resolve_mode(
            command="run", explicit=None, configured="clip", local_input=False
        )
        assert resolved.line == "Mode: clip (from config)"

    def test_configured_clip_is_ignored_for_local_input_rather_than_erroring(self):
        # `default_mode = clip` is legal for the command `run` yet not for
        # `optica run --folder ./images`: legality is per invocation.
        resolved = m.resolve_mode(
            command="run", explicit=None, configured="clip", local_input=True
        )
        assert resolved.mode == "label"

    def test_configured_label_is_not_legal_under_fetch(self):
        resolved = m.resolve_mode(
            command="fetch", explicit=None, configured="label", local_input=False
        )
        assert resolved.mode == "curate"

    def test_explicit_mode_is_reported_as_such(self):
        resolved = m.resolve_mode(
            command="fetch", explicit="clip", configured=None, local_input=False
        )
        assert resolved.line == "Mode: clip (--mode)"

    @pytest.mark.parametrize("mode", ["curate", "clip"])
    def test_fetching_modes_with_local_input_error_with_the_corrected_command(self, mode):
        argv = ["run", "--mode", mode, "--folder", "./images", "-c", "cat,dog"]
        with pytest.raises(OpticaValidationError) as info:
            m.resolve_mode(
                command="run", explicit=mode, configured=None, local_input=True, argv=argv
            )
        assert "requires fetched input" in info.value.message
        assert info.value.fix[-1] == "optica run --folder ./images -c cat,dog"


class TestDetectionOrder:
    def test_folder_first(self, tmp_path):
        case = m.detect_label_input(
            folder=tmp_path,
            manifest=tmp_path / "m.csv",
            dataset=tmp_path,
            dataset_explicit=True,
        )
        assert case is m.DetectionCase.FOLDER

    def test_manifest_second(self, tmp_path):
        case = m.detect_label_input(
            folder=None,
            manifest=tmp_path / "m.csv",
            dataset=tmp_path,
            dataset_explicit=True,
        )
        assert case is m.DetectionCase.MANIFEST

    def test_a_missing_explicit_dataset_never_falls_through_to_case_4(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "dataset" / "cat").mkdir(parents=True)
        with pytest.raises(OpticaValidationError, match="No dataset found at datset"):
            m.detect_label_input(
                folder=None, manifest=None, dataset=Path("datset"), dataset_explicit=True
            )

    def test_default_dataset_present(self, tmp_path):
        (tmp_path / "dataset" / "cat").mkdir(parents=True)
        case = m.detect_label_input(
            folder=None,
            manifest=None,
            dataset=tmp_path / "dataset",
            dataset_explicit=False,
        )
        assert case is m.DetectionCase.DEFAULT_DATASET

    def test_nothing_lists_every_valid_option(self, tmp_path):
        with pytest.raises(OpticaValidationError) as info:
            m.detect_label_input(
                folder=None,
                manifest=None,
                dataset=tmp_path / "dataset",
                dataset_explicit=False,
            )
        joined = " ".join(info.value.fix)
        assert "--folder" in joined
        assert "--manifest" in joined
        assert "--dataset" in joined


class TestShortCircuit:
    def _organized(self, tmp_path: Path) -> Path:
        (tmp_path / "ds" / "cat").mkdir(parents=True)
        return tmp_path / "ds"

    def test_explicit_organized_dataset_with_no_source_skips_acquisition(self, tmp_path):
        assert m.short_circuits_acquisition(
            dataset=self._organized(tmp_path),
            dataset_explicit=True,
            folder=None,
            manifest=None,
            explicit_mode=None,
        )

    def test_bare_dataset_presence_does_not(self, tmp_path):
        assert not m.short_circuits_acquisition(
            dataset=self._organized(tmp_path),
            dataset_explicit=False,
            folder=None,
            manifest=None,
            explicit_mode=None,
        )

    @pytest.mark.parametrize("mode", ["curate", "clip"])
    def test_an_explicit_fetching_mode_overrides_it(self, tmp_path, mode):
        assert not m.short_circuits_acquisition(
            dataset=self._organized(tmp_path),
            dataset_explicit=True,
            folder=None,
            manifest=None,
            explicit_mode=mode,
        )

    def test_an_input_source_makes_dataset_the_destination(self, tmp_path):
        assert not m.short_circuits_acquisition(
            dataset=self._organized(tmp_path),
            dataset_explicit=True,
            folder=tmp_path,
            manifest=None,
            explicit_mode=None,
        )


class TestDestination:
    def test_absent_or_empty_needs_no_prompt(self, tmp_path):
        assert m.destination_contents(tmp_path / "nope") is None
        (tmp_path / "empty").mkdir()
        assert m.destination_contents(tmp_path / "empty") is None

    def test_populated_lists_per_class_counts_like_the_plan(self, tmp_path):
        dest = tmp_path / "dataset"
        for name, count in (("cat", 50), ("dog", 47)):
            (dest / name).mkdir(parents=True)
            for i in range(count):
                (dest / name / f"{i}.jpg").write_bytes(b"x")
        counts = m.destination_contents(dest)
        assert counts == {"cat": 50, "dog": 47}
        lines = m.describe_destination(dest, counts, "labels from --folder")
        assert lines == [
            "dataset/ already exists and will be replaced with new labels from --folder:",
            "  cat: 50 images",
            "  dog: 47 images",
        ]

    def test_replace_removes_rather_than_merges(self, tmp_path):
        dest = tmp_path / "dataset"
        (dest / "old").mkdir(parents=True)
        (dest / "old" / "stale.jpg").write_bytes(b"x")
        m.replace_destination(dest)
        assert dest.is_dir()
        assert list(dest.iterdir()) == []
        assert tmp_path.exists()

    def test_the_partial_is_a_hidden_sibling(self, tmp_path):
        # A sibling, so the final rename stays on one filesystem.
        dest = tmp_path / "data" / "dataset"
        assert m.partial_destination(dest) == tmp_path / "data" / ".dataset.partial"

    def test_commit_replaces_the_old_dataset_with_the_new_one(self, tmp_path):
        dest = tmp_path / "dataset"
        (dest / "old").mkdir(parents=True)
        (dest / "old" / "stale.jpg").write_bytes(b"x")
        partial = m.partial_destination(dest)
        (partial / "cat").mkdir(parents=True)
        (partial / "cat" / "a.jpg").write_bytes(b"new")
        m.commit_dataset(partial, dest)
        assert not partial.exists()
        assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*")) == [
            "cat",
            "cat/a.jpg",
        ]

    def test_commit_into_an_absent_destination(self, tmp_path):
        dest = tmp_path / "dataset"
        partial = m.partial_destination(dest)
        (partial / "dog").mkdir(parents=True)
        m.commit_dataset(partial, dest)
        assert (dest / "dog").is_dir()
        assert not partial.exists()

    def test_commit_replaces_a_file_standing_where_the_folder_goes(self, tmp_path):
        dest = tmp_path / "dataset"
        dest.write_bytes(b"not a folder")
        partial = m.partial_destination(dest)
        partial.mkdir()
        m.commit_dataset(partial, dest)
        assert dest.is_dir()

    def test_unattended_refusal_names_overwrite(self, tmp_path):
        error = m.overwrite_refused(tmp_path / "dataset")
        assert isinstance(error, OpticaValidationError)
        assert any("--overwrite" in line for line in error.fix)


class TestClassesAgainstDataset:
    def test_a_missing_folder_is_a_hard_error_with_both_lists(self):
        with pytest.raises(OpticaValidationError) as info:
            m.compare_classes(["cat", "pug"], ["cat", "golden_retriever"])
        err = info.value
        assert err.message == "--classes does not match the dataset folder structure."
        assert err.fix == [
            "In --classes but no matching folder: pug",
            "In dataset/ but not in --classes: golden_retriever",
            "Fix the --classes list, drop --classes, or rename the folders, and try again.",  # noqa: E501 - verbatim plan text
        ]

    def test_the_hard_error_fires_before_any_subset_question(self):
        folders = ["cat", "dog", "fish"]
        with pytest.raises(OpticaValidationError):
            m.compare_classes(["cat", "typo"], folders)

    def test_a_subset_asks_with_the_plans_wording(self):
        folders = [
            "bird", "cat", "dog", "fish", "hamster", "lizard", "parrot", "rabbit",
            "snake", "turtle",
        ]  # fmt: skip
        confirmation = m.compare_classes(["cat", "dog", "bird"], folders)
        assert confirmation is not None
        assert confirmation.lines == [
            "--classes requests training on: cat, dog, bird (3 of 10 folders found)",
            "Excluded from this run: fish, hamster, lizard, parrot, rabbit, snake, turtle",  # noqa: E501 - verbatim plan text
        ]
        assert confirmation.question == "Proceed with the 3 requested classes only?"

    def test_the_exclude_list_truncates_past_ten(self):
        folders = ["a"] + [f"x{i:02d}" for i in range(12)]
        confirmation = m.compare_classes(["a"], folders)
        assert confirmation is not None
        assert confirmation.lines[1].endswith("(and 2 more)")

    def test_exact_match_in_any_order_is_silent(self):
        assert m.compare_classes(["dog", "cat"], ["cat", "dog"]) is None


class TestClipThresholdBands:
    @pytest.mark.parametrize(
        ("value", "band"),
        [
            (-0.1, m.ThresholdBand.OUT_OF_RANGE),
            (1.5, m.ThresholdBand.OUT_OF_RANGE),
            (0.0, m.ThresholdBand.ZERO),
            (1.0, m.ThresholdBand.ONE),
            (0.75, m.ThresholdBand.STRICT),
            (0.99, m.ThresholdBand.STRICT),
            (0.5, m.ThresholdBand.HIGH),
            (0.7499, m.ThresholdBand.HIGH),
            (0.1, m.ThresholdBand.NORMAL),
            (0.25, m.ThresholdBand.NORMAL),
            (0.4999, m.ThresholdBand.NORMAL),
            (0.0001, m.ThresholdBand.LOW),
            (0.0999, m.ThresholdBand.LOW),
        ],
    )
    def test_the_seven_bands(self, value, band):
        assert m.threshold_band(value) is band

    @pytest.mark.parametrize("value", [-0.1, 0.0, 1.0, 1.01])
    def test_hard_error_bands(self, value):
        with pytest.raises(OpticaConfigError):
            m.check_clip_threshold(value, command="fetch")

    def test_the_zero_message_on_fetch_matches_the_plan(self):
        with pytest.raises(OpticaConfigError) as info:
            m.check_clip_threshold(0.0, command="fetch")
        err = info.value
        assert err.message == "--clip-threshold 0.0 disables CLIP filtering entirely."
        assert err.why == "clip mode requires a threshold greater than 0.0."
        assert err.fix == ["To skip filtering, use --mode curate instead."]

    def test_on_run_the_zero_message_also_offers_label(self):
        with pytest.raises(OpticaConfigError) as info:
            m.check_clip_threshold(0.0, command="run")
        assert "--mode label" in info.value.fix[0]

    def test_strict_end_is_a_prompt(self):
        check = m.check_clip_threshold(0.8, command="fetch")
        assert check.prompt is not None
        assert check.warning is None

    @pytest.mark.parametrize("value", [0.05, 0.6])
    def test_warn_and_continue_bands(self, value):
        check = m.check_clip_threshold(value, command="fetch")
        assert check.warning is not None
        assert check.prompt is None

    def test_normal_band_is_silent(self):
        check = m.check_clip_threshold(0.25, command="fetch")
        assert check.warning is None
        assert check.prompt is None


class TestClipExtraEntryCheck:
    def test_missing_extra_raises_the_capability_message(self, monkeypatch):
        monkeypatch.setattr(m, "clip_available", lambda: False)
        with pytest.raises(OpticaCLIPError) as info:
            m.require_clip_extra()
        assert info.value.message == (
            "CLIP filtering requires the clip extra. "
            "Run: optica setup --include-extras clip or pip install optica[clip]"
        )

    def test_present_extra_passes(self, monkeypatch):
        monkeypatch.setattr(m, "clip_available", lambda: True)
        m.require_clip_extra()


class TestSoftCap:
    def test_warns_only_above_the_cap(self):
        assert not m.soft_cap_exceeded(500, 500)
        assert m.soft_cap_exceeded(501, 500)


class TestMissingClassesError:
    def test_fetch_message_matches_the_plan(self):
        err = m.missing_classes_error("fetch")
        assert err.message == "--classes is required for fetch — nothing to search for."
        assert err.fix == ["Example: optica fetch --classes cat,dog"]


def _staging_fixture(home: Path) -> None:
    root = home / ".optica" / "staging"
    (root / "cat").mkdir(parents=True)
    (root / "cat" / "0001.jpg").write_bytes(b"x")
    (root / "dog.partial").mkdir()
    (root / "curation.json").write_text(json.dumps({"version": 1}), encoding="utf-8")
    labeling = root / "labeling"
    labeling.mkdir()
    (labeling / "good.json").write_text(
        json.dumps(
            {
                "version": 1,
                "source": "/home/u/images",
                "source_type": "folder",
                "classes": ["cat", "dog"],
                "entries": {"/home/u/images/a.jpg": {"state": "labeled", "class": "cat"}},
            }
        ),
        encoding="utf-8",
    )
    (labeling / "bad.json").write_text("{", encoding="utf-8")


class TestClearStaging:
    def test_lists_all_three_staging_shapes(self, tmp_path):
        _staging_fixture(tmp_path)
        listing = m.list_staging(tmp_path)
        assert [(s.name, s.partial) for s in listing.fetched] == [
            ("cat", False),
            ("dog", True),
        ]
        assert listing.curation is not None
        sources = {entry.source for entry in listing.labeling}
        assert sources == {"/home/u/images", None}
        text = "\n".join(listing.lines)
        assert "cat — 1 images" in text
        assert "incomplete fetch" in text
        assert "Curation session" in text
        assert "/home/u/images — 1 images labeled" in text
        # An unreadable session is listed, so it can be cleared.
        assert "(unreadable)" in text

    def test_clears_everything_and_keeps_the_staging_directory(self, tmp_path):
        _staging_fixture(tmp_path)
        m.clear_staging(tmp_path)
        root = tmp_path / ".optica" / "staging"
        assert root.is_dir()
        assert list(root.iterdir()) == []
        assert m.list_staging(tmp_path).empty

    def test_nothing_staged(self, tmp_path):
        assert m.list_staging(tmp_path).empty
