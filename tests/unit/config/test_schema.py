"""The typed config model, the environment tier, and value validation.

Mirrors ``src/optica/config/schema.py``. Covers plan § "Configuration" →
*Config keys (V1)*, *Split-sum validation* and *Numeric range validation*.

``test_manager.py`` exercises these through the priority chain; this file
exercises them directly, so a failure says which layer broke.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from optica.config.defaults import DEFAULTS
from optica.config.schema import EnvConfig, OpticaConfig, _coerce, validate_values
from optica.exceptions import OpticaConfigError


class TestOpticaConfig:
    def test_defaults_match_the_key_table(self):
        config = OpticaConfig()
        for key, expected in DEFAULTS.items():
            assert getattr(config, key) == expected

    def test_it_is_frozen(self):
        # A resolved config is a decision already made; nothing downstream may
        # quietly amend it.
        config = OpticaConfig()
        with pytest.raises(ValidationError):
            config.epochs = 5

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(ValidationError):
            OpticaConfig.model_validate({"nonsense": 1})

    def test_every_key_is_present(self):
        assert set(OpticaConfig().model_dump()) == set(DEFAULTS)


class TestCoerce:
    """Types are checked before ranges, so the message names the right problem."""

    def test_an_integer_key_accepts_an_integer(self):
        assert _coerce("epochs", 20, "config") == 20

    def test_an_integer_key_rejects_a_float(self):
        with pytest.raises(OpticaConfigError) as caught:
            _coerce("epochs", 10.5, "config")
        assert "whole number" in caught.value.message

    def test_an_integer_key_rejects_a_string(self):
        with pytest.raises(OpticaConfigError):
            _coerce("epochs", "ten", "config")

    def test_an_integer_key_rejects_a_boolean(self):
        # `bool` is an `int` in Python; a boolean here is a typo, not a count.
        with pytest.raises(OpticaConfigError):
            _coerce("epochs", True, "config")

    def test_a_float_key_accepts_an_integer(self):
        # 1 for learning_rate is a number, not a type error.
        assert _coerce("learning_rate", 1, "config") == 1.0

    def test_a_float_key_rejects_a_boolean(self):
        with pytest.raises(OpticaConfigError):
            _coerce("finetune_ratio", True, "config")

    def test_a_boolean_key_rejects_an_integer(self):
        with pytest.raises(OpticaConfigError) as caught:
            _coerce("augmentation", 1, "config")
        assert "true or false" in caught.value.message

    def test_a_string_key_rejects_a_number(self):
        with pytest.raises(OpticaConfigError):
            _coerce("default_mode", 3, "config")

    def test_the_error_names_the_source(self):
        with pytest.raises(OpticaConfigError) as caught:
            _coerce("epochs", "ten", "--epochs")
        assert "--epochs" in (caught.value.why or "")

    def test_a_key_with_no_default_passes_through(self):
        assert _coerce("flickr_api_key", "abc", "config") == "abc"

    def test_none_passes_through(self):
        assert _coerce("epochs", None, "config") is None


class TestValidateValues:
    """Every failure is collected; the caller raises once."""

    def test_a_valid_config_has_no_problems(self):
        assert validate_values(dict(DEFAULTS), {}) == []

    def test_a_range_violation_is_reported(self):
        problems = validate_values({**DEFAULTS, "epochs": 0}, {"epochs": "config"})
        assert any("epochs" in problem for problem in problems)

    def test_the_permitted_domain_is_quoted(self):
        problems = validate_values({**DEFAULTS, "epochs": 0}, {"epochs": "config"})
        assert "integer >= 1" in problems[0]

    def test_a_fixed_value_violation_lists_options_and_default(self):
        problems = validate_values(
            {**DEFAULTS, "default_source": "flikr"}, {"default_source": "config"}
        )
        assert "flickr" in problems[0]
        assert "open-datasets" in problems[0]
        assert "Default: open-datasets" in problems[0]

    def test_several_failures_are_all_reported(self):
        # Never fail on the first invalid value only.
        problems = validate_values(
            {**DEFAULTS, "epochs": 0, "batch_size": 0, "default_mode": "nope"},
            {},
        )
        rendered = " ".join(problems)
        assert "epochs" in rendered
        assert "batch_size" in rendered
        assert "default_mode" in rendered
        assert len(problems) >= 3

    def test_the_source_annotation_appears(self):
        problems = validate_values({**DEFAULTS, "epochs": 0}, {"epochs": "--epochs"})
        assert "--epochs" in problems[0]

    def test_an_unannotated_key_reads_as_default(self):
        problems = validate_values({**DEFAULTS, "epochs": 0}, {})
        assert "(default)" in problems[0]


class TestClipThresholdBands:
    """The four hard-error bands of the seven (plan § "CLIP Adapter")."""

    @pytest.mark.parametrize("value", [-0.1, 0.0, 1.0, 1.1])
    def test_rejected(self, value):
        problems = validate_values(
            {**DEFAULTS, "clip_threshold": value}, {"clip_threshold": "config"}
        )
        assert any("clip_threshold" in problem for problem in problems)

    @pytest.mark.parametrize("value", [0.05, 0.25, 0.6, 0.99])
    def test_the_other_three_bands_pass_config_validation(self, value):
        # A prompt and two warnings belong to the command about to use the
        # value, not to config load.
        problems = validate_values({**DEFAULTS, "clip_threshold": value}, {})
        assert not any("clip_threshold" in problem for problem in problems)


class TestSplitSum:
    """A hard error: no auto-adjust, no prompt."""

    def test_the_defaults_sum_to_one(self):
        assert validate_values(dict(DEFAULTS), {}) == []

    def test_a_mismatch_is_reported(self):
        problems = validate_values(
            {**DEFAULTS, "train_split": 0.80, "val_split": 0.10},
            {"train_split": "config", "val_split": "config"},
        )
        assert any("must equal 1.0" in problem for problem in problems)

    def test_the_breakdown_is_printed_not_just_the_total(self):
        problems = validate_values(
            {**DEFAULTS, "train_split": 0.80, "val_split": 0.10},
            {"train_split": "config", "val_split": "config"},
        )
        message = next(p for p in problems if "must equal 1.0" in p)
        # The plan's shape, per value and then the total.
        assert "0.80 (config)" in message
        assert "0.10 (config)" in message
        assert "0.15 (default)" in message
        assert "1.05" in message

    def test_the_check_runs_when_no_split_is_explicitly_set(self):
        # A key at its default does not change the sum, so the check cannot be
        # conditioned on which keys were set.
        problems = validate_values({**DEFAULTS, "test_split": 0.50}, {})
        assert any("must equal 1.0" in problem for problem in problems)

    @pytest.mark.parametrize("test_split", [0.151, 0.149])
    def test_float_tolerance(self, test_split):
        problems = validate_values({**DEFAULTS, "test_split": test_split}, {})
        assert not any("must equal 1.0" in problem for problem in problems)

    def test_beyond_tolerance_fails(self):
        problems = validate_values({**DEFAULTS, "test_split": 0.17}, {})
        assert any("must equal 1.0" in problem for problem in problems)


class TestEnvConfig:
    """``OPTICA_`` plus the uppercased key, with API keys the exception."""

    def test_nothing_set_is_nothing_reported(self):
        assert EnvConfig().explicit() == {}

    def test_a_prefixed_variable_is_read(self, monkeypatch):
        monkeypatch.setenv("OPTICA_EPOCHS", "30")
        assert EnvConfig().explicit() == {"epochs": 30}

    def test_the_value_is_typed_not_left_as_text(self, monkeypatch):
        monkeypatch.setenv("OPTICA_EPOCHS", "30")
        assert EnvConfig().explicit()["epochs"] == 30

    def test_a_long_key_keeps_its_underscores(self, monkeypatch):
        monkeypatch.setenv("OPTICA_MAX_OPEN_DATASETS_PER_CLASS", "250")
        assert EnvConfig().explicit() == {"max_open_datasets_per_class": 250}

    def test_an_api_key_has_no_prefix(self, monkeypatch):
        monkeypatch.setenv("FLICKR_API_KEY", "abc123")
        assert EnvConfig().explicit() == {"flickr_api_key": "abc123"}

    def test_the_prefixed_spelling_is_not_how_an_api_key_is_set(self, monkeypatch):
        monkeypatch.setenv("OPTICA_FLICKR_API_KEY", "abc123")
        assert EnvConfig().explicit() == {}

    def test_an_empty_api_key_counts_as_unset(self, monkeypatch):
        # Clearing a credential in a shell profile must not shadow the config
        # file with an empty string.
        monkeypatch.setenv("FLICKR_API_KEY", "")
        assert EnvConfig().explicit() == {}

    def test_a_boolean_variable(self, monkeypatch):
        monkeypatch.setenv("OPTICA_AUGMENTATION", "false")
        assert EnvConfig().explicit() == {"augmentation": False}

    def test_unrelated_variables_are_ignored(self, monkeypatch):
        monkeypatch.setenv("OPTICA_NOT_A_KEY", "1")
        assert EnvConfig().explicit() == {}
