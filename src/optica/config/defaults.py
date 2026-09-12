"""Built-in default values, and the domains every key is validated against.

Implements plan § "Configuration" → *Config keys (V1)* and *Numeric range
validation*. Every value here is transcribed from the plan's tables; nothing is
inferred.

All V1 config keys are **flat** — no nested keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "API_KEYS",
    "CONFIG_KEYS",
    "DEFAULTS",
    "DEFAULT_TASK",
    "KEY_HELP",
    "NUMERIC_DOMAINS",
    "Domain",
    "env_var_for",
]

DEFAULT_TASK: Final = "classify"
"""The task type Optica's flat CLI and API aliases resolve through.

**A module-level constant, not a config key.** With one task type a settable
value would have exactly one legal setting; it becomes a config key when a second
task ships, and adding one then is non-breaking, which is what makes the constant
safe now. Alias resolution consults this rather than hardcoding ``"classify"``,
so a post-V1 task slots in without restructuring the CLI.
"""

MODES: Final[tuple[str, ...]] = ("label", "curate", "clip")
SOURCES: Final[tuple[str, ...]] = ("flickr", "open-datasets")
MODELS: Final[tuple[str, ...]] = (
    "efficientnet-small",
    "efficientnet-large",
    "resnet",
    "resnet-50",
    "mobilenet",
    "mobilenet-large",
)
"""``resnet``/``resnet-50`` and ``mobilenet``/``mobilenet-large`` are alias
pairs — one model each, not four."""

OPTIMIZERS: Final[tuple[str, ...]] = ("adamw", "adam", "sgd")

DEFAULTS: Final[dict[str, Any]] = {
    "default_mode": "curate",
    "default_source": "open-datasets",
    "default_model": "efficientnet-small",
    "images_per_class": 50,
    "epochs": 10,
    "learning_rate": 0.001,
    "optimizer": "adamw",
    "batch_size": 32,
    "early_stopping": 5,
    "augmentation": True,
    "train_split": 0.70,
    "val_split": 0.15,
    "test_split": 0.15,
    "max_checkpoints": 3,
    "clip_threshold": 0.25,
    "finetune_ratio": 0.70,
    "max_open_datasets_per_class": 500,
    "curation_port": 8765,
    "curation_timeout_minutes": 60,
    "flickr_api_key": None,
}
"""Every V1 config key and its built-in default.

``flickr_api_key`` is the one key with **no** default: it is absent rather than
defaulted, which is why ``--view`` renders it as ``(not set)`` instead of
flagging it as still-at-default.
"""

API_KEYS: Final[frozenset[str]] = frozenset({"flickr_api_key"})
"""Keys that are vendor credentials.

Never written to ``.optica.toml``, never emitted by ``config --init``, masked by
``--view``, and always written to the global file regardless of whether a
project-local one exists.
"""

CONFIG_KEYS: Final[tuple[str, ...]] = tuple(DEFAULTS)

KEY_HELP: Final[dict[str, str]] = {
    "default_mode": "Acquisition mode: label, curate, clip",
    "default_source": "Fetch source: flickr, open-datasets",
    "default_model": "Backbone: efficientnet-small, efficientnet-large, resnet, "
    "resnet-50, mobilenet, mobilenet-large",
    "images_per_class": "Images per class to fetch",
    "epochs": "Training epochs",
    "learning_rate": "Calibrated for the adaptive optimizers. SGD typically "
    "needs a rate one to two orders of magnitude higher",
    "optimizer": "adamw, adam, sgd",
    "batch_size": "Hardware-dependent; reduce if OOM on CPU",
    "early_stopping": "Patience in epochs. 0 disables early stopping",
    "augmentation": "Training-time transforms. --no-augmentation is the "
    "inverted flag",
    "train_split": "Fraction of the dataset used for training",
    "val_split": "Fraction of the dataset used for validation",
    "test_split": "Fraction of the dataset used for testing",
    "max_checkpoints": "Top N checkpoints saved per run",
    "clip_threshold": "CLIP confidence threshold for clip mode",
    "finetune_ratio": "Proportion of total epochs for Phase 2 fine-tuning. "
    "0.0 skips fine-tuning; 1.0 skips head warmup",
    "max_open_datasets_per_class": "Soft cap for Open Images fetch",
    "curation_port": "Default Curation Server port; auto-increments if taken",
    "curation_timeout_minutes": "Curation server idle timeout. 0 disables",
    "flickr_api_key": "Flickr API key. Global config only, never .optica.toml",
}


@dataclass(frozen=True)
class Domain:
    """The permitted range for one numeric key.

    Attributes:
        minimum: Lower bound.
        maximum: Upper bound, or None where the plan states none.
        min_inclusive: Whether ``minimum`` itself is permitted.
        max_inclusive: Whether ``maximum`` itself is permitted.
        description: The domain as the plan writes it, for the error message.
    """

    minimum: float
    maximum: float | None = None
    min_inclusive: bool = True
    max_inclusive: bool = True
    description: str = ""

    def contains(self, value: float) -> bool:
        """Whether ``value`` lies inside this domain."""
        if self.min_inclusive:
            if value < self.minimum:
                return False
        elif value <= self.minimum:
            return False
        if self.maximum is None:
            return True
        if self.max_inclusive:
            return value <= self.maximum
        return value < self.maximum


NUMERIC_DOMAINS: Final[dict[str, Domain]] = {
    "epochs": Domain(1, description="integer >= 1"),
    "batch_size": Domain(1, description="integer >= 1"),
    "early_stopping": Domain(0, description="integer >= 0"),
    "learning_rate": Domain(
        0.0, 1.0, min_inclusive=False, description="float in (0, 1]"
    ),
    "finetune_ratio": Domain(0.0, 1.0, description="float in [0.0, 1.0]"),
    "train_split": Domain(0.0, 1.0, description="float in [0.0, 1.0]"),
    "val_split": Domain(0.0, 1.0, description="float in [0.0, 1.0]"),
    "test_split": Domain(0.0, 1.0, description="float in [0.0, 1.0]"),
    "max_checkpoints": Domain(1, description="integer >= 1"),
    "images_per_class": Domain(1, description="integer >= 1"),
    "max_open_datasets_per_class": Domain(1, description="integer >= 1"),
    "curation_port": Domain(1024, 65535, description="integer in [1024, 65535]"),
    "curation_timeout_minutes": Domain(0, description="integer >= 0"),
    # The four hard-error bands of the seven (plan § "CLIP Adapter"): below 0.0,
    # above 1.0, exactly 0.0 (disables filtering) and exactly 1.0 (nothing
    # passes) are all errors, which is exactly an open interval. The remaining
    # three bands are a prompt and two warnings, and belong to the command that
    # is about to use the value rather than to config load.
    "clip_threshold": Domain(
        0.0,
        1.0,
        min_inclusive=False,
        max_inclusive=False,
        description="float in (0.0, 1.0), exclusive at both ends",
    ),
}

SPLIT_KEYS: Final[tuple[str, str, str]] = ("train_split", "val_split", "test_split")
SPLIT_TOLERANCE: Final = 0.01
"""``train_split + val_split + test_split`` must equal 1.0 within this."""


def env_var_for(key: str) -> str:
    """Return the environment variable that sets ``key``.

    The transform is mechanical — ``OPTICA_`` plus the uppercased key — and
    applies to **every** config key, exactly as the CLI-flag-to-config-key
    transform does. API keys are the deliberate exception: they keep their
    unprefixed vendor names, because a user typically already holds them under
    those names.
    """
    if key in API_KEYS:
        return key.upper()
    return f"OPTICA_{key.upper()}"
