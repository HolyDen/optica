# Pass 1 — Foundation

## Read
`spec/optica-plan-v1-core.md` §§ "Code Structure", "Exceptions", "Coding Style",
"CLI Layer & Conventions", "Configuration", "CLI Flag Reference (V1)".
Also `notes/verified.md`.

## Build
- `src/optica/exceptions.py`
- `src/optica/utils/`
- `src/optica/config/`
- `src/optica/cli/main.py` and the `classify` skeleton
- `tests/conftest.py` and `tests/unit/` mirroring what you build
- `.github/workflows/ci.yml` — **minimal only**: checkout, set up Python 3.11,
  `pip install -e .[test]`, `ruff check`, `mypy`, `pytest -m "not slow"`.
  on `ubuntu-latest`, `macos-latest` and `windows-latest`; single
  Python version for now. **Trigger on pushes to any branch, not only `main`** —
  implementation happens on `build/v0.2.0` and is pushed at each pass boundary,
  so a `main`-only trigger would mean CI never runs during the build. No version
  matrix and no `optica setup` step yet —
  pass 6 adds both. Three runners from the start because development happens
  on Windows, so Linux and macOS get no local coverage at all, and Windows
  filesystem behaviour (reserved device names, trailing dots, path length)
  differs from both.
- Extend `.gitattributes` — which already carries `spec/*.md -text` — with
  `* text=auto eol=lf`, now that there is source code for it to govern. Three
  CI runners and a Windows dev machine otherwise disagree about line endings.

**The global Typer exception handler comes first.** The plan names it twice as a
hard sequencing prerequisite: every other command's error behaviour executes
through it.

## Remember
A declined prompt exits `3`. `click.Abort` exits `130`. **Do not use
`confirm(..., abort=True)`** — it raises `Abort` for both cases.

## Out of scope
`input/`, `server/`, `training/`, `export/`, `api/`, `cli/setup.py`.

## Done when
`pip install -e .` then `optica --version` works with no torch installed, and
each of exit codes 0, 1, 2, 3 and 130 is reachable and covered by a test stub.
The workflow file is valid YAML; the human pushes and confirms it runs green
on Ubuntu before pass 2 starts.
