"""Training and evaluation transforms.

Covers plan § "Training" → *Input resolution and normalization*: evaluation
resizes to ``input_size / crop_pct`` at the backbone's interpolation and
centre-crops to ``input_size``; augmentation replaces the centre crop with a
random one. The resize arithmetic runs in CI; the transforms themselves are
``slow`` and are checked against timm's own evaluation transform.
"""

from __future__ import annotations

from typing import Any

import pytest

from optica.training.models import DataConfig
from optica.training.transforms import resize_size


def _config(size: int, crop_pct: float) -> DataConfig:
    return DataConfig(
        (3, size, size),
        (0.485, 0.456, 0.406),
        (0.229, 0.224, 0.225),
        "bicubic",
        crop_pct,
        "center",
    )


class TestResizeSize:
    @pytest.mark.parametrize(
        ("size", "crop_pct", "expected"),
        [
            (224, 0.875, 256),  # efficientnet_b0, mobilenetv3_large_100
            (224, 0.95, 235),  # resnet50 — crop_pct genuinely differs
            (320, 0.875, 365),  # efficientnet_b4
        ],
    )
    def test_floor_of_input_over_crop_pct(self, size, crop_pct, expected):
        assert resize_size(_config(size, crop_pct)) == expected


@pytest.mark.slow
class TestTransforms:
    @pytest.mark.parametrize("name", ["efficientnet_b0", "resnet50", "efficientnet_b4"])
    def test_evaluation_matches_timms_own_eval_transform(self, name, timm_model):
        import timm
        import torch
        from PIL import Image

        from optica.training.models import resolve_data_config
        from optica.training.transforms import build_transforms

        model = timm_model(name)
        config = resolve_data_config(model)
        _, ours = build_transforms(config, augmentation=True)
        data: Any = timm.data  # partially typed; these two are not re-exported
        theirs = data.create_transform(
            **data.resolve_model_data_config(model), is_training=False
        )
        generator = torch.Generator().manual_seed(1)
        pixels = (torch.rand(3, 300, 420, generator=generator) * 255).byte()
        image = Image.fromarray(pixels.permute(1, 2, 0).numpy())
        a, b = ours(image), theirs(image)
        assert a.shape == (3, config.input_size[1], config.input_size[2])
        assert torch.allclose(a, b, atol=1e-6)

    def test_augmentation_is_random_and_evaluation_is_not(self):
        import torch
        from PIL import Image

        from optica.training.transforms import build_transforms

        train, evaluation = build_transforms(_config(64, 0.875), augmentation=True)
        pixels = (
            torch.rand(3, 90, 120, generator=torch.Generator().manual_seed(2)) * 255
        ).byte()
        image = Image.fromarray(pixels.permute(1, 2, 0).numpy())
        torch.manual_seed(0)
        outputs = [train(image) for _ in range(4)]
        assert all(o.shape == (3, 64, 64) for o in outputs)
        assert not all(torch.equal(outputs[0], o) for o in outputs[1:])
        assert torch.equal(evaluation(image), evaluation(image))

    def test_without_augmentation_training_uses_the_evaluation_transform(self):
        from optica.training.transforms import build_transforms

        train, evaluation = build_transforms(_config(64, 0.875), augmentation=False)
        assert train is evaluation
