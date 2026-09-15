"""Training and evaluation transforms.

Implements plan § "Training" → *Input resolution and normalization* and the
augmentation line of *OOM handling* ("random flip, rotation ±15°, color jitter,
random crop").

**Evaluation** is the transform the exported model is used under, and the one
``usage_examples.md`` teaches: resize the shorter side to
``floor(input_size / crop_pct)`` at the backbone's interpolation, centre-crop to
``input_size``, normalise with the backbone's mean and std. A slow test checks it
against ``timm.data.create_transform(..., is_training=False)`` pixel for pixel.

**Training with augmentation** replaces the centre crop with a random one, as the
plan says, after the same resize — so a training crop frames the image the way an
evaluation crop does. Then a horizontal flip, a rotation within ±15°, and colour
jitter. The plan names the four operations and the rotation range only; the
flip probability (0.5) and jitter strengths (0.2 brightness, contrast and
saturation) are assumed (``notes/build-log.md``).

**Without augmentation** training uses the evaluation transform.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Final

from optica.training.models import DataConfig
from optica.utils.mlstack import import_torch_stack

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "COLOR_JITTER",
    "FLIP_PROBABILITY",
    "ROTATION_DEGREES",
    "build_transforms",
    "resize_size",
]

ROTATION_DEGREES: Final = 15
FLIP_PROBABILITY: Final = 0.5
COLOR_JITTER: Final = 0.2


def resize_size(config: DataConfig) -> int:
    """The shorter-side size evaluation resizes to before its centre crop.

    ``floor(input_size / crop_pct)`` — timm's own ``scale_size`` rule. For
    resnet50 (224, 0.95) that is 235; for the 0.875 backbones at 224, 256.
    """
    return math.floor(config.input_size[1] / config.crop_pct)


def build_transforms(
    config: DataConfig, *, augmentation: bool
) -> tuple[Callable[[Any], Any], Callable[[Any], Any]]:
    """``(train_transform, eval_transform)`` for one backbone's data config."""
    import_torch_stack()
    from torchvision import transforms as tv
    from torchvision.transforms import InterpolationMode

    interpolation = InterpolationMode(config.interpolation)
    size = config.input_size[1]
    normalise = [tv.ToTensor(), tv.Normalize(mean=config.mean, std=config.std)]
    evaluation = tv.Compose(
        [
            tv.Resize(resize_size(config), interpolation=interpolation),
            tv.CenterCrop(size),
            *normalise,
        ]
    )
    if not augmentation:
        return evaluation, evaluation
    training = tv.Compose(
        [
            tv.Resize(resize_size(config), interpolation=interpolation),
            tv.RandomCrop(size),
            tv.RandomHorizontalFlip(p=FLIP_PROBABILITY),
            tv.RandomRotation(ROTATION_DEGREES, interpolation=interpolation),
            tv.ColorJitter(
                brightness=COLOR_JITTER, contrast=COLOR_JITTER, saturation=COLOR_JITTER
            ),
            *normalise,
        ]
    )
    return training, evaluation
