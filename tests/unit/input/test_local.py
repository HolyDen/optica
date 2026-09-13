"""The Local Adapter.

Covers plan § "Input & Acquisition" → *Label mode — detection order* (the
``--folder``/``--dataset`` shape errors), *``--manifest``* (format, columns,
path semantics, URLs, duplicates and contradictions, mixed manifests,
materialization, filename collisions), *Unreadable images — pre-flight
verification* (dispositions for user-provided files, zero readable aborts), and
Known Constraints (``dataset/`` reserved, nested subfolders, copy never move).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from optica.exceptions import OpticaValidationError
from optica.input import local


def _jpeg(color="red", size=(160, 160)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "JPEG")
    return buffer.getvalue()


def _bmp(color="blue", size=(160, 160)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "BMP")
    return buffer.getvalue()


def _dataset(root: Path, spec: dict[str, int]) -> Path:
    for name, count in spec.items():
        folder = root / name
        folder.mkdir(parents=True)
        for i in range(count):
            (folder / f"{i}.jpg").write_bytes(_jpeg(size=(160 + i, 160)))
    return root


class TestFolderShapes:
    def test_organized_via_folder_names_the_subfolders(self, tmp_path):
        images = _dataset(tmp_path / "images", {"cat": 1, "dog": 1, "bird": 1})
        with pytest.raises(OpticaValidationError) as info:
            local.require_flat_folder(images)
        err = info.value
        assert "appears to already be organized into subfolders: bird/, cat/, dog/" in (
            err.message
        )
        assert err.why == "--folder expects a flat folder of unlabeled images."
        assert err.fix[-1] == f"optica train --dataset {images}"

    def test_flat_folder_lists_files_and_skips_litter(self, tmp_path):
        folder = tmp_path / "flat"
        folder.mkdir()
        (folder / "b.jpg").write_bytes(_jpeg())
        (folder / "a.jpg").write_bytes(_jpeg())
        (folder / ".hidden.jpg").write_bytes(_jpeg())
        (folder / "Thumbs.db").write_bytes(b"x")
        assert [p.name for p in local.require_flat_folder(folder)] == ["a.jpg", "b.jpg"]

    def test_missing_folder_is_an_error_naming_the_path(self, tmp_path):
        with pytest.raises(OpticaValidationError, match="No folder found"):
            local.require_flat_folder(tmp_path / "nope")

    def test_flat_folder_given_as_dataset_is_an_error(self, tmp_path):
        folder = tmp_path / "flat"
        folder.mkdir()
        (folder / "a.jpg").write_bytes(_jpeg())
        with pytest.raises(OpticaValidationError, match="flat folder, not an organized"):
            local.load_organized_dataset(folder)

    def test_loose_images_in_dataset_are_an_error(self, tmp_path):
        root = _dataset(tmp_path / "dataset", {"cat": 5, "dog": 5})
        (root / "stray.jpg").write_bytes(_jpeg())
        with pytest.raises(OpticaValidationError, match="Loose files"):
            local.load_organized_dataset(root)

    def test_nested_subfolders_list_both_resolutions(self, tmp_path):
        root = _dataset(tmp_path / "dataset", {"cat": 1, "dog": 1})
        (root / "cat" / "outdoor").mkdir()
        (root / "cat" / "indoor").mkdir()
        with pytest.raises(OpticaValidationError) as info:
            local.load_organized_dataset(root)
        err = info.value
        assert err.message == (
            "Nested subfolders found inside class 'cat' (indoor/, outdoor/) — "
            "unsupported."
        )
        joined = "\n".join(err.fix)
        assert "Flatten" in joined
        assert "Separate" in joined
        assert "cat_outdoor" in joined
        assert "cat_indoor" in joined

    def test_one_class_folder_is_below_the_minimum(self, tmp_path):
        root = _dataset(tmp_path / "dataset", {"cat": 5})
        with pytest.raises(OpticaValidationError, match="fewer than 2 classes"):
            local.load_organized_dataset(root)

    def test_empty_dataset_folder(self, tmp_path):
        root = tmp_path / "dataset"
        root.mkdir()
        with pytest.raises(OpticaValidationError, match="No dataset found"):
            local.load_organized_dataset(root)

    def test_valid_dataset(self, tmp_path):
        root = _dataset(tmp_path / "dataset", {"dog": 3, "cat": 2})
        dataset = local.load_organized_dataset(root)
        assert list(dataset.classes) == ["cat", "dog"]
        assert dataset.counts == {"cat": 2, "dog": 3}


class TestPreflight:
    def test_unreadable_are_dropped_and_listed_files_untouched(self, tmp_path):
        good = tmp_path / "good.jpg"
        bad = tmp_path / "bad.jpg"
        good.write_bytes(_jpeg())
        bad.write_bytes(b"")
        readable, unreadable = local.preflight([good, bad])
        assert readable == [good]
        assert [r.path for r in unreadable] == [bad]
        assert bad.exists()

    def test_zero_readable_aborts(self, tmp_path):
        bad = tmp_path / "bad.jpg"
        bad.write_text("nope", encoding="utf-8")
        with pytest.raises(OpticaValidationError, match="None of the 1 files"):
            local.preflight([bad])


def _write_csv(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class TestManifestFormat:
    def test_other_extension_is_a_hard_error_naming_both(self, tmp_path):
        path = tmp_path / "m.txt"
        path.write_text("path\n", encoding="utf-8")
        with pytest.raises(OpticaValidationError) as info:
            local.parse_manifest(path)
        assert ".csv" in info.value.message
        assert ".json" in info.value.message

    def test_missing_path_column_reports_what_the_header_held(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "file,label\na.jpg,cat\n")
        with pytest.raises(OpticaValidationError) as info:
            local.parse_manifest(path)
        assert info.value.message == "Manifest is missing the 'path' column."
        assert "The first row was read as the header. Found: file, label" in (
            info.value.why or ""
        )

    def test_missing_class_column_matches_the_plan_example(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path,label\na.jpg,cat\n")
        manifest = local.parse_manifest(path)
        with pytest.raises(OpticaValidationError) as info:
            manifest.require_fully_labeled()
        assert info.value.message == "Manifest is missing the 'class' column."
        assert info.value.why == (
            "The first row was read as the header. Found: path, label — rename the "
            "intended column to 'class' and try again."
        )

    def test_a_headerless_file_fails_the_path_check_like_any_other(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "a.jpg,cat\nb.jpg,dog\n")
        with pytest.raises(OpticaValidationError, match="'path' column"):
            local.parse_manifest(path)

    def test_columns_match_case_insensitively_and_trimmed(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", " PATH , Class ,extra\na.jpg,cat,1\n")
        manifest = local.parse_manifest(path)
        assert manifest.rows[0].class_name == "cat"
        assert manifest.has_class_column

    def test_extra_columns_are_ignored_not_rejected(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "id,path,class,score\n1,a.jpg,cat,0.9\n")
        assert len(local.parse_manifest(path).rows) == 1

    def test_json_array_of_objects(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(
            json.dumps([{"path": "a.jpg", "class": "cat"}, {"Path": "b.jpg"}]),
            encoding="utf-8",
        )
        manifest = local.parse_manifest(path)
        assert [r.class_name for r in manifest.rows] == ["cat", None]

    def test_json_not_an_array(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"path": "a.jpg"}), encoding="utf-8")
        with pytest.raises(OpticaValidationError, match="array of objects"):
            local.parse_manifest(path)


class TestManifestPaths:
    def test_relative_paths_resolve_against_the_manifest_directory(
        self, tmp_path, monkeypatch
    ):
        sub = tmp_path / "data"
        sub.mkdir()
        path = _write_csv(sub / "m.csv", "path,class\nimg/a.jpg,cat\n")
        monkeypatch.chdir(tmp_path)
        assert (
            local.parse_manifest(path).rows[0].path == (sub / "img" / "a.jpg").resolve()
        )

    @pytest.mark.parametrize("url", ["https://example.com/a.jpg", "s3://bucket/a.jpg"])
    def test_a_url_row_is_unsupported_not_invalid(self, tmp_path, url):
        path = _write_csv(tmp_path / "m.csv", f"path,class\na.jpg,cat\n{url},dog\n")
        with pytest.raises(OpticaValidationError) as info:
            local.parse_manifest(path)
        assert "not supported" in info.value.message
        assert "rows 2" in info.value.message

    def test_a_windows_drive_path_is_not_a_url(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path,class\nC:/images/a.jpg,cat\n")
        assert local.parse_manifest(path).rows

    def test_exact_duplicates_dedupe_across_spellings(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path,class\n./a.jpg,cat\na.jpg,cat\n")
        manifest = local.parse_manifest(path)
        assert len(manifest.rows) == 1
        assert manifest.duplicates_removed == 1

    def test_contradictory_rows_are_a_hard_error_naming_both(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path,class\na.jpg,cat\n./a.jpg,dog\n")
        with pytest.raises(OpticaValidationError) as info:
            local.parse_manifest(path)
        line = info.value.fix[0]
        assert "rows 1 and 2" in line
        assert "cat" in line
        assert "dog" in line

    def test_class_names_go_through_the_rules(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path,class\na.jpg,cat\nb.jpg,Cat\n")
        with pytest.raises(OpticaValidationError, match="class column"):
            local.parse_manifest(path)

    def test_content_hash_changes_with_content(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path\na.jpg\n")
        first = local.parse_manifest(path).content_hash
        _write_csv(path, "path\nb.jpg\n")
        assert local.parse_manifest(path).content_hash != first


class TestManifestLabelStates:
    def test_mixed_is_a_hard_error_naming_rows(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path,class\na.jpg,cat\nb.jpg,\nc.jpg,\n")
        manifest = local.parse_manifest(path)
        assert manifest.label_state is local.LabelState.MIXED
        with pytest.raises(OpticaValidationError) as info:
            manifest.require_consistent()
        assert "2, 3" in (info.value.why or "")

    def test_fully_labeled_manifest_to_label_is_a_hard_error(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path,class\na.jpg,cat\nb.jpg,dog\n")
        with pytest.raises(OpticaValidationError, match="already fully labeled"):
            local.parse_manifest(path).require_unlabeled_for_label()

    def test_unlabeled_manifest_is_fine_for_label(self, tmp_path):
        path = _write_csv(tmp_path / "m.csv", "path\na.jpg\nb.jpg\n")
        manifest = local.parse_manifest(path)
        assert manifest.label_state is local.LabelState.NONE
        manifest.require_unlabeled_for_label()


class TestCopyIntoDataset:
    def test_originals_untouched_and_counts_reported(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        a = src / "a.jpg"
        a.write_bytes(_jpeg("red"))
        before = a.read_bytes()
        report = local.copy_into_dataset([(a, "cat")], tmp_path / "dataset")
        assert a.read_bytes() == before
        assert (tmp_path / "dataset" / "cat" / "a.jpg").read_bytes() == before
        assert report.copied == {"cat": 1}
        assert report.total == 1

    def test_same_basename_from_two_directories_suffixes_in_row_order(self, tmp_path):
        for sub, color in (("a", "red"), ("b", "green"), ("c", "blue")):
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "img.jpg").write_bytes(_jpeg(color))
        items = [(tmp_path / sub / "img.jpg", "cat") for sub in ("a", "b", "c")]
        report = local.copy_into_dataset(items, tmp_path / "dataset")
        names = sorted(p.name for p in (tmp_path / "dataset" / "cat").iterdir())
        assert names == ["img.jpg", "img_2.jpg", "img_3.jpg"]
        assert report.renamed == 2

    def test_collisions_run_on_post_conversion_names(self, tmp_path):
        folder = tmp_path / "flat"
        folder.mkdir()
        (folder / "photo.bmp").write_bytes(_bmp("blue"))
        (folder / "photo.jpg").write_bytes(_jpeg("red"))
        items = [(folder / "photo.bmp", "cat"), (folder / "photo.jpg", "cat")]
        report = local.copy_into_dataset(items, tmp_path / "dataset")
        names = sorted(p.name for p in (tmp_path / "dataset" / "cat").iterdir())
        # The BMP is written as .jpg, never as .bmp holding JPEG bytes.
        assert names == ["photo.jpg", "photo_2.jpg"]
        assert report.converted == 1
        assert report.renamed == 1
        assert (folder / "photo.bmp").exists()

    def test_byte_identical_within_a_class_is_excluded(self, tmp_path):
        (tmp_path / "x").mkdir()
        (tmp_path / "y").mkdir()
        data = _jpeg("red")
        (tmp_path / "x" / "one.jpg").write_bytes(data)
        (tmp_path / "y" / "two.jpg").write_bytes(data)
        items = [(tmp_path / "x" / "one.jpg", "cat"), (tmp_path / "y" / "two.jpg", "cat")]
        report = local.copy_into_dataset(items, tmp_path / "dataset")
        assert report.copied == {"cat": 1}
        assert report.duplicates == {"cat": 1}

    def test_identical_bytes_in_two_classes_are_both_kept(self, tmp_path):
        data = _jpeg("red")
        (tmp_path / "one.jpg").write_bytes(data)
        items = [(tmp_path / "one.jpg", "cat"), (tmp_path / "one.jpg", "dog")]
        report = local.copy_into_dataset(items, tmp_path / "dataset")
        assert report.copied == {"cat": 1, "dog": 1}

    def test_undersized_copy_is_resized_and_reported(self, tmp_path):
        (tmp_path / "tiny.jpg").write_bytes(_jpeg(size=(64, 64)))
        report = local.copy_into_dataset([(tmp_path / "tiny.jpg", "cat")], tmp_path / "d")
        assert report.resized == 1
        with Image.open(tmp_path / "d" / "cat" / "tiny.jpg") as image:
            assert image.size == (128, 128)

    def test_unreadable_source_is_reported_not_raised(self, tmp_path):
        (tmp_path / "bad.jpg").write_bytes(b"")
        report = local.copy_into_dataset(
            [(tmp_path / "bad.jpg", "cat"), (tmp_path / "missing.jpg", "cat")],
            tmp_path / "d",
        )
        assert len(report.unreadable) == 2
        assert report.total == 0

    def test_copy_note_matches_the_plan_shape(self, tmp_path):
        files = []
        for i in range(3):
            path = tmp_path / f"{i}.bin"
            path.write_bytes(b"x" * 1500)
            files.append(path)
        note = local.copy_note(files, tmp_path / "dataset")
        assert note == "Copying 3 images (4.5 KB) to dataset/ — originals untouched"
