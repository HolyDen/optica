"""Train / validation / test splitting.

Implements plan § "Training" → *Dataset splitting* and the ``training_data_hash``
serialisation in *``checkpoint_info.json``*.

**Stratified per class, never a random split of the pooled dataset.** Per class
of *n* images, in this order::

    n_val   = max(1, floor(n x val_split))
    n_test  = min(floor(n x test_split), n - n_val - 1)
    n_train = n - n_val - n_test

Every class keeps at least one training and one validation image; the remainder
biases toward training. ``train_split`` takes part only through the sum rule
that config load already enforces — the formula never reads it.

**Floor with a tolerance.** ``floor(n x ratio)`` on binary floats undercounts
whenever the product lands a hair below an integer — ``100 x 0.29`` is
``28.999999999999996``. The plan states exact arithmetic, so products within
``1e-9`` of the integer above count as that integer (``notes/build-log.md``).

**Assignment** uses scikit-learn's ``train_test_split`` (plan § "Tech Stack"),
called per class with **integer** sizes, so the counts are exactly the formula's
and ``random_state`` alone decides which files land where. The arithmetic here is
torch- and sklearn-free and runs in CI; the assignment imports sklearn lazily.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from optica.exceptions import OpticaTorchError

__all__ = [
    "ClassSplit",
    "DatasetSplit",
    "exact_floor",
    "split_counts",
    "stratified_split",
    "training_data_hash",
]

_FLOOR_TOLERANCE: Final = 1e-9


def exact_floor(value: float) -> int:
    """``floor(value)``, treating a product a float-error below an integer as it."""
    return math.floor(value + _FLOOR_TOLERANCE)


def split_counts(n: int, val_split: float, test_split: float) -> tuple[int, int, int]:
    """``(n_train, n_val, n_test)`` for one class of ``n`` images.

    Worked, from the plan: 5 → 4/1/0; 20 → 14/3/3; 100 → 70/15/15.

    Raises:
        ValueError: Below two images, where no split keeps a training and a
            validation image. The five-image floor makes this unreachable from
            the CLI; the guard is for direct callers.
    """
    if n < 2:
        raise ValueError(f"a class needs at least 2 images to split, got {n}")
    n_val = max(1, exact_floor(n * val_split))
    n_test = min(exact_floor(n * test_split), n - n_val - 1)
    n_test = max(0, n_test)
    return n - n_val - n_test, n_val, n_test


@dataclass
class ClassSplit:
    """One class's files, split.

    Attributes:
        train: Training files.
        val: Validation files.
        test: Test files — may be empty for a small class.
    """

    train: list[Path] = field(default_factory=list)
    val: list[Path] = field(default_factory=list)
    test: list[Path] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        """``{"train": …, "val": …, "test": …}`` — the log's per-class record."""
        return {"train": len(self.train), "val": len(self.val), "test": len(self.test)}


@dataclass
class DatasetSplit:
    """The whole dataset, split per class.

    Attributes:
        classes: Class name to its split, in sorted class order.
        random_state: The seed that produced it.
    """

    classes: dict[str, ClassSplit]
    random_state: int

    def items(self, part: str) -> list[tuple[Path, int]]:
        """``(file, class index)`` pairs for ``train``, ``val`` or ``test``.

        Class indices follow sorted class order — the model's output order.
        """
        return [
            (path, index)
            for index, split in enumerate(self.classes.values())
            for path in getattr(split, part)
        ]

    @property
    def classes_without_test(self) -> list[str]:
        """Classes whose split left no test image."""
        return [name for name, split in self.classes.items() if not split.test]

    def train_counts(self) -> list[int]:
        """Training images per class, index-aligned with the classes."""
        return [len(split.train) for split in self.classes.values()]


def stratified_split(
    files: Mapping[str, Sequence[Path]],
    val_split: float,
    test_split: float,
    random_state: int,
) -> DatasetSplit:
    """Split each class by :func:`split_counts`, assigned by ``train_test_split``.

    Args:
        files: Class name to its files. Classes are taken in sorted order and
            each class's files in sorted path order before shuffling, so the
            result depends on ``random_state`` and the file set only.
        val_split: The validation ratio.
        test_split: The test ratio.
        random_state: The run's seed, saved with every checkpoint.

    Raises:
        OpticaTorchError: scikit-learn is not installed.
    """
    try:
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        raise OpticaTorchError() from exc

    result: dict[str, ClassSplit] = {}
    for name in sorted(files):
        ordered = sorted(files[name])
        n_train, n_val, n_test = split_counts(len(ordered), val_split, test_split)
        train, held = train_test_split(
            ordered,
            train_size=n_train,
            test_size=n_val + n_test,
            random_state=random_state,
            shuffle=True,
        )
        if n_test:
            val, test = train_test_split(
                held,
                train_size=n_val,
                test_size=n_test,
                random_state=random_state,
                shuffle=True,
            )
        else:
            val, test = list(held), []
        result[name] = ClassSplit(list(train), list(val), list(test))
    return DatasetSplit(result, random_state)


def training_data_hash(root: Path) -> str:
    r"""MD5 of the dataset's **structure**, never its contents.

    The plan's exact serialisation: the UTF-8 sorted relative paths of every
    file under ``root``, one per line, ``\\n``-joined, no trailing newline. The
    root's own name is excluded, so relocating a dataset keeps its hash. Paths
    are written with ``/`` on every platform — otherwise the same dataset would
    hash differently on Windows (``notes/build-log.md``).
    """
    paths = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    return hashlib.md5(
        "\n".join(paths).encode("utf-8"), usedforsecurity=False
    ).hexdigest()
