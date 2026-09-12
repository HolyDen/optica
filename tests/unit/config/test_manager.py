"""Priority resolution, reading and writing.

Covers plan § "Configuration": the five-tier priority chain, ``.env`` at the
env-var tier, split-sum and numeric-range validation at config-load time,
unknown-key rejection at write time, the API-key rules, and ``--init``'s
commented defaults.
"""

from __future__ import annotations

import pytest

from optica.config.manager import ConfigManager, Source
from optica.exceptions import OpticaConfigError


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """A manager with a throwaway project directory and home."""
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    monkeypatch.chdir(project)
    return ConfigManager(project_dir=project, home=home)


class TestPriority:
    """CLI flags > project > env > global > built-in defaults."""

    def test_defaults_when_nothing_is_set(self, manager):
        resolved = manager.resolve()
        assert resolved.config.epochs == 10
        assert resolved.sources["epochs"] is Source.DEFAULT

    def test_global_beats_defaults(self, manager):
        manager.global_path.parent.mkdir(parents=True, exist_ok=True)
        manager.global_path.write_text("epochs = 25\n", encoding="utf-8")
        resolved = manager.resolve()
        assert resolved.config.epochs == 25
        assert resolved.sources["epochs"] is Source.GLOBAL

    def test_env_beats_global(self, manager, monkeypatch):
        manager.global_path.parent.mkdir(parents=True, exist_ok=True)
        manager.global_path.write_text("epochs = 25\n", encoding="utf-8")
        monkeypatch.setenv("OPTICA_EPOCHS", "30")
        resolved = manager.resolve()
        assert resolved.config.epochs == 30
        assert resolved.sources["epochs"] is Source.ENV

    def test_project_beats_env(self, manager, monkeypatch):
        monkeypatch.setenv("OPTICA_EPOCHS", "30")
        manager.project_path.write_text("epochs = 40\n", encoding="utf-8")
        resolved = manager.resolve()
        assert resolved.config.epochs == 40
        assert resolved.sources["epochs"] is Source.PROJECT

    def test_flags_beat_everything(self, manager, monkeypatch):
        monkeypatch.setenv("OPTICA_EPOCHS", "30")
        manager.project_path.write_text("epochs = 40\n", encoding="utf-8")
        resolved = manager.resolve(overrides={"epochs": 50})
        assert resolved.config.epochs == 50
        assert resolved.sources["epochs"] is Source.FLAG

    def test_an_unset_flag_does_not_shadow_a_lower_tier(self, manager):
        manager.project_path.write_text("epochs = 40\n", encoding="utf-8")
        resolved = manager.resolve(overrides={"epochs": None})
        assert resolved.config.epochs == 40

    def test_tiers_merge_per_key_rather_than_wholesale(self, manager, monkeypatch):
        manager.global_path.parent.mkdir(parents=True, exist_ok=True)
        manager.global_path.write_text("batch_size = 64\n", encoding="utf-8")
        monkeypatch.setenv("OPTICA_EPOCHS", "30")
        resolved = manager.resolve()
        assert resolved.config.batch_size == 64
        assert resolved.config.epochs == 30


class TestDotEnv:
    """``.env`` sits at the env-var tier, not beside it."""

    def test_dotenv_supplies_the_env_tier(self, manager):
        manager.dotenv_path.write_text("OPTICA_EPOCHS=33\n", encoding="utf-8")
        resolved = manager.resolve()
        assert resolved.config.epochs == 33
        assert resolved.sources["epochs"] is Source.ENV

    def test_a_real_variable_wins_over_the_file(self, manager, monkeypatch):
        manager.dotenv_path.write_text("OPTICA_EPOCHS=33\n", encoding="utf-8")
        monkeypatch.setenv("OPTICA_EPOCHS", "44")
        assert manager.resolve().config.epochs == 44

    def test_project_config_still_beats_dotenv(self, manager):
        manager.dotenv_path.write_text("OPTICA_EPOCHS=33\n", encoding="utf-8")
        manager.project_path.write_text("epochs = 40\n", encoding="utf-8")
        assert manager.resolve().config.epochs == 40


class TestApiKeys:
    def test_unprefixed_env_name(self, manager, monkeypatch):
        monkeypatch.setenv("FLICKR_API_KEY", "abc123")
        assert manager.resolve().config.flickr_api_key == "abc123"

    def test_a_key_in_the_project_file_is_a_load_time_error(self, manager):
        manager.project_path.write_text('flickr_api_key = "abc123"\n', encoding="utf-8")
        with pytest.raises(OpticaConfigError) as caught:
            manager.resolve()
        assert "flickr_api_key" in (caught.value.why or "")
        assert ".optica.toml" in caught.value.message

    def test_a_key_in_the_global_file_is_fine(self, manager):
        manager.global_path.parent.mkdir(parents=True, exist_ok=True)
        manager.global_path.write_text('flickr_api_key = "abc123"\n', encoding="utf-8")
        assert manager.resolve().config.flickr_api_key == "abc123"

    def test_set_always_writes_a_key_to_the_global_file(self, manager):
        manager.project_path.write_text("epochs = 12\n", encoding="utf-8")
        target, _ = manager.set_key("flickr_api_key", "abc123")
        assert target == manager.global_path

    def test_an_empty_variable_counts_as_unset(self, manager, monkeypatch):
        manager.global_path.parent.mkdir(parents=True, exist_ok=True)
        manager.global_path.write_text('flickr_api_key = "stored"\n', encoding="utf-8")
        monkeypatch.setenv("FLICKR_API_KEY", "")
        assert manager.resolve().config.flickr_api_key == "stored"


class TestSplitSum:
    """A mismatch is a hard error: no auto-adjust, no prompt."""

    def test_mismatch_raises(self, manager):
        manager.project_path.write_text(
            "train_split = 0.80\nval_split = 0.10\n", encoding="utf-8"
        )
        with pytest.raises(OpticaConfigError) as caught:
            manager.resolve()
        rendered = " ".join(
            [caught.value.message, caught.value.why or "", *caught.value.fix]
        )
        assert "must equal 1.0" in rendered

    def test_the_error_annotates_each_value_with_its_source(self, manager):
        manager.project_path.write_text(
            "train_split = 0.80\nval_split = 0.10\n", encoding="utf-8"
        )
        with pytest.raises(OpticaConfigError) as caught:
            manager.resolve()
        rendered = " ".join(
            [caught.value.message, caught.value.why or "", *caught.value.fix]
        )
        # The plan's shape: 0.80 (config) + 0.10 (config) + 0.15 (default) = 1.05
        assert "0.80 (config)" in rendered
        assert "0.10 (config)" in rendered
        assert "0.15 (default)" in rendered
        assert "1.05" in rendered

    def test_the_check_runs_even_when_no_split_is_set(self, manager):
        # A key at its default does not change the sum, so the defaults must
        # themselves be valid.
        manager.resolve()

    def test_float_tolerance_is_accepted(self, manager):
        manager.project_path.write_text(
            "train_split = 0.7\nval_split = 0.15\ntest_split = 0.151\n",
            encoding="utf-8",
        )
        manager.resolve()


class TestRangeValidation:
    def test_out_of_range_raises_at_load(self, manager):
        manager.project_path.write_text("epochs = 0\n", encoding="utf-8")
        with pytest.raises(OpticaConfigError):
            manager.resolve()

    def test_clip_threshold_zero_is_rejected(self, manager):
        manager.project_path.write_text("clip_threshold = 0.0\n", encoding="utf-8")
        with pytest.raises(OpticaConfigError):
            manager.resolve()

    def test_clip_threshold_one_is_rejected(self, manager):
        manager.project_path.write_text("clip_threshold = 1.0\n", encoding="utf-8")
        with pytest.raises(OpticaConfigError):
            manager.resolve()

    def test_an_integer_key_rejects_a_float(self, manager):
        manager.project_path.write_text("epochs = 10.5\n", encoding="utf-8")
        with pytest.raises(OpticaConfigError):
            manager.resolve()

    def test_an_integer_key_rejects_a_boolean(self, manager):
        manager.project_path.write_text("epochs = true\n", encoding="utf-8")
        with pytest.raises(OpticaConfigError):
            manager.resolve()

    def test_a_fixed_value_key_lists_its_options_and_default(self, manager):
        manager.project_path.write_text('default_source = "flikr"\n', encoding="utf-8")
        with pytest.raises(OpticaConfigError) as caught:
            manager.resolve()
        rendered = " ".join(
            [caught.value.message, caught.value.why or "", *caught.value.fix]
        )
        assert "flickr" in rendered
        assert "open-datasets" in rendered
        assert "Default: open-datasets" in rendered

    def test_all_invalid_values_are_reported_at_once(self, manager):
        manager.project_path.write_text(
            'epochs = 0\nbatch_size = 0\ndefault_mode = "nope"\n', encoding="utf-8"
        )
        with pytest.raises(OpticaConfigError) as caught:
            manager.resolve()
        rendered = " ".join(caught.value.fix)
        # Never fail on the first invalid value only.
        assert "epochs" in rendered
        assert "batch_size" in rendered
        assert "default_mode" in rendered


class TestUnknownKeys:
    def test_rejected_at_write_time_with_a_suggestion(self, manager):
        with pytest.raises(OpticaConfigError) as caught:
            manager.set_key("epocs", "20")
        assert "epochs" in (caught.value.why or "") + " ".join(caught.value.fix)

    def test_rejected_at_write_time_without_a_close_match(self, manager):
        with pytest.raises(OpticaConfigError) as caught:
            manager.set_key("zzzzzz", "20")
        assert caught.value.options  # lists the valid keys

    def test_nothing_is_written_when_the_key_is_rejected(self, manager):
        with pytest.raises(OpticaConfigError):
            manager.set_key("epocs", "20")
        assert not manager.global_path.exists()

    def test_rejected_at_load_time_too(self, manager):
        manager.project_path.write_text("epocs = 20\n", encoding="utf-8")
        with pytest.raises(OpticaConfigError):
            manager.resolve()

    def test_a_nested_table_is_rejected(self, manager):
        manager.project_path.write_text("[training]\nepochs = 20\n", encoding="utf-8")
        with pytest.raises(OpticaConfigError) as caught:
            manager.resolve()
        assert "flat" in (caught.value.why or "")


class TestSet:
    def test_writes_global_when_no_project_file_exists(self, manager):
        target, value = manager.set_key("epochs", "20")
        assert target == manager.global_path
        assert value == 20
        assert manager.resolve().config.epochs == 20

    def test_writes_project_when_one_exists(self, manager):
        manager.project_path.write_text("epochs = 12\n", encoding="utf-8")
        target, _ = manager.set_key("epochs", "20")
        assert target == manager.project_path

    def test_global_flag_forces_global(self, manager):
        manager.project_path.write_text("epochs = 12\n", encoding="utf-8")
        target, _ = manager.set_key("epochs", "20", use_global=True)
        assert target == manager.global_path

    def test_creates_the_global_file_when_neither_exists(self, manager):
        assert not manager.global_path.exists()
        target, _ = manager.set_key("epochs", "20")
        assert target.exists()

    def test_rejects_a_value_outside_the_domain(self, manager):
        with pytest.raises(OpticaConfigError):
            manager.set_key("curation_port", "80")

    def test_rejects_a_non_integer(self, manager):
        with pytest.raises(OpticaConfigError):
            manager.set_key("epochs", "ten")

    def test_booleans_parse(self, manager):
        _, value = manager.set_key("augmentation", "false")
        assert value is False
        assert manager.resolve().config.augmentation is False

    def test_an_existing_key_is_replaced_not_duplicated(self, manager):
        manager.set_key("epochs", "20")
        manager.set_key("epochs", "30")
        text = manager.global_path.read_text(encoding="utf-8")
        assert text.count("epochs") == 1
        assert manager.resolve().config.epochs == 30


class TestInit:
    """``--init`` writes commented defaults."""

    def test_every_key_is_present_but_commented(self, manager):
        path = manager.init_project()
        text = path.read_text(encoding="utf-8")
        assert "# epochs = 10" in text
        assert "\nepochs = 10" not in text

    def test_the_api_key_is_never_emitted(self, manager):
        # The file is committed, so a commented credential is an invitation to
        # uncomment one into version control.
        text = manager.init_project().read_text(encoding="utf-8")
        assert "flickr_api_key" not in text

    def test_nothing_is_set_so_view_still_flags_defaults(self, manager):
        manager.init_project()
        rows = {row.key: row for row in manager.view()}
        assert rows["epochs"].at_default is True

    def test_uncommenting_a_key_sets_it(self, manager):
        path = manager.init_project()
        text = path.read_text(encoding="utf-8").replace("# epochs = 10", "epochs = 99")
        path.write_text(text, encoding="utf-8")
        assert manager.resolve().config.epochs == 99

    def test_set_replaces_a_commented_key_in_place(self, manager):
        manager.init_project()
        manager.set_key("epochs", "42")
        assert manager.resolve().config.epochs == 42
        assert "# epochs = 10" not in manager.project_path.read_text(encoding="utf-8")

    def test_the_file_stays_valid_toml(self, manager):
        manager.init_project()
        manager.resolve()  # would raise on a parse failure


class TestView:
    def test_source_annotations(self, manager, monkeypatch):
        monkeypatch.setenv("OPTICA_EPOCHS", "30")
        manager.global_path.parent.mkdir(parents=True, exist_ok=True)
        manager.global_path.write_text("batch_size = 64\n", encoding="utf-8")
        rows = {row.key: row for row in manager.view()}
        assert rows["epochs"].source is Source.ENV
        assert rows["batch_size"].source is Source.GLOBAL
        assert rows["optimizer"].source is Source.DEFAULT

    def test_defaults_are_flagged(self, manager):
        rows = {row.key: row for row in manager.view()}
        assert rows["epochs"].at_default is True

    def test_an_api_key_is_masked_but_keeps_its_source(self, manager, monkeypatch):
        monkeypatch.setenv("FLICKR_API_KEY", "super-secret")
        row = next(r for r in manager.view() if r.key == "flickr_api_key")
        assert "super-secret" not in row.value
        assert row.value == "••••••••"
        assert row.source is Source.ENV

    def test_an_unset_api_key_renders_as_not_set(self, manager):
        row = next(r for r in manager.view() if r.key == "flickr_api_key")
        assert row.value == "(not set)"
        assert row.is_set is False
        # Absent and defaulted are different states.
        assert row.at_default is False

    def test_every_key_appears(self, manager):
        from optica.config.defaults import CONFIG_KEYS

        assert [row.key for row in manager.view()] == list(CONFIG_KEYS)


class TestPlanValuesStillToImplement:
    @pytest.mark.skip(reason="stub - pass 2")
    def test_clear_staging_lists_all_three_staging_shapes(self):
        """All three staging shapes are listed.

        The deletion logic lives in the Input Manager; cli/config.py delegates
        to it.
        """

    @pytest.mark.skip(reason="stub - pass 5")
    def test_setup_creates_the_global_config(self):
        """`~/.optica/config.toml` is created by `optica setup`."""
