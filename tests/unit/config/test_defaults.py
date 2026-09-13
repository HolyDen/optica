"""The V1 config key table.

Covers plan § "Configuration" → *Config keys (V1)* and *Numeric range
validation*. Every value here is transcribed from the plan's own tables, so a
failure means the code drifted from the plan rather than the other way round.
"""

from __future__ import annotations

import pytest

from optica.config import defaults


class TestKeyTable:
    """The nineteen keys and their defaults, row by row."""

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("default_mode", "curate"),
            ("default_source", "open-datasets"),
            ("default_model", "efficientnet-small"),
            ("images_per_class", 50),
            ("epochs", 10),
            ("learning_rate", 0.001),
            ("optimizer", "adamw"),
            ("batch_size", 32),
            ("early_stopping", 5),
            ("augmentation", True),
            ("train_split", 0.70),
            ("val_split", 0.15),
            ("test_split", 0.15),
            ("max_checkpoints", 3),
            ("clip_threshold", 0.25),
            ("finetune_ratio", 0.70),
            ("max_open_datasets_per_class", 500),
            ("curation_port", 8765),
            ("curation_timeout_minutes", 60),
        ],
    )
    def test_default(self, key, value):
        assert defaults.DEFAULTS[key] == value

    def test_flickr_api_key_has_no_default(self):
        # The only key that can be *absent* rather than defaulted, which is why
        # --view renders it as "(not set)".
        assert defaults.DEFAULTS["flickr_api_key"] is None

    def test_the_splits_sum_to_one(self):
        assert sum(defaults.DEFAULTS[key] for key in defaults.SPLIT_KEYS) == 1.0

    def test_keys_not_in_the_v1_set_are_absent(self):
        # Accepted, do not add: these travel with later flags.
        absent_keys = (
            "export_format",
            "strict_min_size",
            "dedup_threshold",
            "default_task",
        )
        for absent in absent_keys:
            assert absent not in defaults.DEFAULTS

    def test_every_key_is_flat(self):
        assert all(isinstance(value, (str, int, float, bool, type(None)))
                   for value in defaults.DEFAULTS.values())


class TestDefaultTask:
    """``default_task`` is a constant in V1, not a config key."""

    def test_value(self):
        assert defaults.DEFAULT_TASK == "classify"

    def test_it_is_not_a_config_key(self):
        assert "default_task" not in defaults.DEFAULTS


class TestFixedValueSets:
    def test_modes(self):
        assert defaults.MODES == ("label", "curate", "clip")

    def test_sources(self):
        assert defaults.SOURCES == ("flickr", "open-datasets")

    def test_models_are_six_names_for_four_backbones(self):
        assert defaults.MODELS == (
            "efficientnet-small",
            "efficientnet-large",
            "resnet",
            "resnet-50",
            "mobilenet",
            "mobilenet-large",
        )

    def test_optimizers(self):
        assert defaults.OPTIMIZERS == ("adamw", "adam", "sgd")


class TestDomains:
    """The plan's numeric-range table."""

    @pytest.mark.parametrize(
        ("key", "ok", "bad"),
        [
            ("epochs", 1, 0),
            ("batch_size", 1, 0),
            ("early_stopping", 0, -1),
            ("max_checkpoints", 1, 0),
            ("images_per_class", 1, 0),
            ("max_open_datasets_per_class", 1, 0),
            ("curation_timeout_minutes", 0, -1),
            ("curation_port", 1024, 1023),
            ("finetune_ratio", 0.0, -0.1),
            ("train_split", 1.0, 1.1),
        ],
    )
    def test_boundaries(self, key, ok, bad):
        domain = defaults.NUMERIC_DOMAINS[key]
        assert domain.contains(ok)
        assert not domain.contains(bad)

    def test_curation_port_upper_bound(self):
        domain = defaults.NUMERIC_DOMAINS["curation_port"]
        assert domain.contains(65535)
        assert not domain.contains(65536)

    def test_learning_rate_excludes_zero_and_includes_one(self):
        domain = defaults.NUMERIC_DOMAINS["learning_rate"]
        assert not domain.contains(0.0)
        assert domain.contains(1.0)
        assert not domain.contains(1.0001)

    @pytest.mark.parametrize("value", [-0.1, 0.0, 1.0, 1.1])
    def test_clip_threshold_hard_error_bands(self, value):
        # Four of the seven bands are hard errors: below 0.0, above 1.0,
        # exactly 0.0 (disables filtering) and exactly 1.0 (nothing passes).
        assert not defaults.NUMERIC_DOMAINS["clip_threshold"].contains(value)

    @pytest.mark.parametrize("value", [0.05, 0.25, 0.6, 0.9])
    def test_clip_threshold_accepts_the_other_three_bands(self, value):
        assert defaults.NUMERIC_DOMAINS["clip_threshold"].contains(value)


class TestEnvVarNames:
    """``OPTICA_`` plus the uppercased key, mechanically, for every key."""

    @pytest.mark.parametrize(
        ("key", "variable"),
        [
            ("epochs", "OPTICA_EPOCHS"),
            ("clip_threshold", "OPTICA_CLIP_THRESHOLD"),
            ("max_open_datasets_per_class", "OPTICA_MAX_OPEN_DATASETS_PER_CLASS"),
        ],
    )
    def test_prefixed(self, key, variable):
        assert defaults.env_var_for(key) == variable

    def test_api_keys_keep_their_unprefixed_vendor_name(self):
        # They are credentials a user already holds under that name, not Optica
        # settings.
        assert defaults.env_var_for("flickr_api_key") == "FLICKR_API_KEY"

    def test_every_key_has_a_variable(self):
        assert all(defaults.env_var_for(key) for key in defaults.CONFIG_KEYS)


class TestPlanValuesStillToImplement:
    # The three hard-error bands are this module's (``NUMERIC_DOMAINS``); the
    # prompt and the two warnings belong to the command about to use the value,
    # and were built in pass 2 in ``optica.input.manager``. Full band table:
    # tests/unit/input/test_manager.py::TestClipThresholdBands.

    @pytest.mark.parametrize("value", [0.75, 0.9, 0.999])
    def test_clip_threshold_strict_end_prompt_band(self, value):
        """0.75 to <1.0 raises a Y/n prompt: very strict, few images pass."""
        from optica.input.manager import check_clip_threshold

        assert defaults.NUMERIC_DOMAINS["clip_threshold"].contains(value)
        check = check_clip_threshold(value, command="fetch")
        assert check.prompt is not None
        assert check.warning is None

    @pytest.mark.parametrize(
        ("value", "warns"),
        [(0.05, True), (0.0999, True), (0.1, False), (0.25, False), (0.4999, False),
         (0.5, True), (0.7499, True)],
    )  # fmt: skip
    def test_clip_threshold_warn_and_continue_bands(self, value, warns):
        """Two bands warn and continue.

        0.5 to <0.75 and >0.0 to <0.1 warn; 0.1 to <0.5 is normal, with no
        warning.
        """
        from optica.input.manager import check_clip_threshold

        check = check_clip_threshold(value, command="fetch")
        assert (check.warning is not None) is warns
        assert check.prompt is None

    @pytest.mark.skip(reason="stub - pass 4")
    def test_finetune_ratio_extremes_warn(self):
        """Both extremes are permitted, and both warn.

        0.0 skips fine-tuning; 1.0 skips head warmup.
        """
