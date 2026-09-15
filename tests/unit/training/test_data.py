"""Datasets and loaders over a split.

Covers plan § "Training" → *Training Engine* step 1 (``ImageFolder`` class
order — sorted folder names — as output-index order) and the pass-3 handoff that
a truncated image can pass header-only pre-flight and must fail cleanly at
training rather than as a loader traceback.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from optica.exceptions import OpticaTrainingError

pytestmark = pytest.mark.slow


def _noisy_jpeg(size: int = 300) -> bytes:
    # A noisy image: pre-flight's header check passes it when cut in half
    # (notes/build-log.md, pass 3 — a flat image would be caught earlier).
    import torch
    from PIL import Image

    pixels = (
        torch.rand(size, size, 3, generator=torch.Generator().manual_seed(5)) * 255
    ).byte()
    buffer = io.BytesIO()
    Image.fromarray(pixels.numpy()).save(buffer, "JPEG")
    return buffer.getvalue()


class TestImageListDataset:
    def test_a_truncated_image_is_a_training_error_naming_the_file(self, tmp_path):
        from optica.input.validation import inspect_in_place
        from optica.training.data import ImageListDataset

        data = _noisy_jpeg()
        path = tmp_path / "broken.jpg"
        path.write_bytes(data[: len(data) // 2])
        assert inspect_in_place(path).readable  # control: pre-flight lets it through
        dataset = ImageListDataset([(path, 0)], transform=lambda image: image)
        with pytest.raises(OpticaTrainingError) as info:
            dataset[0]
        assert str(path) in info.value.message
        assert path.read_bytes() == data[: len(data) // 2]  # untouched

    def test_items_become_transformed_images_and_labels(self, image_dataset):
        from optica.training.data import ImageListDataset

        root = image_dataset({"cat": 1})
        path = next((root / "cat").iterdir())
        dataset = ImageListDataset([(path, 3)], transform=lambda image: image.size)
        assert len(dataset) == 1
        assert dataset[0] == ((64, 64), 3)


class TestLoaders:
    def test_only_training_shuffles_and_the_seed_fixes_its_order(self, image_dataset):
        import torch

        from optica.training.data import make_loaders
        from optica.training.splits import stratified_split

        root = image_dataset({"cat": 20, "dog": 20})
        files = {name: sorted((root / name).iterdir()) for name in ("cat", "dog")}
        split = stratified_split(files, 0.15, 0.15, 11)

        def to_tensor(image):
            return torch.tensor(image.getpixel((0, 0)), dtype=torch.float32)

        def labels(loader: Any) -> list[int]:
            return [int(t) for _, targets in loader for t in targets]

        cpu = torch.device("cpu")
        train1, val1, _ = make_loaders(
            split, to_tensor, to_tensor, batch_size=4, device=cpu, seed=3
        )
        train2, _, _ = make_loaders(
            split, to_tensor, to_tensor, batch_size=4, device=cpu, seed=3
        )
        assert labels(train1) == labels(train2)
        expected_val = [label for _, label in split.items("val")]
        assert labels(val1) == expected_val  # unshuffled, in split order
        assert labels(train1) != sorted(labels(train1))  # shuffled
