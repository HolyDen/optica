"""Datasets and loaders over a split.

Not in plan § "Code Structure"'s tree; added in pass 4 (``notes/build-log.md``).

**Why not ``ImageFolder`` itself.** Training reads ``--dataset`` in place and
must leave out what pre-flight and deduplication excluded without touching the
user's folder, so the loader works from the resolved file list. The class order
is still ``ImageFolder``'s — class folder names, sorted — which is the model's
output-index order and the order ``checkpoint_info.json`` records.

**A file that fails to decode here** is one header-only pre-flight let through —
a truncated JPEG can pass it (``notes/build-log.md``, pass 3). It raises
:class:`~optica.exceptions.OpticaTrainingError` naming the file rather than a
Pillow traceback from inside the loader; the file is left untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from optica.exceptions import OpticaTrainingError
from optica.training.splits import DatasetSplit
from optica.utils.mlstack import import_torch_stack

if TYPE_CHECKING:
    import torch

__all__ = ["NUM_WORKERS", "ImageListDataset", "make_loaders"]

NUM_WORKERS: Final = 0
"""Loading happens in the training process. Worker processes on Windows re-import
the entry point under spawn; V1 keeps the one path that behaves identically on all
three platforms (``notes/build-log.md``)."""


class ImageListDataset:
    """``(image, class index)`` pairs from an explicit file list."""

    def __init__(
        self, items: Sequence[tuple[Path, int]], transform: Callable[[Any], Any]
    ) -> None:
        self.items = list(items)
        self.transform = transform

    def __len__(self) -> int:
        """Images in the list."""
        return len(self.items)

    def __getitem__(self, index: int) -> tuple[Any, int]:
        """The transformed image and its class index."""
        from PIL import Image

        path, label = self.items[index]
        try:
            with Image.open(path) as image:
                rgb = image.convert("RGB")
        except (OSError, ValueError, SyntaxError) as exc:
            raise OpticaTrainingError(
                f"{path} could not be decoded during training.",
                why=f"{type(exc).__name__}: {exc}. Pre-flight reads image headers, "
                "and some damaged files pass it.",
                fix="Remove or replace that file, then run again. Optica has not "
                "changed it.",
            ) from exc
        return self.transform(rgb), label


def make_loaders(
    split: DatasetSplit,
    train_transform: Callable[[Any], Any],
    eval_transform: Callable[[Any], Any],
    *,
    batch_size: int,
    device: torch.device,
    seed: int,
) -> tuple[Any, Any, Any]:
    """``(train, val, test)`` loaders. Only training shuffles, seeded by the run."""
    import_torch_stack()
    import torch

    generator = torch.Generator()
    generator.manual_seed(seed)
    pin = device.type == "cuda"

    def loader(part: str, transform: Callable[[Any], Any], shuffle: bool) -> Any:
        # Map-style by protocol (__len__/__getitem__) rather than by subclassing
        # torch's Dataset, which would import torch with this module.
        dataset: Any = ImageListDataset(split.items(part), transform)
        return torch.utils.data.DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=NUM_WORKERS,
            pin_memory=pin,
            generator=generator if shuffle else None,
        )

    return (
        loader("train", train_transform, True),
        loader("val", eval_transform, False),
        loader("test", eval_transform, False),
    )
