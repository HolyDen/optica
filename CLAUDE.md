# Optica — implementation instructions

Optica is a Python package for image classification via transfer learning: a CLI
and a Python API over a fetch → label → curate → train → export pipeline. There
is no source code yet. This file governs how it gets written.

## The specification

`spec/optica-plan-v1-core.md` is the specification — 1781 lines. Read the
sections relevant to the current pass before writing code for that pass.

**The plan wins.** Every other document — anything under `notes/`, anything
found outside the repo, anything in this file that appears to contradict it — is
derived from the plan or records reasoning about it. A derived artifact is not
an authority over the thing it was derived from.

**The plan is not a source of facts about the world.** See the next section.

**The plan is read-only.** `spec/` is denied to the Edit and Write tools. If
verification contradicts it, stop, write the proposed change to
`notes/build-log.md`, and report. Do not route around it silently, and do not
edit the specification to match what you found — that inverts the authority
this file exists to establish.

## Verify external facts before code depends on them

Checked against the outside world in September 2026, six of the plan's factual
claims were wrong. Four rounds of review had missed all six, because every round
checked the document against itself. Those six are fixed. The discipline is what
matters now.

Before writing code that depends on any of the following, check the source:

- a URL or a host
- an API's terms, pricing, or access requirements
- a package version, or what a package declares in its own metadata
- a download size
- a support or end-of-life window
- a column name, schema, or field in someone else's dataset

Two rules earned the same day:

- **Sweep for what should no longer be there, not for what you meant to
  change.** A correction pass named three stale sites; the residual sweep found
  six.
- **Print the breakdown, not the total.** A computed figure came back plausible,
  in range, and wrong by 80%, because a wheel picker had silently chosen the
  wrong architecture. Only the per-item table exposed it.

Record every check in `notes/verified.md` with the date and the command or URL
that produced it. Facts recorded there are reusable by later passes. Facts held
only in conversation are not — they do not survive compaction.

## When the plan doesn't specify something

Two modes, and the difference matters because most passes run unattended.

**Before a pass starts:** if something foundational is missing or unclear, stop
and ask. Nothing has been built on top of it yet, so pausing is cheap and
appropriate.

**Once code-writing is underway:** do not hard-stop for every gap. A hard stop
in an unattended run can sit unnoticed for an unknown length of time — the
opposite of what the run is for. Make the most reasonable assumption, flag it
clearly, keep building, and record it in `notes/build-log.md`: what was missing,
what was assumed, where, and why. **The decision is never silent, even when it
isn't a stop.** Silence, not forward motion, is the risk to guard against.

**One exception:** a mid-build gap that is itself foundational — where
continuing means building substantially on an unresolved question rather than
filling in one local detail — is treated like a pre-start gap. Stop. If
genuinely unsure which mode applies, log and continue: a log can be read
afterwards, and a stop cannot be un-paused by anyone who doesn't know it
happened.

## Build order

**Do not invent a build order.** The plan names the first task twice: the
**global Typer exception handler** is a hard sequencing prerequisite and ships
before any other CLI work, because every other flag decision's error behaviour
executes through it.

The work is split into six passes. Each pass opens with a message stating its
number and scope. Do not build outside the current pass's scope; note anything
that looks urgent in `notes/build-log.md` and leave it for its own pass.

| Pass | Scope | Done when |
|---|---|---|
| 0 | The four verification tasks below; place `pyproject.toml` | Four answers in `notes/verified.md` |
| 1 | `exceptions.py`, `utils/`, `config/`, CLI skeleton, **global Typer handler**, exit codes, minimal `ci.yml` | `pip install -e .` then `optica --version` works with no torch installed |
| 2 | `input/` except `clip.py` — class-name rules, blocklist, manifest, validation, sessions | `optica fetch` runs end to end |
| 3 | `server/` — FastAPI app, routes, both pages, shared JS/CSS | `optica label` and `optica curate` run |
| 4 | `training/`, `export/`, `input/clip.py` | `optica train` and `optica export` run |
| 5 | `api/simple.py`, `api/classifier.py`, `cli/setup.py`, the registries | `optica.run()` and `optica setup` work |
| 6 | Full CI matrix, `README.md`, `CHANGELOG.md`, version classifiers | Matrix is valid YAML; README and CHANGELOG complete |

## How each pass works

**Branch.** All passes work on `build/v0.2.0`. Never commit to `main`.

**Python 3.11**, the declared floor. Building on the floor turns a 3.12-only
construct into an immediate syntax error rather than a bug that only 3.11 users
see.

**Commit per coherent unit** — a module together with its test stub. Not per
file, not per pass. Conventional Commits, module as scope, two lines of body:

```
feat(cli): add global Typer exception handler

Implements plan § "Exceptions".
Pass: 1
```

Reference plan sections by heading, not by line number: headings survive edits.

**Windows is the development platform, and the plan names it best-effort** —
Linux and macOS are its primary targets. CI on Ubuntu is therefore the only
Linux check there is, it runs from pass 1 onward, and it must not be left red.
Two consequences for how code gets written: the venv lives at `.venv/Scripts`,
not `.venv/bin`, and every path goes through `pathlib.Path` — never string
concatenation, never a hardcoded separator. NTFS is case-insensitive, so
anything depending on case distinctness is exercised only in CI.

**Every pass ends Ruff-clean and mypy-clean.** Type debt fixed five passes later
ripples back through modules nobody has in context any more.

**If a pass's milestone isn't met:** fix it, within the pass's scope. If it
still isn't met, stop, write the state to `notes/build-log.md`, and report. Do
not begin the next pass's work.

## Pass 0 — verification

Four external facts could not be checked in the environment that prepared this
repo, and they gate code that follows. They are spelled out in
`notes/passes/pass-0.md` and their answers belong in `notes/verified.md`. Do not
write code that depends on any of them before they are answered.

## Settled points that the plan leaves implicit

**Declined prompts exit `3`; `click.Abort` exits `130`.** Optica handles an `N`
answer itself and returns `3`. `click.Abort` is reserved for an interrupt at a
prompt and joins SIGINT at `130`. **Do not use `confirm(..., abort=True)`** — it
raises `Abort` for both cases and would return `130` where the exit-code table
requires `3`. This lands in pass 1 and every later command inherits it.

**Core is exactly six packages.** Do not add `click` or `pydantic` to the
dependency list. `pydantic` arrives transitively through `pydantic-settings` — confirmed
2026-09-13, `pip show pydantic` reports `Required-by: pydantic-settings`.
`click` does **not**: Typer vendors it as the private `typer._click` and
declares no dependency, so `import click` fails in a Core install. Use
`typer`'s equivalents — `typer.testing`, `typer._click.exceptions` — never
`click.*`. Adding real Click would install a second `UsageError` class
alongside the vendored one, and every `except` would silently stop firing.
**Never rely on Click's absence.** Real Click reaches the environment by more
than one route — uvicorn brings it with `optica[web]`, and `huggingface_hub`
brings it with the torch stack — and any dependency bump can add another. Where
it is present `import click` **succeeds** and the mistake stops being loud: a
mistaken `except click.UsageError` compiles, runs, and silently never fires,
because Typer still raises the vendored `typer._click` one. Do not write code
whose correctness depends on which route installed what. Use `typer`'s
equivalents unconditionally.

## Tests

`tests/unit/` mirrors the source tree; `tests/integration/` for cross-module
flows; `tests/conftest.py` holds synthetic `pretrained=False` fixtures.

Each pass writes the test files for the modules it built. A test file opens by
naming the plan sections it covers. Where the plan states an expected value —
split arithmetic, phase allocation, the `--yes` table rows, `clip_threshold`
bands, exit codes, collision suffixes, error message text — transcribe it into a
stub now, marked `@pytest.mark.skip(reason="stub — pass N")`. These are free
test cases while the code is being written and expensive archaeology later.

Anything specified but not obviously testable gets `# TODO(test): <what>` in the
source, so one grep produces the post-implementation worklist.

`@pytest.mark.slow` goes on anything importing torch, from the start. CI never
installs the torch stack.

## Working files

- **`notes/verified.md`** — facts checked against the world. Small, durable,
  read at the start of every pass. Date and source for each entry.
- **`notes/build-log.md`** — append-only. Assumptions logged under the gap rule
  above, and a line at each pass boundary saying where it stopped.

Neither is a specification. Neither is authority over the plan.

## Hard don'ts

- **Do not change `version` in `pyproject.toml`.** `0.1.0` and `0.1.1` are
  published placeholders and permanently consumed. It says `0.1.1` on purpose,
  so that an accidental build-and-upload fails as a duplicate rather than
  burning `0.2.0`. A human bumps it at ship time.
- **Never read, print, or commit `.env`.**
- **`README.md` belongs to pass 6.** Do not update it in an earlier pass, however
  stale it looks.
- **Run smoke checks inside `.smoke/`**, not at the repo root. Optica does not
  gitignore `./dataset/`, and `git add` is allowed.
- **Never `git push`. Never publish to PyPI.**
- Commit as you go, always with `git commit -m`. A bare `git commit` opens an
  editor and will hang an unattended pass.
