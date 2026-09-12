"""The typed config model, and the environment-variable tier.

Implements plan § "Configuration" → *Config keys (V1)*, *Split-sum validation*
and *Numeric range validation*.

Validation runs at **config-load time, before any command executes**, per the
config-mirrors-flag standing rule, so a bad value in ``.optica.toml`` errors
rather than misbehaving silently.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from optica.config.defaults import (
    DEFAULTS,
    MODELS,
    MODES,
    NUMERIC_DOMAINS,
    OPTIMIZERS,
    SOURCES,
    SPLIT_KEYS,
    SPLIT_TOLERANCE,
)
from optica.exceptions import OpticaConfigError

__all__ = ["EnvConfig", "OpticaConfig", "validate_values"]

_FIXED_VALUES: dict[str, tuple[str, ...]] = {
    "default_mode": MODES,
    "default_source": SOURCES,
    "default_model": MODELS,
    "optimizer": OPTIMIZERS,
}


class OpticaConfig(BaseModel):
    """A fully resolved configuration.

    Flat by design: plan § "Configuration" states that all V1 config keys are
    flat, with no nested keys.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_mode: str = "curate"
    default_source: str = "open-datasets"
    default_model: str = "efficientnet-small"
    images_per_class: int = 50
    epochs: int = 10
    learning_rate: float = 0.001
    optimizer: str = "adamw"
    batch_size: int = 32
    early_stopping: int = 5
    augmentation: bool = True
    train_split: float = 0.70
    val_split: float = 0.15
    test_split: float = 0.15
    max_checkpoints: int = 3
    clip_threshold: float = 0.25
    finetune_ratio: float = 0.70
    max_open_datasets_per_class: int = 500
    curation_port: int = 8765
    curation_timeout_minutes: int = 60
    flickr_api_key: str | None = None


class EnvConfig(BaseSettings):
    """The environment-variable tier of the priority chain.

    Every field is optional so that only variables the user actually exported
    appear — an unset key must fall through to the next tier rather than
    shadowing it with a default.

    ``env_prefix`` is the mechanism plan § "Configuration" names: ``epochs``
    becomes ``OPTICA_EPOCHS``, ``clip_threshold`` becomes
    ``OPTICA_CLIP_THRESHOLD``. ``flickr_api_key`` overrides it with an explicit
    alias, because a vendor credential keeps the name the user already holds it
    under.

    A ``.env`` file sits at **this** tier rather than beside it, and the Config
    Manager is what puts it there: it calls ``python-dotenv`` to load the file
    into the environment before this class reads it, so ``.env`` values inherit
    env-var precedence instead of forming a sixth tier, and a real environment
    variable still wins over the file.
    """

    model_config = SettingsConfigDict(
        env_prefix="OPTICA_",
        extra="ignore",
        case_sensitive=False,
    )

    default_mode: str | None = None
    default_source: str | None = None
    default_model: str | None = None
    images_per_class: int | None = None
    epochs: int | None = None
    learning_rate: float | None = None
    optimizer: str | None = None
    batch_size: int | None = None
    early_stopping: int | None = None
    augmentation: bool | None = None
    train_split: float | None = None
    val_split: float | None = None
    test_split: float | None = None
    max_checkpoints: int | None = None
    clip_threshold: float | None = None
    finetune_ratio: float | None = None
    max_open_datasets_per_class: int | None = None
    curation_port: int | None = None
    curation_timeout_minutes: int | None = None
    flickr_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FLICKR_API_KEY"),
    )

    @model_validator(mode="after")
    def _no_empty_strings(self) -> EnvConfig:
        """Treat an exported-but-empty variable as unset.

        ``FLICKR_API_KEY=`` in a shell profile is a common way to *clear* a
        credential; reading it as an empty key would shadow the global config
        with nothing.
        """
        if self.flickr_api_key == "":
            object.__setattr__(self, "flickr_api_key", None)
        return self

    def explicit(self) -> dict[str, Any]:
        """Return only the keys the environment actually set."""
        return {
            key: value
            for key, value in self.model_dump().items()
            if value is not None
        }


def _coerce(key: str, value: Any, source: str) -> Any:
    """Convert a raw TOML or flag value to the key's declared type.

    Raises:
        OpticaConfigError: When the value is not of the key's type. Integer keys
            reject floats, strings and booleans, per plan § "Error handling and
            prompt conventions" → *Integer flags reject non-integers*.
    """
    default = DEFAULTS[key]
    if default is None or value is None:
        return value

    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        raise OpticaConfigError(
            f"{key} must be true or false",
            why=f"Got: {value!r} ({source})",
            fix=f"Set {key} = {str(DEFAULTS[key]).lower()}",
        )

    if isinstance(default, int):
        # `bool` is an `int` in Python; a boolean here is a typo, not a count.
        if isinstance(value, bool) or not isinstance(value, int):
            raise OpticaConfigError(
                f"{key} must be a whole number",
                why=f"Got: {value!r} ({source})",
                fix=f"Set {key} = {DEFAULTS[key]}",
            )
        return value

    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OpticaConfigError(
                f"{key} must be a number",
                why=f"Got: {value!r} ({source})",
                fix=f"Set {key} = {DEFAULTS[key]}",
            )
        return float(value)

    if not isinstance(value, str):
        raise OpticaConfigError(
            f"{key} must be text",
            why=f"Got: {value!r} ({source})",
            fix=f"Set {key} = \"{DEFAULTS[key]}\"",
        )
    return value


def validate_values(values: dict[str, Any], sources: dict[str, str]) -> list[str]:
    """Check every value against its domain, collecting **all** failures.

    Plan § "Error handling and prompt conventions": never fail on the first
    invalid value only — a typo loop of fix-one-rerun-hit-the-next is a poor
    experience for any audience. The caller raises once with everything found.

    Args:
        values: The resolved configuration.
        sources: Where each value came from, for the error annotations.

    Returns:
        One message per violation, in key order. Empty when everything is valid.
    """
    problems: list[str] = []

    for key, allowed in _FIXED_VALUES.items():
        value = values.get(key)
        if value is not None and value not in allowed:
            problems.append(
                f"{key} = {value!r} ({sources.get(key, 'default')}) is not valid. "
                f"Valid options: {', '.join(allowed)}. Default: {DEFAULTS[key]}"
            )

    for key, domain in NUMERIC_DOMAINS.items():
        value = values.get(key)
        if value is None:
            continue
        if not domain.contains(float(value)):
            problems.append(
                f"{key} = {value} ({sources.get(key, 'default')}) is out of range. "
                f"Permitted: {domain.description}"
            )

    problems.extend(_split_sum_problem(values, sources))
    return problems


def _split_sum_problem(
    values: dict[str, Any], sources: dict[str, str]
) -> list[str]:
    """Return the split-sum error, if the three splits do not sum to 1.0.

    The check **always** runs regardless of which keys are explicitly set: a key
    sitting at its default does not change the sum. A mismatch is a hard error —
    no auto-adjust, no prompt — and the message annotates each value's source.
    """
    parts = [float(values.get(key, DEFAULTS[key])) for key in SPLIT_KEYS]
    total = sum(parts)
    if abs(total - 1.0) <= SPLIT_TOLERANCE:
        return []
    breakdown = " + ".join(
        f"{value:.2f} ({sources.get(key, 'default')})"
        for key, value in zip(SPLIT_KEYS, parts, strict=True)
    )
    return [
        "train_split + val_split + test_split must equal 1.0. "
        f"Got: {breakdown} = {total:.2f}. "
        "Set all three values to sum to 1.0. "
        "Example: train_split = 0.80, val_split = 0.10, test_split = 0.10"
    ]
