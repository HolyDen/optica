"""``optica setup`` — the Machine Initializer.

Covers plan § "`optica setup` — Machine Initializer": the flags and their
impossible combinations, **`--ci`** (config only, no install, no environment
detection, no prompts, no Review), the five environment-resolution cases and
their non-interactive counterparts, *interactivity is binary*, the create-name
collision, the two hardware safety prompts and their auto-abort, the Review
step, idempotence, and the completion and incomplete messages.

Every condition is constructed. The GPU probe, the installed-package probe and
the subprocess runner are all replaced, so nothing here depends on what this
machine happens to have: a test about a machine with no CUDA GPU says so in its
own body rather than inheriting the build machine's answer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from optica.cli.main import app
from optica.cli.setup import EnvKind
from optica.exceptions import ExitCode
from optica.utils import system as sysinfo


@pytest.fixture
def machine(monkeypatch, fake_home, project_dir):
    """A machine with nothing installed, no GPU, and no environment anywhere."""
    state: dict[str, Any] = {
        "installed": {},
        "commands": [],
        "returncode": 0,
        "gpu": sysinfo.GPUInfo(sysinfo.Accelerator.CPU, description="CPU only"),
    }

    def run(command, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        state["commands"].append(list(command))
        return subprocess.CompletedProcess(command, state["returncode"], "", "")

    monkeypatch.setattr("optica.cli.setup.subprocess.run", run)
    monkeypatch.setattr(
        "optica.cli.setup.sysinfo.installed_version",
        lambda package: state["installed"].get(package),
    )
    monkeypatch.setattr("optica.cli.setup.sysinfo.detect_gpu", lambda: state["gpu"])
    monkeypatch.setattr("optica.cli.setup.sysinfo.pairing_problem", lambda: None)
    monkeypatch.setattr("optica.cli.setup.stack_import_problem", lambda: None)
    # No environment of any kind, unless a test builds one.
    monkeypatch.setattr("optica.cli.setup.sysinfo.running_in_conda", lambda: False)
    monkeypatch.setattr("optica.cli.setup.sysinfo.running_in_venv", lambda: False)
    monkeypatch.setattr("optica.cli.setup.sysinfo.venv_path", lambda: None)
    monkeypatch.setattr("optica.cli.setup.sysinfo.conda_prefix", lambda: None)
    monkeypatch.setattr("optica.cli.setup.sysinfo.declared_venv", lambda: None)
    return state


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)
    monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)


def _venv(root: Path, name: str = ".venv") -> Path:
    """A directory that is a virtual environment by the marker that decides it."""
    path = root / name
    (path / "Scripts").mkdir(parents=True)
    (path / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (path / "Scripts" / "python.exe").write_bytes(b"")
    return path


def _answers(monkeypatch, *replies: str) -> list[str]:
    queue = list(replies)
    asked: list[str] = []

    def prompt(text: str, **kwargs: Any) -> str:
        asked.append(text)
        return queue.pop(0)

    def confirm(text: str, **kwargs: Any) -> bool:
        asked.append(text)
        return queue.pop(0).strip().lower().startswith("y")

    monkeypatch.setattr("typer.prompt", prompt)
    monkeypatch.setattr("typer.confirm", confirm)
    return asked


def _pip(state: dict[str, Any]) -> list[list[str]]:
    return [c for c in state["commands"] if "pip" in c]


class TestCI:
    """Plan § "`optica setup`" → *`--ci` — the owning definition*."""

    def test_it_writes_config_and_installs_nothing(self, machine, fake_home, capsys):
        code = app.invoke_guarded(["setup", "--ci"])
        out = capsys.readouterr().out
        assert code == ExitCode.SUCCESS
        assert (fake_home / ".optica" / "config.toml").is_file()
        assert _pip(machine) == []
        assert "Setup complete" in out

    def test_it_never_touches_environment_detection(self, machine, monkeypatch):
        # Constructed: every detection entry point fails the test if reached.
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("--ci must not detect an environment")

        for name in (
            "running_in_venv",
            "running_in_conda",
            "declared_venv",
            "conda_prefix",
            "discover_venvs",
            "detect_gpu",
        ):
            monkeypatch.setattr(f"optica.cli.setup.sysinfo.{name}", forbidden)
        assert app.invoke_guarded(["setup", "--ci"]) == ExitCode.SUCCESS

    def test_it_asks_nothing_even_with_a_terminal(
        self, machine, interactive, monkeypatch
    ):
        # A prompt in CI would be a hard exit 1, so --ci must reach none.
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("--ci must not prompt")

        monkeypatch.setattr("typer.prompt", forbidden)
        monkeypatch.setattr("typer.confirm", forbidden)
        assert app.invoke_guarded(["setup", "--ci"]) == ExitCode.SUCCESS

    def test_it_shows_no_review(self, machine, capsys):
        app.invoke_guarded(["setup", "--ci"])
        captured = capsys.readouterr()
        assert "Review" not in captured.out + captured.err

    def test_a_second_run_leaves_the_file_alone(self, machine, fake_home, capsys):
        app.invoke_guarded(["setup", "--ci"])
        target = fake_home / ".optica" / "config.toml"
        target.write_text("epochs = 20\n", encoding="utf-8")
        capsys.readouterr()
        assert app.invoke_guarded(["setup", "--ci"]) == ExitCode.SUCCESS
        assert target.read_text(encoding="utf-8") == "epochs = 20\n"
        assert "already present" in capsys.readouterr().out

    def test_it_works_outside_a_venv(self, machine, monkeypatch, fake_home):
        # CI runs outside a venv on all three runners: actions/setup-python
        # installs into the hosted toolcache. Constructed, since this machine is
        # inside one.
        monkeypatch.setattr("optica.cli.setup.sysinfo.running_in_venv", lambda: False)
        assert app.invoke_guarded(["setup", "--ci"]) == ExitCode.SUCCESS

    @pytest.mark.parametrize(
        "flag",
        ["--all-extras", "--no-extras", "--include-extras=web", "--exclude-extras=clip"],
    )
    def test_it_errors_with_every_extras_flag(self, machine, flag, capsys):
        code = app.invoke_guarded(["setup", "--ci", flag])
        assert code == ExitCode.ERROR
        assert "--ci cannot be combined" in capsys.readouterr().err


class TestFlagCombinations:
    def test_all_extras_with_no_extras_is_a_hard_error(self, machine, capsys):
        code = app.invoke_guarded(["setup", "--all-extras", "--no-extras"])
        assert code == ExitCode.ERROR
        assert "cannot be combined" in capsys.readouterr().err

    def test_upgrade_with_an_extras_flag_is_a_hard_error(self, machine, capsys):
        code = app.invoke_guarded(["setup", "--upgrade", "--all-extras"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "--upgrade cannot be combined" in err
        assert "per-package prompts" in err

    def test_skip_keys_alongside_an_extras_flag_is_silently_accepted(
        self, machine, project_dir, capsys
    ):
        # A flag asking for something already true is a no-op, not an error.
        _venv(project_dir)
        code = app.invoke_guarded(["setup", "--no-extras", "--skip-keys"])
        assert code == ExitCode.SUCCESS
        assert "skip-keys" not in capsys.readouterr().err

    def test_an_unknown_extra_lists_the_valid_keys(self, machine, capsys):
        code = app.invoke_guarded(["setup", "--include-extras", "wbe"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "Did you mean 'web'?" in err


class TestEnvironmentResolution:
    def test_an_active_venv_wins_and_a_found_one_is_ignored(
        self, machine, monkeypatch, project_dir, capsys
    ):
        active = project_dir / "active-env"
        monkeypatch.setattr("optica.cli.setup.sysinfo.running_in_venv", lambda: True)
        monkeypatch.setattr("optica.cli.setup.sysinfo.venv_path", lambda: active)
        _venv(project_dir)  # on disk, and must not be asked about
        code = app.invoke_guarded(["setup", "--no-extras"])
        assert code == ExitCode.SUCCESS
        assert f"Venv: {active} (active)" in capsys.readouterr().err

    def test_an_active_conda_environment_is_a_valid_target(
        self, machine, monkeypatch, project_dir, capsys
    ):
        prefix = project_dir / "conda-env"
        monkeypatch.setattr("optica.cli.setup.sysinfo.running_in_conda", lambda: True)
        monkeypatch.setattr("optica.cli.setup.sysinfo.conda_prefix", lambda: prefix)
        code = app.invoke_guarded(["setup", "--no-extras"])
        assert code == ExitCode.SUCCESS
        # `none — installing into system Python` would be false here, which is
        # the bar the plan holds itself to.
        assert f"Conda: {prefix} (active)" in capsys.readouterr().err

    def test_an_active_environment_optica_is_not_in_is_a_hard_error(
        self, machine, monkeypatch, project_dir, capsys
    ):
        elsewhere = project_dir / "someone-elses-env"
        monkeypatch.setattr(
            "optica.cli.setup.sysinfo.declared_venv", lambda: elsewhere
        )
        code = app.invoke_guarded(["setup", "--no-extras"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "Optica is not installed in it" in err
        assert str(elsewhere) in err
        assert "pip install optica" in err

    def test_it_is_a_hard_error_interactively_too(
        self, machine, monkeypatch, project_dir, interactive, capsys
    ):
        monkeypatch.setattr(
            "optica.cli.setup.sysinfo.declared_venv", lambda: project_dir / "other"
        )
        assert app.invoke_guarded(["setup", "--upgrade"]) == ExitCode.ERROR
        assert "Optica is not installed in it" in capsys.readouterr().err

    def test_exactly_one_found_is_confirmed_before_use(
        self, machine, project_dir, interactive, monkeypatch, capsys
    ):
        path = _venv(project_dir)
        asked = _answers(monkeypatch, "y", "n", "n", "n", "", "y")
        code = app.invoke_guarded(["setup"])
        assert code == ExitCode.SUCCESS, capsys.readouterr().err
        assert any("not currently active. Install into it?" in t for t in asked)
        assert f"Venv: {path} (detected (not active))" in capsys.readouterr().err

    def test_more_than_one_found_is_listed_and_picked(
        self, machine, project_dir, interactive, monkeypatch, capsys
    ):
        _venv(project_dir, ".venv")
        second = _venv(project_dir, "env311")
        _answers(monkeypatch, "2", "n", "n", "n", "", "y")
        code = app.invoke_guarded(["setup"])
        assert code == ExitCode.SUCCESS, capsys.readouterr().err
        # Name-sorted: `.venv` then `env311`, so 2 is the second.
        assert f"Venv: {second}" in capsys.readouterr().err


class TestNonInteractiveEnvironment:
    def test_none_found_is_a_hard_error_naming_the_fix(
        self, machine, project_dir, capsys
    ):
        code = app.invoke_guarded(["setup", "--no-extras"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "No virtual environment found" in err
        assert "python -m venv .venv" in err

    def test_more_than_one_found_is_a_hard_error(self, machine, project_dir, capsys):
        _venv(project_dir, ".venv")
        _venv(project_dir, "env311")
        code = app.invoke_guarded(["setup", "--no-extras"])
        assert code == ExitCode.ERROR
        assert "2 virtual environments found" in capsys.readouterr().err

    def test_a_single_one_is_used_without_confirmation(
        self, machine, project_dir, monkeypatch, capsys
    ):
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a non-interactive setup must not prompt")

        monkeypatch.setattr("typer.prompt", forbidden)
        monkeypatch.setattr("typer.confirm", forbidden)
        path = _venv(project_dir)
        assert app.invoke_guarded(["setup", "--no-extras"]) == ExitCode.SUCCESS
        assert str(path) in capsys.readouterr().err


class TestCreateNameCollision:
    def test_an_existing_directory_is_rejected_and_re_asked(
        self, machine, project_dir, interactive, monkeypatch, capsys
    ):
        (project_dir / "taken").mkdir()
        asked = _answers(monkeypatch, "Y", "taken", "fresh", "n", "n", "n", "", "y")
        code = app.invoke_guarded(["setup"])
        assert code == ExitCode.SUCCESS, capsys.readouterr().err
        err = capsys.readouterr().err
        assert "taken/ already exists but is not a virtual environment" in err
        assert asked.count("Name for the new environment") == 2
        assert "(created)" in err

    def test_force_does_not_bypass_it(
        self, machine, project_dir, interactive, monkeypatch, capsys
    ):
        (project_dir / ".venv").mkdir()
        _answers(monkeypatch, "Y", ".venv", "other", "n", "n", "n", "", "y")
        code = app.invoke_guarded(["setup", "--force"])
        assert code == ExitCode.SUCCESS, capsys.readouterr().err
        err = capsys.readouterr().err
        assert "already exists but is not a virtual environment" in err


class TestHardwareSafetyPrompts:
    @pytest.fixture
    def cuda(self, machine):
        machine["gpu"] = sysinfo.GPUInfo(
            sysinfo.Accelerator.CUDA,
            name="NVIDIA RTX 3080",
            cuda_version="13.0",
            description="CUDA-capable GPU (NVIDIA RTX 3080, CUDA 13.0)",
        )
        return machine

    def test_cpu_requested_on_a_cuda_machine_auto_aborts_unattended(
        self, cuda, project_dir, capsys
    ):
        _venv(project_dir)
        code = app.invoke_guarded(["setup", "--include-extras", "torch-cpu"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "may limit performance" in err
        assert "optica setup --include-extras torch-auto" in err

    def test_gpu_requested_without_one_auto_aborts_unattended(
        self, machine, project_dir, capsys
    ):
        # Constructed: this machine has a CUDA GPU, so the probe is replaced.
        _venv(project_dir)
        code = app.invoke_guarded(["setup", "--include-extras", "torch-gpu"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "No CUDA-capable GPU detected" in err
        assert "will fail at runtime" in err
        assert "optica setup --include-extras torch-cpu" in err

    def test_force_suppresses_the_prompt_and_the_abort_with_it(
        self, machine, project_dir, capsys
    ):
        _venv(project_dir)
        code = app.invoke_guarded(
            ["setup", "--include-extras", "torch-gpu", "--force"]
        )
        assert code == ExitCode.SUCCESS, capsys.readouterr().err

    def test_torch_auto_fires_no_safety_prompt_either_way(
        self, cuda, project_dir, capsys
    ):
        _venv(project_dir)
        code = app.invoke_guarded(["setup", "--include-extras", "torch-auto"])
        assert code == ExitCode.SUCCESS, capsys.readouterr().err

    def test_the_review_names_the_detected_hardware(self, cuda, project_dir, capsys):
        _venv(project_dir)
        app.invoke_guarded(["setup", "--include-extras", "torch-auto"])
        assert "NVIDIA RTX 3080" in capsys.readouterr().err


class TestInstallCommands:
    def test_the_torch_stack_takes_two_commands_not_one(
        self, machine, project_dir, capsys
    ):
        # `timm` and `scikit-learn` are absent from download.pytorch.org and
        # --index-url replaces PyPI, so one command cannot install all four.
        _venv(project_dir)
        machine["gpu"] = sysinfo.GPUInfo(
            sysinfo.Accelerator.CUDA, cuda_version="13.1", description="CUDA GPU"
        )
        app.invoke_guarded(
            ["setup", "--include-extras", "torch-auto", "--exclude-extras", "web"]
        )
        commands = _pip(machine)
        assert len(commands) == 2
        indexed, from_pypi = commands
        assert "--index-url" in indexed
        assert indexed[indexed.index("--index-url") + 1].endswith("/cu130")
        assert indexed[-2:] == ["torch", "torchvision"]
        assert "--index-url" not in from_pypi
        assert from_pypi[-2:] == ["timm", "scikit-learn"]

    def test_no_extra_index_url_is_ever_passed(self, machine, project_dir):
        _venv(project_dir)
        app.invoke_guarded(["setup", "--include-extras", "torch-cpu", "--force"])
        for command in _pip(machine):
            assert "--extra-index-url" not in command

    def test_torch_cpu_uses_the_cpu_index(self, machine, project_dir):
        _venv(project_dir)
        app.invoke_guarded(
            ["setup", "--include-extras", "torch-cpu", "--exclude-extras", "web"]
        )
        [indexed, _] = _pip(machine)
        assert indexed[indexed.index("--index-url") + 1].endswith("/cpu")

    def test_a_pip_extra_is_one_command(self, machine, project_dir):
        _venv(project_dir)
        app.invoke_guarded(
            ["setup", "--include-extras", "web", "--exclude-extras", "torch"]
        )
        assert _pip(machine) == [
            [str(sysinfo.venv_python(project_dir / ".venv")), "-m", "pip", "install",
             "optica[web]"]
        ]

    def test_it_installs_into_the_resolved_environment_not_the_running_one(
        self, machine, project_dir
    ):
        path = _venv(project_dir)
        app.invoke_guarded(
            ["setup", "--include-extras", "web", "--exclude-extras", "torch"]
        )
        assert _pip(machine)[0][0] == str(sysinfo.venv_python(path))


class TestIdempotence:
    def test_an_installed_set_is_skipped_silently(self, machine, project_dir, capsys):
        _venv(project_dir)
        machine["installed"] = {
            "torch": "2.14.0+cu130",
            "torchvision": "0.29.0+cu130",
            "timm": "1.0.29",
            "scikit-learn": "1.9.1",
        }
        code = app.invoke_guarded(
            ["setup", "--include-extras", "torch-auto", "--exclude-extras", "web"]
        )
        assert code == ExitCode.SUCCESS
        assert _pip(machine) == []
        assert "already up to date" in capsys.readouterr().out

    def test_the_review_marks_each_package_already_installed(
        self, machine, project_dir, capsys
    ):
        _venv(project_dir)
        machine["installed"] = dict.fromkeys(("torch", "torchvision", "timm"), "1.0")
        app.invoke_guarded(["setup", "--include-extras", "torch-auto"])
        err = capsys.readouterr().err
        assert "already installed" in err
        assert "will install" in err  # scikit-learn is absent

    def test_an_incompatible_pairing_reaches_the_repair_state(
        self, machine, project_dir, monkeypatch, capsys
    ):
        _venv(project_dir)
        machine["installed"] = dict.fromkeys(("torch", "torchvision"), "1.0")
        monkeypatch.setattr(
            "optica.cli.setup.sysinfo.pairing_problem",
            lambda: "torchvision 0.29.0 requires torch 2.14.0, but torch 2.1.0 "
            "is installed",
        )
        app.invoke_guarded(["setup", "--include-extras", "torch-auto"])
        assert "repair" in capsys.readouterr().err


class TestReview:
    def test_it_is_printed_non_interactively_and_asks_nothing(
        self, machine, project_dir, monkeypatch, capsys
    ):
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("the Review's prompt is omitted when non-interactive")

        monkeypatch.setattr("typer.confirm", forbidden)
        _venv(project_dir)
        app.invoke_guarded(["setup", "--all-extras"])
        err = capsys.readouterr().err
        assert "Optica Setup — Review" in err
        assert "Proceed with installation?" not in err

    def test_the_total_is_the_plans_own_figure(self, machine, project_dir, capsys):
        _venv(project_dir)
        app.invoke_guarded(["setup", "--all-extras"])
        # torch-auto + web + clip, the plan's worked Review.
        assert "Total download: ~0.9–3.1GB" in capsys.readouterr().err

    def test_no_extras_selected_says_so(self, machine, project_dir, capsys):
        _venv(project_dir)
        app.invoke_guarded(["setup", "--no-extras"])
        err = capsys.readouterr().err
        assert "none selected" in err
        assert "Total download: none selected" in err

    def test_a_skipped_api_key_is_shown_explicitly(self, machine, project_dir, capsys):
        _venv(project_dir)
        app.invoke_guarded(["setup", "--no-extras"])
        assert "— skipped" in capsys.readouterr().err

    def test_the_transitive_torch_line_appears_for_clip_alone(
        self, machine, project_dir, capsys
    ):
        _venv(project_dir)
        app.invoke_guarded(
            ["setup", "--include-extras", "clip", "--exclude-extras", "torch,web"]
        )
        err = capsys.readouterr().err
        assert "Plus the torch stack open-clip-torch pulls in" in err
        # Never folded into the total: the sum stays a sum of what was selected.
        assert "Total download: ~600MB" in err

    def test_it_does_not_appear_when_a_variant_is_selected(
        self, machine, project_dir, capsys
    ):
        _venv(project_dir)
        app.invoke_guarded(["setup", "--all-extras"])
        assert "pulls in" not in capsys.readouterr().err


class TestCompletion:
    def test_a_failed_extra_is_counted_as_an_extra_not_a_package(
        self, machine, project_dir, capsys
    ):
        _venv(project_dir)
        machine["returncode"] = 1
        code = app.invoke_guarded(
            ["setup", "--include-extras", "clip", "--exclude-extras", "torch,web"]
        )
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "Setup incomplete — 1 extra failed." in err
        assert "CLIP filtering failed to install." in err
        assert "Affected: optica fetch --mode clip, optica run --mode clip" in err
        assert "optica setup --include-extras clip" in err

    def test_the_activation_command_leads_when_the_target_is_not_active(
        self, machine, project_dir, capsys
    ):
        path = _venv(project_dir)
        app.invoke_guarded(["setup", "--no-extras"])
        out = capsys.readouterr().out
        assert "Activate the environment before using Optica:" in out
        assert str(path) in out

    def test_feature_availability_rather_than_a_binary_state(
        self, machine, project_dir, capsys
    ):
        _venv(project_dir)
        app.invoke_guarded(["setup", "--no-extras"])
        out = capsys.readouterr().out
        assert "Core pipeline:" in out
        assert "Browser UI:" in out
        assert "CLIP filtering:" in out

    def test_a_stack_present_but_not_installed_by_setup_says_so(
        self, machine, project_dir, capsys
    ):
        _venv(project_dir)
        machine["installed"] = {"torch": "2.14.0+cu130"}
        app.invoke_guarded(["setup", "--exclude-extras", "torch"])
        assert "present, not installed by setup" in capsys.readouterr().out


class TestApiKeys:
    def test_a_key_typed_at_the_prompt_reaches_the_global_config(
        self, machine, project_dir, interactive, monkeypatch, fake_home
    ):
        _venv(project_dir)
        _answers(monkeypatch, "y", "n", "n", "n", "abc123", "y")
        assert app.invoke_guarded(["setup"]) == ExitCode.SUCCESS
        written = (fake_home / ".optica" / "config.toml").read_text(encoding="utf-8")
        assert "abc123" in written

    def test_skip_keys_asks_nothing(
        self, machine, project_dir, interactive, monkeypatch, fake_home
    ):
        _venv(project_dir)
        asked = _answers(monkeypatch, "y", "n", "n", "n", "y")
        app.invoke_guarded(["setup", "--skip-keys"])
        assert not any("FLICKR" in text for text in asked)

    def test_enter_preserves_an_existing_value(
        self, machine, project_dir, interactive, monkeypatch, fake_home
    ):
        target = fake_home / ".optica" / "config.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('flickr_api_key = "kept"\n', encoding="utf-8")
        _venv(project_dir)
        _answers(monkeypatch, "y", "n", "n", "n", "", "y")
        app.invoke_guarded(["setup"])
        assert "kept" in target.read_text(encoding="utf-8")


class TestEnvironmentKinds:
    def test_the_label_follows_the_kind(self):
        from optica.cli.setup import Environment

        venv = Environment(EnvKind.VENV, Path("/x/.venv"), "created")
        conda = Environment(EnvKind.CONDA, Path("/x/env"), "active", active=True)
        system = Environment(EnvKind.SYSTEM, None, "none — installing into system Python")
        assert venv.line.startswith("Venv: ")
        assert conda.line.startswith("Conda: ")
        assert system.line == "none — installing into system Python"
