"""Train / validation / test splitting, and the structure hash.

Covers plan § "Training" → *Dataset splitting* (the per-class formula and its
worked values 5 → 4/1/0, 20 → 14/3/3, 100 → 70/15/15) and *``checkpoint_info.json``*
→ ``training_data_hash`` (the exact serialisation). The arithmetic and the hash
run in CI; the scikit-learn assignment is ``slow``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from optica.training import splits


class TestSplitCounts:
    @pytest.mark.parametrize(
        ("n", "expected"),
        [(5, (4, 1, 0)), (20, (14, 3, 3)), (100, (70, 15, 15))],
    )
    def test_the_plans_worked_values(self, n, expected):
        assert splits.split_counts(n, 0.15, 0.15) == expected

    @pytest.mark.parametrize("n", range(2, 200))
    def test_every_class_keeps_a_training_and_a_validation_image(self, n):
        n_train, n_val, n_test = splits.split_counts(n, 0.15, 0.15)
        assert n_train >= 1
        assert n_val >= 1
        assert n_test >= 0
        assert n_train + n_val + n_test == n

    def test_validation_is_allocated_before_test(self):
        # n = 2: n_val = max(1, 0) = 1; n_test = min(0, 2 - 1 - 1) = 0.
        assert splits.split_counts(2, 0.15, 0.15) == (1, 1, 0)
        # n = 3 with a large test ratio: the cap n - n_val - 1 binds.
        assert splits.split_counts(3, 0.15, 0.9) == (1, 1, 1)

    def test_a_product_a_float_error_below_an_integer_floors_to_it(self):
        # 100 x 0.29 is 28.999999999999996 in binary floating point.
        assert 100 * 0.29 < 29
        assert splits.split_counts(100, 0.29, 0.0) == (71, 29, 0)

    def test_the_tolerance_does_not_round_up_real_fractions(self):
        assert splits.exact_floor(28.9) == 28
        assert splits.exact_floor(28.999999) == 28

    def test_fewer_than_two_images_cannot_split(self):
        with pytest.raises(ValueError):
            splits.split_counts(1, 0.15, 0.15)


class TestTrainingDataHash:
    def _tree(self, root: Path, files: list[str]) -> Path:
        for relative in files:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        return root

    def test_the_exact_serialisation(self, tmp_path):
        root = self._tree(tmp_path / "ds", ["dog/b.png", "cat/a.png", "cat/c.png"])
        expected = hashlib.md5(b"cat/a.png\ncat/c.png\ndog/b.png").hexdigest()
        assert splits.training_data_hash(root) == expected

    def test_contents_do_not_change_it(self, tmp_path):
        root = self._tree(tmp_path / "ds", ["cat/a.png", "dog/b.png"])
        before = splits.training_data_hash(root)
        (root / "cat" / "a.png").write_bytes(b"different bytes entirely")
        assert splits.training_data_hash(root) == before

    def test_relocating_the_root_does_not_change_it(self, tmp_path):
        a = self._tree(tmp_path / "one", ["cat/a.png", "dog/b.png"])
        b = self._tree(tmp_path / "elsewhere" / "two", ["cat/a.png", "dog/b.png"])
        assert splits.training_data_hash(a) == splits.training_data_hash(b)

    def test_adding_a_file_changes_it(self, tmp_path):
        root = self._tree(tmp_path / "ds", ["cat/a.png", "dog/b.png"])
        before = splits.training_data_hash(root)
        self._tree(root, ["dog/c.png"])
        assert splits.training_data_hash(root) != before

    def test_separators_are_forward_slashes_on_every_platform(self, tmp_path):
        root = self._tree(tmp_path / "ds", ["cat/a.png"])
        # Constructed rather than inherited: the expected digest is the POSIX
        # form, whatever os.sep is on the machine running this.
        assert splits.training_data_hash(root) == hashlib.md5(b"cat/a.png").hexdigest()


@pytest.mark.slow
class TestStratifiedSplit:
    def _files(self, counts: dict[str, int]) -> dict[str, list[Path]]:
        return {
            name: [Path(f"/data/{name}/{i:04d}.png") for i in range(n)]
            for name, n in counts.items()
        }

    def test_counts_follow_the_formula_per_class(self):
        result = splits.stratified_split(
            self._files({"cat": 20, "dog": 5}), 0.15, 0.15, 7
        )
        assert result.classes["cat"].counts == {"train": 14, "val": 3, "test": 3}
        assert result.classes["dog"].counts == {"train": 4, "val": 1, "test": 0}
        assert result.classes_without_test == ["dog"]

    def test_the_same_random_state_gives_the_same_split(self):
        files = self._files({"cat": 30, "dog": 30})
        a = splits.stratified_split(files, 0.15, 0.15, 1234)
        b = splits.stratified_split(files, 0.15, 0.15, 1234)
        assert a.classes == b.classes

    def test_a_different_random_state_gives_a_different_split(self):
        files = self._files({"cat": 30, "dog": 30})
        a = splits.stratified_split(files, 0.15, 0.15, 1)
        b = splits.stratified_split(files, 0.15, 0.15, 2)
        assert a.classes != b.classes

    def test_input_order_does_not_matter(self):
        files = self._files({"cat": 30, "dog": 30})
        shuffled = {
            name: list(reversed(paths)) for name, paths in reversed(files.items())
        }
        assert (
            splits.stratified_split(files, 0.15, 0.15, 9).classes
            == splits.stratified_split(shuffled, 0.15, 0.15, 9).classes
        )

    def test_parts_are_disjoint_and_complete(self):
        files = self._files({"cat": 23})
        split = splits.stratified_split(files, 0.15, 0.15, 3).classes["cat"]
        together = split.train + split.val + split.test
        assert sorted(together) == sorted(files["cat"])
        assert len(set(together)) == len(together)

    def test_class_indices_follow_sorted_class_order(self):
        result = splits.stratified_split(self._files({"dog": 5, "cat": 5}), 0.15, 0.15, 0)
        assert list(result.classes) == ["cat", "dog"]
        labels = {Path(p).parent.name: label for p, label in result.items("train")}
        assert labels == {"cat": 0, "dog": 1}
