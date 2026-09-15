# Optica — V1-Core Plan

*The single implementation-ready specification for Optica's first shipped release (V1). Material deferred to V1-fast-follow or later — ONNX export, REST export, the `--strict` posture flag, and the post-V1 roadmap — is deliberately absent and lives elsewhere.*

*"V1" throughout means **first ship** — the `0.2.0` release — not a 1.0 maturity milestone.*

---

## Part I — Orientation

### Project Overview

**What:** Optica is an open-source Python package for computer vision tasks using pretrained models. It provides a simple, opinionated toolkit that handles the full pipeline — from image sourcing to model export — so users can build classifiers without deep ML expertise.

V1 delivers **image classification only**, but the surface is task-namespaced from the first release (see Python API), so the vocabulary already accommodates future task types without restructuring.

**For whom:** Developers at all levels — from beginners who want a working model in a few CLI commands, to advanced users who need full programmatic control. The five documentation tiers (Quick Start → CLI → Simple API → Python API → Classifier) give that range an explicit structure. Scales from hobbyist projects to production **models** — what scales is the model Optica produces, which is deployable anywhere PyTorch runs. **Optica itself is a single-machine, single-user tool**: one write command at a time behind a global lock, one curation session, a localhost-only browser server. It is designed to be *scripted* — exit codes, `--ci`, `--yes` and structured results all exist for unattended runs — but not to be *deployed*.

**Why:** Setting up a transfer-learning pipeline from scratch requires assembling many libraries, writing boilerplate, and making dozens of non-obvious decisions. Optica makes that a single command. It also solves the data problem: users often don't have training images, so **Optica can fetch and curate them automatically.** This claim is load-bearing — it is why the fully non-interactive acquisition path (clip mode) is core rather than optional.

**V1 scope:** Image classification. Local CPU + GPU training. **Three input modes** — label (user-provided images + browser labeling), curate mode (fetch + browser curation), clip mode (fetch + CLIP auto-filter). **One export format in V1: PyTorch `.pt`.** ONNX and REST export are fast-follow additions immediately after V1; the `--format` flag and `export_format` config key arrive with them, so V1 `optica export` always produces `model.pt` with no format selection.

> *Accepted scope framing:* the three input modes ship together in V1 because all three are adapters onto the one pipeline and the automatic-acquisition promise depends on clip mode. Export is asymmetric by design — one format at first ship, more immediately after — because `pt` is the smallest, most portable artifact and never fails on a missing optional dependency.

**Distribution:** PyPI only. `pip install optica`. Apache-2.0 license. Python 3.11–3.13 (not 3.14 — see Tech Stack).

**Package variants (V1):**
- `pip install optica` — lightweight Core (**6 packages**; see Tech Stack).
- `pip install optica[clip]` — adds `open-clip-torch` for clip mode. `open-clip-torch` declares `torch`, `torchvision` and `timm` unconditionally, so this extra pulls them from the default index too — see Tech Stack.
- `pip install optica[web]` — adds FastAPI + uvicorn for `optica label`, `optica curate`, and `optica run` in label or curate mode (REST export travels with the ONNX/REST fast-follow).
- `pip install optica[all]` — in V1 resolves to **`web` + `clip`** (the ONNX extra ships with the fast-follow). Grows as new feature extras are added.

Heavy ML packages (torch, torchvision, timm, scikit-learn) are **not** pip extras of Optica's own and are not installed by a bare `pip install optica`. Three of them — torch, torchvision, timm — are nonetheless reachable through `optica[clip]`, which `open-clip-torch` pulls them into. All four are handled by `optica setup`, which owns them because of the torch index-URL constraint — see Tech Stack and `optica setup`.

---

### Project Identity

- **Package name:** Optica
- **PyPI:** `pypi.org/project/optica` — secured. Placeholder releases `0.1.0` and `0.1.1` are already published; PyPI never permits a version number to be reused, even after deletion, so both are permanently consumed.
- **GitHub:** `github.com/HolyDen/optica` — live
- **License:** Apache-2.0
- **Python:** 3.11–3.13 (`requires-python = ">=3.11"`, with 3.14 explicitly not a V1 target — see Tech Stack)
- **Versioning:** semver — PATCH for bug fixes, MINOR for new features, MAJOR for breaking changes. **The first shipped release is `0.2.0`.** Remaining in `0.x` is deliberate rather than incidental: while the major version is zero, semver permits a minor bump to break compatibility, which keeps the CLI and API surface adjustable through early real-world use. `1.0.0` follows once that surface is confirmed by actual usage — the asymmetry matters, since `0.x → 1.0.0` is a milestone while `1.0.0 → 2.0.0` weeks after launch is a correction. *Python packaging follows PEP 440, not semver; for plain `X.Y.Z` releases the two are identical, diverging only on pre-release spellings (`1.0.0a1`, not `1.0.0-alpha.1`).* The dependency-bound strategy (Tech Stack) relies on upstream projects honoring semver.
- **Repo layout:** `src/` layout, Hatchling build backend
- **Platform support:** Linux and macOS are primary targets. Windows is best-effort for V1 — covered by CI, but not a primary target: regressions there are fixed on a best-effort basis rather than blocking a release. (Case-insensitive class-name collision handling in the labeling UI exists specifically to protect Windows/macOS filesystems.)
- **CI/CD:** GitHub Actions only. On every push/PR: pytest, Ruff, mypy — run as a **version matrix** across the minimum and maximum declared versions of **what each leg installs**, which is Core plus `optica[test]` (see Tech Stack for what the matrix does not reach; this supersedes any single-job description). The torch stack is unpinned and therefore outside the matrix, and is never installed in CI.

---

### Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| ML Framework | PyTorch + torchvision + timm | timm chosen over the torchvision model zoo for its unified `create_model()` API |
| CLI | Typer + Rich | Type-hint-driven CLI, pairs with mypy |
| Browser UI | FastAPI + vanilla HTML/JS | No frontend dependencies; FastAPI is reused for REST export (fast-follow) |
| HTTP Client | httpx | Sync + async in one library |
| Image Processing | Pillow + torchvision transforms | Pillow for format/corruption handling, torchvision for augmentation |
| CLIP | open-clip-torch | Actively maintained, better benchmarks than OpenAI's release. Optional — clip mode only, installed via `optica[clip]` |
| Configuration | python-dotenv + pydantic-settings | Type-safe config validation. python-dotenv handles `.env` discovery; pydantic-settings handles validation |
| Logging (user) | Rich | Progress bars, colored output, status messages |
| Logging (internal) | Python standard `logging` | Per-module loggers, capturable by external tools |
| Data Splitting | scikit-learn | `train_test_split` |
| Code Quality | Ruff + mypy | Linting, formatting, type checking |
| Testing | pytest | Unit + integration tests |

*(ONNX and REST export are not part of V1 — they arrive as a fast-follow, together with `torch.onnx`/`onnx`/`onnxruntime` and the `optica[onnx]` extra.)*

#### Dependency taxonomy — three tiers

Dependencies are organized by **how they install**, not by which task needs them (task relevance is answered by the extras table below). The taxonomy is task-agnostic and stable across future task types.

| Tier | Name | Criterion | V1 members |
|---|---|---|---|
| 1 | **Core** | Required for `pip install optica` to be minimally functional | `typer`, `rich`, `python-dotenv`, `pydantic-settings`, `httpx`, `Pillow` |
| 2 | **Extras** | Standard PyPI, no hardware detection, feature-gated behind named pip extras | `FastAPI`, `uvicorn`, `open-clip-torch` — which declares `torch`, `torchvision` and `timm` unconditionally, so `optica[clip]` installs three Tier 3 packages from the default index with no hardware detection (`onnx`, `onnxruntime` join with the ONNX fast-follow) |
| 3 | **Platform-dependent** | Hardware-aware install via `optica setup` | `torch`, `torchvision`, `timm`, `scikit-learn` |

**Core is 6 packages**, not 5: `Pillow` is Core because `optica fetch` needs it unconditionally for image validation — a functional requirement, not a packaging preference.

#### Package install split

`pip install optica` installs only Core: `typer`, `rich`, `python-dotenv`, `pydantic-settings`, `httpx`, `Pillow`.

`optica setup` installs the four **Platform-dependent** packages into the resolved environment: `torch`, `torchvision`, `timm`, `scikit-learn`. (`Pillow` is Core, not a setup package — fetch needs it unconditionally for image validation. FastAPI and uvicorn live in `optica[web]`; onnx and onnxruntime in `optica[onnx]`, fast-follow. scikit-learn belongs in setup as training infrastructure, always installed alongside torch.)

**Why platform-dependent packages are not pip extras:** PyTorch requires different index URLs depending on hardware (CPU-only vs CUDA 12.6 vs CUDA 13.0). A `pyproject.toml` extras declaration cannot conditionally specify different index URLs — this must be done programmatically at runtime. `optica setup` detects hardware first, then constructs and runs the correct install command. This is a technical constraint specific to the torch stack, **not** a general "heavy packages" rule — it does not apply to FastAPI, uvicorn, onnx, or onnxruntime, which are exactly why those are ordinary pip extras.

#### Extras table (V1)

| Extra | User-facing? | Contains | Enables |
|---|---|---|---|
| `optica[web]` | Yes | `FastAPI`, `uvicorn` | `optica label`, `optica curate`, `optica run` in label or curate mode (REST export, fast-follow) |
| `optica[clip]` | Yes | `open-clip-torch` | clip mode |
| `optica[all]` | Yes | `web` + `clip` in V1 | everything shippable in V1 |
| `optica[test]` | **No** | `pytest`, `Ruff`, `mypy` | CI and local test runs |
| `optica setup` | — | `torch`, `torchvision`, `timm`, `scikit-learn` | training stack |

`optica[test]` is a lean, **non-user-facing** extra (named `test`, not `dev`). It exists because the CI version matrix (below) installs it once per matrix leg, so per-leg weight is real — it holds only the test toolchain. Docs tooling gets its own `[docs]` extra when the documentation site lands (fast-follow), rather than fattening this one.

#### Verified package versions (September 2026 snapshot)

`pyproject.toml` cannot be written without verified versions. This table is that verification; re-run it at implementation time (it is a listed item on the pre-implementation gate, since versions ship on a weeks-to-months cadence).

| Package | Latest stable | Notes |
|---|---|---|
| `torch` | 2.14.0 (Sep 2026) | Requires Python ≥ 3.10 |
| `torchvision` | 0.29.0 | Pairs with torch 2.14.0. Tabulated for orientation at this snapshot — 2.13↔0.28, 2.12↔0.27, 2.11↔0.26 — but the list is not the rule; see the derivation note below |
| `timm` | 1.0.29 | No restrictive torch pins — install torch first, then timm |
| `open-clip-torch` | 3.3.0 (Feb 2026) | Requires Python ≥ 3.9; depends on timm + torch |
| `fastapi` | 0.141.1 | Requires Python ≥ 3.10; uvicorn bundled via `fastapi[standard]` |
| `pydantic-settings` | 2.15.0 (Aug 2026) | Requires Python ≥ 3.10 |

*(`onnx` 1.22.0 and `onnxruntime` 1.29.0 are verified but attach to the ONNX fast-follow, not V1.)*

**Hard constraint:** FastAPI has dropped Pydantic v1 — **Pydantic ≥ 2.9.0 only.** Any design assuming Pydantic v1 is invalid.

**Python target:** 3.11–3.13. **3.10 is excluded: it reaches end of life on 31 October 2026**, so a 3.10 floor would ship V1 supporting a runtime that is already unsupported — and it pins those users to `scikit-learn` 1.7.2, since 1.8.0 raised its own floor to 3.11, while `onnxruntime` requires 3.11 outright and would block the ONNX fast-follow. Python 3.14 is supported by most packages but is still early — not the recommended V1 target. **PyPI is authoritative** over the GitHub table for torch/torchvision pairings, and the rule is **derived rather than tabulated**: torchvision declares an exact `torch==<version>` in its own distribution metadata, so the compatible pair is whatever the installed torchvision says it is — read locally through `importlib.metadata`, with **no network call at check time**. Under PEP 440 a public-version specifier ignores local labels, so `torch==2.14.0` is satisfied by a CUDA-index `2.14.0+cu130` and the check behaves identically on the CPU and CUDA paths. **The pairings tabulated above are illustrative at the snapshot date and are not the rule.**

#### Version-bound strategy

`pyproject.toml` pins `>=min, <next_major` for **every dependency it declares** — accepting patch and minor updates (typically compatible) while blocking major breaks (typically breaking).

- `min` = the verified version **rounded down to minor** (e.g. a dependency at `1.0.22` → `>=1.0`). This deliberately claims a range slightly wider than anything actually run.
- `next_major` = the next integer major (e.g. a dependency at `1.x` → `<2.0`).
- **FastAPI is pre-1.0** — ceiling is `<1.0`. Revisit once FastAPI reaches 1.0 (flagged for the pre-implementation gate).
- **Concrete bound values are deferred to the pre-implementation gate**, since bounds derive from re-verified versions.

**torch is never a direct dependency in `pyproject.toml` in V1** — though it remains reachable transitively, through the `clip` extra declared there. `optica setup` owns torch installation; `OpticaTorchError` covers its absence; there is nothing to pin. (A future `optica[torch]` extra with bounds is post-V1, gated on the CUDA-variant complexity.)

**Keeping current:** Dependabot for automated update PRs; a **CI version matrix** testing the minimum *and* maximum declared versions of what it installs (not just latest — testing only latest can never catch use of an API absent in the lower bound); and changelog monitoring for the major dependencies (torch, FastAPI, open-clip-torch), since semantic breaks that don't trip a version constraint won't be caught automatically. The matrix verifies the declared range of **what each leg installs** — Core plus `optica[test]`, and `optica[web]` on at least one leg, under the `>=min, <next_major` bounds `pyproject.toml` sets — and its cost is two legs on a suite built to be fast. **At least one leg installs no extras at all**, since the suite passing with none present is what holds the import-time contract to account. **Two things it does not verify, and is not claimed to.** The torch stack: those four packages are deliberately unpinned, so there is no minimum to test against, and their compatibility is asserted by the pairing rule and checked at install time instead. The `clip` extra: `open-clip-torch` is declared and carries bounds, but no leg installs it — and it **cannot** be added, since it declares torch, torchvision and timm unconditionally and would drag the torch stack into CI. `FastAPI` and `uvicorn` were excluded on the same cost reasoning — installing a package the suite does not exercise verifies that its range resolves, not that its API works — and are installed once the suite exercises them.

> *Accepted limitation — the `requirements.txt` gap:* `optica setup` cannot be captured by `pip freeze > requirements.txt` in the way ordinary dependencies can — it is inherent to how pip handles platform-specific index URLs, and the ML ecosystem normalizes this pattern (PyTorch itself requires a separate install command). It is handled by documentation (the two-step install is explicit in README and docs) and by `OpticaTorchError`, whose message routes the user to `optica setup` rather than explaining the constraint (the message table is the specification for its wording). This is a known UX characteristic, **not** a flaw to engineer around in V1. An `OPTICA_TORCH_VARIANT` env var (name/semantics to confirm at implementation) lets Docker/CI users bake the torch variant into the environment rather than pass it as a flag.

---

## Part II — Architecture

### Core Principle

**Pipeline architecture.** All three input modes are adapters that feed the same training pipeline:

```
Input → Preprocess → Train → Evaluate → Export
```

The three modes — **label** (user-provided images + browser labeling), **curate** (fetch + browser curation), **clip** (fetch + CLIP auto-filter) — are the three adapters onto this one pipeline. "Full pipeline working end-to-end" is exactly what V1-core means, and clip mode is core because it is one of the three adapters and the only fully non-interactive one — with one exception: a blocklisted class name pauses for sub-term definition, which `--yes` cannot answer (the prompt has no safe default).

**`optica run` runs the pipeline from wherever the input already is; the step commands expose its user-facing stages individually.** `fetch`, `label`/`curate`, `train` and `export` each do one stage's work and stop, so a user enters the pipeline wherever their data already is and leaves it wherever their needs end — fetch and curate without training, train an existing dataset without fetching, export last week's checkpoint. `run` ends at export always, but where it *begins* is inferred from the invocation: given only classes it fetches, given `--folder` it labels, given an already-organized `--dataset` it short-circuits acquisition and begins at training. It never skips a stage in the middle; it starts later. So `run` and the step commands answer one question — how much of the pipeline do I need? — by different means: `run` infers the answer from the input, the step commands let the user state it. The mapping is deliberately not one-to-one: **Input** is served by `fetch` and by `label`/`curate`, because acquiring images and labeling them are separately useful, while **Preprocess** and **Evaluate** have no commands at all, being internal to the stages that own them. What follows from this is that a command accepts only input its own stage can act on; anything needing an earlier stage's work first is a precondition error, not an implicit hand-off. `optica run` is the only command that continues from one stage into the next.

---

### CLI Layer & Conventions

The CLI is a thin entry point: no business logic, it maps commands to components.

#### Commands

| Full | Alias | Purpose |
|---|---|---|
| `optica classify run` | `optica run` | Full workflow |
| `optica classify fetch` | `optica fetch` | Fetch images |
| `optica classify curate` | `optica curate` | Browser curation (curate mode) |
| `optica classify train` | `optica train` | Train model |
| `optica classify export` | `optica export` | Export model |
| `optica classify label` | `optica label` | Label a flat folder of images |
| `optica setup` | — | Machine-level initialization |
| `optica config` | — | Settings management |
| `optica config --init` | — | Project-local config initialization |
| `optica config --set key value` | — | Set a config key (e.g. `optica config --set epochs 20`) |
| `optica config --view` | — | Show resolved config with source annotations; flags keys still at built-in defaults |
| `optica config --clear-staging` | — | List and clear all staging contents (with confirmation) |

**Namespacing and aliases.** The canonical CLI form is `optica classify <command>`; the flat forms (`optica run`, `optica train`, …) are **permanent aliases**, never deprecated or removed. Alias resolution consults `default_task` rather than hardcoding `classify`, so post-V1 task types (e.g. `detect`) slot in without restructuring the CLI. `cli/classify.py` is fully self-contained — all classify-specific logic lives there; `cli/main.py` only registers the `classify` group and the flat aliases, holding nothing classify-specific. This makes `cli/classify.py` the clean template for a future `cli/detect.py`.

#### Global flags

`--verbose`, `--quiet`, `--yes`/`-y`, `--dry-run`, `--force`/`-f` — accepted in either position, applying to the full run.

*(`--strict` is **not** a V1 global flag — it is a fast-follow addition and does not ship in V1. `--verbose`/`--quiet` are position-independent.)*

**`--yes` / `-y`.** Answers **Y** to every Y/N prompt in its scope — this is "answers Y," not "accepts defaults": where a prompt's default is N, `--yes` still answers Y. It never picks a destructive option (a destructive auto-confirm requires a dedicated flag — `--overwrite`, for the `dataset/` overwrite prompt); where no safe Y exists (ambiguous input, missing required value), it raises a hard error rather than hanging. It splits by prompt category: **choice prompts** it answers; **safety prompts** it also answers, taking the continue option — `--force` is what *suppresses* those rather than answering them; **destructive prompts** it never touches, and each has its own dedicated flag or must be answered interactively. It **does not bypass browser curation** — for fully non-interactive pipelines, use `--mode clip`. It does not apply to `optica setup` (which is fully driven by its own flags; see `optica setup`). When blocklisted class names are present, the pipeline pauses for sub-term definition — the one prompt deliberately absent from the table below, since no answer can be defaulted — and `--yes` resumes answering the registered prompts after it, though the class-name confirmation still fires, `--yes` skipping it for clean cases only. **This pause is the general rule's prompting branch, not an exception to it:** in a non-prompting context the same prompt raises `OpticaValidationError` rather than blocking, the disposition the class-name prompt already takes.

`--yes` auto-picks, per prompt (V1):

| Prompt | `--yes` picks |
|---|---|
| Class-name confirmation (clean case) | Skip confirmation |
| Overlap warning | Y — continue |
| Group or separate sub-terms | Group |
| `optica config --init` create confirmation | Y — create |
| Fetch / curation / labeling interrupted → resume? | Resume |
| Training interrupted → continue? | Continue |
| `optica run` top-level R/C/S resume | R — resume |
| Mass rejection F/C/A | C — continue |
| Mass rejection C confirmation | Y — confirm |
| Checkpoint keep/archive/delete/select (K/A/D/S) | K — keep |
| Checkpoint soft-limit warning | Y — continue |
| Export checkpoint selection | Rank 1 (best) |
| `--output` container creation (single component, or multi-component with a trailing slash; path doesn't exist) | Y — create |
| CPU batch-size prompt | Y — continue |
| Class-imbalance warning (F/C/A, or C/A) | C — continue with auto class weighting |
| `--epochs 1` + default `finetune_ratio` | Y — continue |
| `clip_threshold` strict-end prompt (0.75 to <1.0) | Y — continue |
| `clip_threshold` warn-and-continue bands | Y — continue |
| Open Datasets soft-cap warning | Y — continue |
| `--classes`/subset confirmation (organized dataset) | Y — proceed with requested classes |

*(The checkpoint prompt offers four options — K/A/D/S — not three; corrected here. The export-conflict O/S/R/A row and the `--strict` four-option prompt row are absent from V1: the export-conflict prompt and `--strict` both travel to later releases.)*

**`--force` / `-f`.** Bypasses **safety prompts** only. A safety prompt fires when Optica detects that the user's explicit instruction may produce an unintended outcome — the test is *"if the user knew this, would they likely change their instruction?"* `--force` does **not** suppress warnings (they still display), does **not** override hard errors (unconditional by design), and does **not** reach **destructive prompts** — each of those carries its own dedicated flag, which for the `dataset/` overwrite prompt is `--overwrite`. **`--quiet` suppresses neither**: it silences progress and status output only, and warnings, prompts and errors display at every verbosity level (Implementation Note 19). A prompt that fired with nothing on screen would block on stdin invisibly, which is why the display flags stop short of it. `--force` differs from `--yes`, which answers choice and safety prompts rather than suppressing them, and is opposite in direction to the later `--strict`. Registered globally from V1 — same pattern as `--verbose`/`--quiet`/`--yes` — so that safety prompts added to commands in future need no flag re-registration. Canonical example: a hardware-mismatch safety prompt in `optica setup` (see `optica setup`).

**`--dry-run`.** Prints what would happen without executing. Applies to `optica fetch`, `optica train`, `optica export`, and `optica run`. Does **not** apply to `optica label`, `optica curate`, `optica setup`, or `optica config`.

#### Error handling and prompt conventions (standing rules)

These apply across the whole CLI surface and govern every command-specific behavior in Part II.

- **Global Typer exception handler — a hard sequencing prerequisite.** A global handler catches **`click.UsageError` at the base** — not a named list, since every parser error Typer raises is a `UsageError` subclass and a list goes stale the moment Click adds one — redirecting to prompts where applicable (`MissingParameter` on `--classes`) and producing clean wrapped errors otherwise. `click.Abort` is **not** a `UsageError` and is handled separately, exiting `130` alongside SIGINT. **It must be implemented before any other CLI work ships** — it is the mechanism every flag decision's error behavior executes through. A raw Typer traceback must never reach the user.
- **Flag (no value) behavior.** `--classes`/`-c` with no value surfaces the class-name prompt; `--output` with no value falls to its silent default `./optica-output/`; every other flag with no value produces a wrapped error with an example. Fallback hierarchy: try prompt → clean wrapped error → **never** a raw Typer traceback. Wherever the class-name prompt would fire, `--yes` errors rather than hanging on it. *(Stated as a condition rather than a list of commands: a command that later gains the prompt inherits the rule, and one that resolves classes without prompting — `train` against an existing `dataset/` — is never caught by it.)*
- **Validate all flag values upfront; report all invalid at once.** Never fail on the first invalid value only — a typo loop of fix-one-rerun-hit-the-next is a poor experience for any audience.
- **Fixed-value flags always list valid options in errors.** Applies to `--source`, `--mode`, `--model` (and, at fast-follow, `--format`). Include "Default: X" where applicable.
- **Integer flags reject non-integers** (strings, floats, booleans) with a clean wrapped error (using the default value in the example), via the global handler above — never a raw traceback.
- **Config-key validation mirrors flag validation**, run at **config-load time, before any command executes** — giving the split-sum and `clip_threshold` checks (see Configuration) a second enforcement point so a bad value in `.optica.toml` errors rather than misbehaving silently.
- **Output reports actual detected values, never internal shorthand.** Registry keys and variant names are *input* vocabulary (flags, prompts) only. Report `torch 2.14.0 (CUDA 13.0)`, not `torch-cu130`; `CUDA-capable GPU (NVIDIA RTX 3080)`, not `gpu`. Applies to every completion message, warning, and error string.
- **Copy-paste-ready command on correctable abort.** When a command aborts on a user-correctable condition, it outputs the full corrected command, reconstructed with only the relevant substitution and all other flags preserved — but **only** when reconstruction is unambiguous; if the fix needs judgment, it explains the problem instead of guessing a command.
- **Non-interactive flags and safety prompts.** Choice/extras prompts never fire non-interactively (the user already specified). Safety prompts still can — suppressed only by `--force`.
- **Conflict prompts fire before any action.** A prompt that fires after an action has begun is a design error — the damage precedes the question. The principle extends beyond prompts to any check whose answer is knowable before work begins: the dataset destination check, the per-file image validation stages, and the composite entry points' extras check all run before anything is written or any browser opens.
- **Export decisions apply equally to `optica run`.** Every export-step decision (naming, conflict handling, `--output`, checkpoint selection) applies to `optica run`'s export stage without being restated there. This is a standing propagation rule: a reader must carry export behavior into `run`, not treat the two as separate.

- **Value separator — comma, everywhere.** Every multi-value flag accepts comma-separated values (`--classes cat,dog`, `--checkpoint-rank 1,2,3`, `--include-extras web,clip`), and a repeated flag is equally valid (`-c cat -c dog`); the two compose, so `-c cat -c dog,bird` yields three classes. Values are trimmed of surrounding whitespace. **Prompt input follows the same convention** — the class-name prompt takes `cat,dog` and its example shows it, so a list is written one way whether typed as a flag or at a prompt. Multi-word values quote per value: `--classes "orange cat",dog`.

  Space-separated values are not an option — in the literal sense. Click restricts variable-length `nargs` to positional arguments, so a `List[str]` option is repeatable, never space-collecting; `--classes cat dog` binds `cat` and leaves `dog` as a stray positional, aborting with *"Got unexpected extra argument(s)"*. *Rejected: a space convention, which cannot be implemented for options at all; and per-flag separators, which would require users to remember which flag takes which.*

  **This makes the comma a reserved character in class names** — see the filesystem-safe validation rule, which excludes it. **Not in scope: list rendering in output.** Error messages and printed lists separate items with commas because that is how English separates items (`In dataset/ but not in --classes: golden_retriever`); that is prose, not a delimiter convention, and is *not* to be harmonized with flag syntax.

#### Class-name rules

Two rules govern every class name the product accepts, on every surface — **from `-c`, from a manifest's `class` column, and, at fast-follow, added live in the browser** — because every class name becomes a folder. They are stated here, beside the comma convention that forward-references them, rather than in the browser subsection that renders them — the first command accepting class names is `optica fetch`, which never opens a browser.

1. **Filesystem-safe class-name validation.** Every class name must be non-empty, **must not be `.`, `..`, or any name composed only of dots** — those are path components, not names, and `..` would resolve the class folder outside `dataset/` — contain no path separators (`/`, `\`), no comma (reserved as the value separator), **no control characters (U+0000–U+001F)**, and **none of `? * : | " < >`, which Windows rejects in filenames**, stay within a 50-character cap, **not begin with `-`** — a flag spelling, which the parser binds as a value rather than rejecting — **not end with `.` or a space**, and avoid reserved OS filenames blocked outright (`con`, `aux`, `nul`, `prn`, `com1`–`com9`, `lpt1`–`lpt9` — Windows reserved names, relevant given Windows is a best-effort V1 target; the character exclusions above cover the same target for the same reason). **A name failing any of these is a hard error naming it, and every failing name is listed** (truncating past 10, as the class-subset exclude list does) — no name is rewritten to make it pass, since a name that is not a single safe path component is unguessable rather than correctable. No blocklist or overlap check applies (`optica label` never fetches).
2. **Case-insensitive duplicate blocking.** A name matching an existing class under case-insensitive comparison is blocked — folder names are effectively case-insensitive on macOS (default) and Windows, so allowing both `cat` and `Cat` as distinct classes would work on Linux and silently misbehave (folder collision) elsewhere. A case-variant (`Cat` when `cat` exists) is an inline error; an exact re-add (`cat` when `cat` exists) is a neutral inline confirmation, not an error. Both dispositions above describe the browser, where names arrive one at a time. Under `-c`, or from a manifest's `class` column, the whole list arrives at once and there is no inline surface, so: **a case-variant is a hard error at parse**, naming both colliding names; **exact duplicates collapse silently**, and the resolved class list is what gets reported. Nothing is lost by collapsing `cat,cat`; allowing `cat,Cat` is the folder collision the rule exists to prevent.

---

### Configuration

**Two-tier config (global + project-local).** Two files:
- `~/.optica/config.toml` — global, created by `optica setup`. Holds defaults and API keys.
- `.optica.toml` — project-local, created by `optica config --init`. Holds per-project overrides.

Priority (highest to lowest):

```
CLI flags > project-local .optica.toml > env vars > ~/.optica/config.toml > built-in defaults
```

**Environment variables are `OPTICA_` plus the uppercased config key** — `epochs` → `OPTICA_EPOCHS`, `clip_threshold` → `OPTICA_CLIP_THRESHOLD`, `max_open_datasets_per_class` → `OPTICA_MAX_OPEN_DATASETS_PER_CLASS`. The transform is mechanical and applies to **every** config key, exactly as the CLI-flag-to-config-key transform does; `pydantic-settings`' `env_prefix` is the mechanism. Two deliberate exceptions: **API keys keep their unprefixed names** (`FLICKR_API_KEY`) because they are vendor credentials a user typically already holds under those names rather than Optica settings; and **`OPTICA_TORCH_VARIANT` mirrors no config key** — it is a setup-time variable that takes the prefix but sits outside this priority chain entirely.

**A `.env` file sits at the env-var tier, not beside it.** `python-dotenv` discovers `.env` in the project directory and loads it into the environment, so its values inherit env-var precedence rather than forming a sixth tier. **`.env` is gitignored** — the opposite of `.optica.toml`, which is committed deliberately, and the difference is that `.env` is where keys live.

`optica config --set key value` writes to project-local if present, global otherwise; `--global` forces global. **When neither file exists** — a supported state, since Core alone is functional and `--set` is on the lock file's exempt list precisely so it runs before `optica setup` has — the global file is **created**, and its path is reported in the output so it is never a file the user did not know appeared. *Rejected: erroring toward `optica setup`, which contradicts Core being functional on its own.* **An unknown key is rejected at write time**, not written through for the load-time check to catch later: a close match (`difflib.get_close_matches()`, similarity cutoff 0.6) gives a suggestion error, and no close match gives a hard error listing the valid keys — the same treatment `--include-extras` gives an unknown extra. Writing through would let `optica config --set epocs 20` report success and break the *next* command instead, at a distance from the typo. All config keys are **flat** in V1 — no nested keys. `optica config --view` shows the resolved config with source annotations and flags keys still at their built-in default (never explicitly set). **API keys are never written to `.optica.toml`** and never committed — always stored in `~/.optica/config.toml` or environment variables. **An API key found in a project-local file is a config-load-time error naming the file and the key**, before any command executes: the file is committed by design, so a key that merely worked there would reach version control with no signal. **API keys are config keys with one difference: `--view` masks the value, never the source.** A stored key renders as `flickr_api_key = "••••••••"` with its normal source annotation — the annotation is the point, since *"is Optica using the key from my environment or the stale one in my global config?"* is the question people actually hit, and it is answerable without disclosing a character. *Rejected: omitting the keys from `--view` entirely, which leaves a user unable to tell whether a key is set at all.* A key that is **not set anywhere** renders as `flickr_api_key = (not set)`: these are the only V1 keys with no built-in default, so the *"still at built-in default"* flag has nothing to mark on them — absent and defaulted are different states, and only these keys can be absent. `--set` accepts them and always writes them to the global file regardless of whether a project-local one exists — `--global` is implied and need not be passed.

**`.optica.toml` is committed, not gitignored.** It is a project config file analogous to `pyproject.toml` or `.pre-commit-config.yaml`; committing it means teammates and CI share the same Optica configuration. *(The "API keys never in project-local" rule above is what keeps committing it safe — and it is enforced at both ends rather than merely stated: `--init` never emits the key, and a key found in a project-local file is rejected at load.)*

**`optica config --init`** writes **commented defaults** — a short header comment followed by every V1 config key present but commented out (`# epochs = 10`), **except `flickr_api_key`, which is never emitted** — `.optica.toml` is committed, so a commented key there is an invitation to uncomment a credential into version control. Discoverable, since a user sees the whole surface and uncomments what they want, while nothing is *set*: a commented key is not an explicit value, so `optica config --view`'s *still at built-in default* annotation keeps working for projects created this way. *Rejected: writing every key populated, which would make every key explicitly set and that annotation permanently useless for any `--init` project; and an empty file, which offers no discoverability at all.* It prompts before creating:

```
Create .optica.toml in the current directory? [Y/n]
```

`--yes` auto-confirms. When `.optica.toml` already exists instead:

```
.optica.toml already exists.
Use optica config --set to modify individual settings, or overwrite the file entirely.
Overwrite? [y/N — n to exit]
```

The create prompt is a **non-destructive** confirmation (`--yes` answers it); the overwrite prompt is destructive (`--yes` never answers it). *(A first-run command must not write to the filesystem silently.)*

**`optica config --clear-staging`** lists current staging contents (see *Staging shapes* for what is listed, across all three shapes), asks for confirmation, deletes all staging contents, and prints confirmation. It exists because staging is hidden **and large**; the training logs are hidden too and deliberately have no counterpart command, being a few KB each — see Training → *Training log*. The deletion logic lives in the Input Manager; `cli/config.py` delegates to it.

#### `.gitignore` management

Optica gitignores its own regenerable artifacts, and does so at folder level only:

- **Gitignored:** `./checkpoints/` and `./optica-output/` — large, regenerable, never committed. When Optica first creates either folder, it drops a `.gitignore` containing `*` **inside that folder**. Optica never touches the user's project-level or global `.gitignore`.
- **Not gitignored:** `.optica.toml` (committed, above); `./dataset/` (user data — some users version curated datasets deliberately, so this is left to the user); standard project files.

Folder-level is deliberate: the gitignore travels with the folder Optica owns, there is no consent issue (Optica created the folder), it never modifies user-owned files, it works whether or not the project has a `.gitignore` at all, and it composes additively with any existing one. If the user already ignored those paths, the folder-level file is redundant but harmless.

```
your-project/
├── .optica.toml          ← committed, tracked by git
├── dataset/              ← user's choice, Optica doesn't touch
├── checkpoints/
│   └── .gitignore        ← contains: *
├── optica-output/
│   └── .gitignore        ← contains: *
└── src/
```

#### Home directory structure

```
~/
└── .optica/
    ├── config.toml
    ├── optica.lock         ← PID + command name + run ID of the active run
    ├── logs/
    └── staging/
        ├── <class_name>/           ← auto-fetch staged images (complete)
        ├── <class_name>.partial/   ← auto-fetch in progress or interrupted
        ├── curation.json           ← in-progress curation selections
        └── labeling/               ← labeling session progress files
```

#### Config keys (V1)

| Key | Default | Notes |
|---|---|---|
| `default_mode` | `curate` | `label`, `curate`, `clip` |
| `default_source` | `open-datasets` | `flickr`, `open-datasets` |
| `default_model` | `efficientnet-small` | `efficientnet-small`, `efficientnet-large`, `resnet`, `resnet-50`, `mobilenet`, `mobilenet-large` — `resnet`/`resnet-50` and `mobilenet`/`mobilenet-large` are alias pairs, one model each (see Training) |
| `images_per_class` | `50` | |
| `epochs` | `10` | |
| `learning_rate` | `0.001` | Calibrated for the adaptive optimizers. SGD typically needs a rate one to two orders of magnitude higher — set it explicitly when `optimizer = "sgd"` |
| `optimizer` | `"adamw"` | `adamw`, `adam`, `sgd`. Per-optimizer hyperparameters are **fixed in V1 and exposed at no tier**: AdamW `weight_decay = 0.01`, Adam `weight_decay = 0`, SGD `momentum = 0.9`. An expert who needs them constructs their own optimizer and runs their own loop — Tier 5 gives control of the model object, not of the optimizer. Config-only, no CLI flag |
| `batch_size` | `32` | |
| `early_stopping` | `5` | |
| `augmentation` | `true` | Training-time transforms; `--no-augmentation` is the inverted flag. In the V1 key set because both artifacts' `config` blocks and `TrainConfig` already carry it |
| `train_split` / `val_split` / `test_split` | `0.70` / `0.15` / `0.15` | Sum-validated (below) |
| `max_checkpoints` | `3` | Top N checkpoints saved per run |
| `clip_threshold` | `0.25` | Calibrated for ViT-B-32/openai weights and the `"a photo of a {class}"` prompt template; 7-band validation (see Input & Acquisition) |
| `finetune_ratio` | `0.70` | Proportion of total epochs for Phase 2 fine-tuning. Phase 1 uses `1 - finetune_ratio`. `0.0` skips fine-tuning; `1.0` skips head warmup |
| `max_open_datasets_per_class` | `500` | Soft cap for Open Images fetch — courtesy limit for public infrastructure |
| `curation_port` | `8765` | Default Curation Server port; auto-increments if taken |
| `curation_timeout_minutes` | `60` | Curation server idle timeout. `0` disables. **Governs `optica label`'s session timer too**, with its own reset triggers — see Labeling UI |
| `flickr_api_key` | — | Flickr API key. Global config only, never `.optica.toml`. Masked by `--view` |

> *Not in the V1 key set (accepted, do not add):* `export_format` travels with the `--format` flag to the ONNX/REST fast-follow. `strict_min_size` and `dedup_threshold` travel with the `--strict` posture flag; the V1 image-validation size warning fires at 128px (hardcoded, as 64px was) with no config key, and V1 deduplication is MD5-based with no threshold key. `default_task` is **not** a config key in V1: it is a module-level constant, `"classify"`, since one task type means a settable value would have exactly one legal setting. It becomes a config key when a second task ships — adding one then is non-breaking, which is what makes the constant safe now. Keys stay flat in V1.

**Split-sum validation.** `train_split + val_split + test_split` must equal `1.0` (±0.01 float tolerance). A mismatch is a **hard error** — no auto-adjust, no prompt. The check always runs regardless of which keys are explicitly set (a key at its default doesn't change the sum). The error annotates each value's source (`config` vs `default`):

```
✕ train_split + val_split + test_split must equal 1.0.
  Got: 0.80 (config) + 0.10 (config) + 0.15 (default) = 1.05
  Set all three values to sum to 1.0.
  Example: train_split = 0.80, val_split = 0.10, test_split = 0.10
```

This validation also runs at config-load time (per the config-mirrors-flag standing rule), so a bad `.optica.toml` errors before any command executes.

**Numeric range validation.** Every numeric config key has a stated domain, and a value outside it is a **hard error at config load** — the same enforcement point and posture as the split-sum check, per the config-mirrors-flag standing rule. The error names the key, the offending value, its source (`config`, `default`, or the flag that set it), and the permitted domain, in the shape the split-sum error uses above. This is the general rule; `clip_threshold`'s 7-band treatment (see Input & Acquisition) is an elaboration for a key whose *intermediate* values carry different dispositions, not a different standard.

| Key | Domain | Notes |
|---|---|---|
| `epochs` | integer ≥ 1 | |
| `batch_size` | integer ≥ 1 | No upper bound; the CPU batch-size prompt covers the practical ceiling |
| `early_stopping` | integer ≥ 0 | `0` disables early stopping |
| `learning_rate` | float in `(0, 1]` | |
| `finetune_ratio` | float in `[0.0, 1.0]` | `0.0` and `1.0` are permitted and warn (see Training) |
| `train_split` / `val_split` / `test_split` | float in `[0.0, 1.0]` each | The sum rule above applies in addition |
| `max_checkpoints` | integer ≥ 1 | |
| `images_per_class` | integer ≥ 1 | |
| `max_open_datasets_per_class` | integer ≥ 1 | |
| `curation_port` | integer in `[1024, 65535]` | Auto-increments on collision |
| `curation_timeout_minutes` | integer ≥ 0 | `0` disables |

---

### `optica setup` — Machine Initializer

Always global; never per-project (per-project configuration is `optica config --init`). `optica setup` owns the **Platform-dependent** packages (the torch stack) and, as a convenience layer, the feature extras. `pip install optica[X]` remains the canonical way to install a feature extra — setup does not replace it.

#### Flags (V1)

`--include-extras <names>`, `--exclude-extras <names>`, `--all-extras`, `--no-extras`, `--upgrade`, `--ci`, `--skip-keys`, and the global `--force`. `--tasks`/`--all-tasks` are **built but not surfaced** in V1 — with a single task type they unlock nothing (this is a V1 state, not a deferral).

*(`--exclude-extras torch` covers what a dedicated skip flag would do; `--ci` and `--skip-keys` serve distinct roles and are listed in the CLI Flag Reference.)*

**`--ci` — the owning definition.** `optica setup --ci` performs **config initialization only**: no package installation, no environment detection, no prompts of any kind. Packages reach a CI environment through `pip install optica[test]` before setup runs, so there is nothing for setup to install — which is why `--ci` installs no torch build, CPU or otherwise. It is non-interactive by construction rather than by the extras-flag route, so **combining it with an extras-selection flag is a hard error**, not a redundant no-op: `--include-extras clip --ci` asks for an install `--ci` will not perform, which is *impossible in the resolved mode* under the standing no-op-vs-error test, exactly as `--upgrade` is. **No Review step is shown**: the Review exists to confirm an environment target and an install selection, and `--ci` produces neither — its output is the config-initialization result and nothing else. *(This is why the Review's non-interactive rule is scoped to the extras-flag path, not to every non-interactive invocation.)* Every other statement of `--ci` in this document points here.

**Interactivity is binary.** If none of `--all-extras`/`--no-extras`/`--include-extras`/`--exclude-extras` is present, setup is fully interactive; if any is present, it is fully non-interactive and resolves the extras selection silently. *(`--tasks`/`--all-tasks` are built but **not registered as CLI arguments** in V1, so a user cannot put setup into non-interactive mode with them; the resolver accepts them for the post-V1 case.)* `--yes` therefore has **no role in `optica setup`** — it neither drives nor is needed by it. For the same reason `--upgrade` is **incompatible with those flags and errors when combined with any of them**: its only function is to raise per-package prompts, and a fully non-interactive setup has nowhere to put them. V1 has no unattended upgrade path; the completion message's passive upgrade note is what a non-interactive run gets instead.

#### Structural model — decide, then do

All user-facing prompts come first (decide phase); Optica then runs every install and init with no further input (do phase). The user completes all decisions upfront and can walk away.

**Pre-phase — environment detection.** Runs first, unconditionally; everything installs into the resolved environment. V1 logic reads the environment the user is **standing in**, not merely the interpreter Optica runs from: `sys.prefix != sys.base_prefix` identifies a venv Optica is installed in, `CONDA_PREFIX` identifies an active conda environment (conda envs carry their own Python, so prefix and base_prefix match and no `pyvenv.cfg` exists — neither V1 signal sees them), and `VIRTUAL_ENV` or `CONDA_PREFIX` naming an environment Optica is *not* running from is the mismatch case below; a one-level, name-agnostic `pyvenv.cfg` scan **rooted at the current working directory** — the same place the create prompt writes `.venv`, and the root that decides which environments the *exactly one found* and *more than one found* cases can ever see; Y (create) / S (skip, warn) / A (abort) when none is found, with "create new" always available (name prompt defaulting to `.venv`) and OS-aware activation instructions (bash/zsh/CMD/PowerShell). `--ci` skips this phase entirely. If the environment is unresolved, setup aborts — nothing else runs.

**Environment resolution order.** The pre-phase resolves exactly one target environment, in order:

1. **An isolated environment is active and Optica runs from it** — a venv (`sys.prefix != sys.base_prefix`) or a conda environment (`CONDA_PREFIX` set and `sys.prefix` beneath it). It wins outright, and any venv found on disk is ignored without a prompt. A conda environment is a valid target: pip installs into it, and telling a correctly isolated user to create a venv inside it would be worse guidance than the two-state model it replaces. Activating a venv is an explicit act; a directory sitting in the working folder is not. The resolved target is named in the Review step, which is where a wrong target is caught.
2. **An isolated environment is active but Optica is not in it** — `VIRTUAL_ENV` or `CONDA_PREFIX` is set while Optica runs from outside it. **Hard error, interactive and not**, naming both paths and the remedy: install Optica into the active environment. Proceeding is what produces the loop — packages install into an environment Optica does not run from, setup reports success, the next command raises `OpticaTorchError` saying *"Run: optica setup"*, and the user is returned to the command they just finished. The activation-command mitigation at *Review and completion* does not reach this case, because the environment is already active.
3. **Exactly one venv found by the scan, none active** — confirmed before use: `Found ./.venv — not currently active. Install into it? [Y/n]`. **n** falls through to the create / skip / abort options.
4. **More than one found, none active** — no determinate answer, so the matches are listed and the user picks one, or falls through to create / skip / abort.
5. **None found** — the Y / S / A prompt above.

**Under non-interactive invocation** (any of the extras flags) the pre-phase resolves silently and never prompts: an active isolated environment wins — venv or conda; otherwise a single discovered venv is used without confirmation; **none found, or more than one, is a hard error** naming the fix. A mismatch is a hard error on every path, interactive included. `--ci` initializes config without installing packages and is therefore not a non-interactive install path, so this error is the only signal a container build receives and it must be loud rather than recoverable. *Rejected: falling back to skip-with-warning, which would install the torch stack into system Python on the strength of a warning that no non-interactive run will read.*

**Create-name collision.** The create prompt's default is `.venv` unconditionally — it encodes the ecosystem convention and does not bend to anticipate a collision. If the name given, default or typed, already exists as a directory, the prompt rejects it and re-asks: *"`.venv/` already exists but is not a virtual environment. Choose a different name, or remove it and re-run."* Optica never creates a venv into an existing directory, and never inspects one to guess whether it is a repairable partial venv — a heuristic standing in front of a multi-gigabyte write can be wrong in the direction that matters. **`--force` does not bypass this check** (*do not harmonize* with the global rule that `--force` bypasses safety prompts — there is no proceed-anyway branch here to bypass). *Rejected: auto-incrementing the default to `.venv2`, which leaves an orphan environment whose reason the user never learns; and suppressing the default when `.venv` exists, which degrades the common case to serve a rare one.*

**Review and completion.** The Review step's Environment line names the target and its state — `active`, `detected (not active)`, `created`, or `none — installing into system Python` — with the label determined by the kind of environment: `Venv:` for a venv, `Conda:` for a conda environment. The line reports the environment packages will actually land in; under an active conda environment, `none — installing into system Python` would be false, which is the bar the plan holds itself to elsewhere (*Rich output reports actual detected values*). When the resolved environment is **not** the active one, the do-phase summary leads with the OS-appropriate activation command before reporting feature availability. Without it, setup reports success, the next command raises `OpticaTorchError` — whose message is *"Run: optica setup"* — and the user is sent back to the command they just completed. This applies to the created and detected cases alike.

**Decide phase:**
1. **Task selection** — silent/auto in V1 (single task, never prompts). Becomes interactive only when `len(TASK_REGISTRY) > 1`. Gates which extras are relevant.
2. **Extras selection** — torch → web → clip. Typed input (`y`/`n`, `auto`/`cpu`/`gpu`) — universally compatible with SSH, CI, and editor terminals.
3. **API-key prompt** — `FLICKR_API_KEY` (for `--source flickr`); Open Datasets needs no key. Skippable with Enter; skipped entirely under `--skip-keys` or `--ci`. Note shown first: *"A key is only needed for `--source flickr`, and requesting one requires a Flickr Pro subscription. Press Enter to skip if using open-datasets only."*
4. **Hardware scan** — runs whenever a torch stack is in play: any variant selected in step 2, or a stack already installed. **Only the scan is unconditional; the prompt is not.** A mismatch is possible only for `torch-cpu` and `torch-gpu`, since `torch-auto` resolves to whatever the machine has, so only those two can fire the safety prompt below — here in the decide phase, so the do phase keeps its *no user input* guarantee and the user can still walk away once the Review is confirmed. Where no safety prompt fires — the other paths, and `torch-cpu` or `torch-gpu` where the requested variant does not mismatch the hardware — the scan can neither abort setup nor hold the do phase open; its product surfaces at the Review's detected-hardware line, at the Review's build-variant state where the installed build does not match, and in the completion message's build-in-use clause.

The extras prompt (interactive, all selected):

```
Install PyTorch stack? [Y/n]: Y
  Enables: optica train, optica export, optica run
  Which variant?
    auto  — hardware-detected (~250MB–2.5GB)
    cpu   — CPU only (~250MB)
    gpu   — GPU/CUDA (~2–2.5GB)
  [auto/cpu/gpu] (default: auto):

[Y/n] Browser UI — optica label, optica curate, optica run (label/curate modes).
      Installs: FastAPI, uvicorn (~5MB)
[y/N] CLIP filtering — image-text similarity scoring for fetch. Installs: open-clip-torch (~600MB, model downloads on first use)
```

Torch uses two consecutive prompts (Y/N, then variant) because size is knowable only once a variant is chosen. **Defaults: web Y, clip N** (web underlies core workflow commands and is ~5MB; CLIP is a 600MB feature-specific download opted into deliberately). *(In V1 the `web` extra enables `optica label` and `optica curate`; REST export joins it at the fast-follow, at which point an ONNX prompt line — default Y — is inserted between web and clip. The extra is named `web` — over `server`, which would overclaim since Optica hosts nothing in V1, and `browser`, which undersells by missing the future REST export.)*

**Review step** — shown after the decide phase, before anything is installed or written; the user confirms all selections. When a torch stack is in play, the Review names the **detected hardware** alongside it: for `torch-cpu` and `torch-gpu` so a mismatch already answered in the decide phase is visible again before anything installs, and for `torch-auto` or an already-installed stack, where the scan fires no safety prompt, so the Review is where its result surfaces before the user confirms. **Under a non-interactive invocation the Review is still printed and its `Proceed with installation? [Y/n]` prompt is omitted**, since no flag answers it — skipping the Review entirely would remove the only stated catch for a wrong environment target on exactly the path where a wrong target costs most — an unattended environment such as a CI job or a container build (the *environment*, not the `--ci` *flag*; see below). The catch degrades honestly there, from *confirmed by a human* to *visible in the log*; the target it names is unambiguous regardless, because non-interactive environment resolution hard-errors on none-found, on more-than-one, and on a mismatch. **All of this scopes to an invocation made non-interactive by an extras-selection flag, where an install still happens and an environment is still resolved. `optica setup --ci` shows no Review at all** — it installs nothing and detects no environment, so neither of the Review's two subjects exists and the rationale above has nothing to protect (see `--ci` above):

```
─────────────────────────────────────────
  Optica Setup — Review
─────────────────────────────────────────

  Environment
    Venv: .venv (created)

  Extras
    PyTorch stack (auto-detect → CUDA 13.0)   ~250MB–2.5GB
    Browser UI                                ~5MB
    CLIP filtering                            ~600MB

  API keys
    Flickr         — skipped

  Total download: ~0.9–3.1GB

─────────────────────────────────────────
  Proceed with installation? [Y/n]:
```

A total download estimate is shown (a straight sum of selected extras). **The torch stack `open-clip-torch` pulls transitively is shown as its own line beneath the total, never folded into it** — so the sum stays a sum of what was selected, while the user still sees what will be fetched. It appears only when clip is selected, no torch variant is, and no torch stack is already present. **No time estimate** — too machine-variable; progress bars in the do phase handle expectations. Skipped API keys are shown explicitly. If no extras are selected, the section shows "none selected."

**Do phase (no user input):** package installs (all selected extras in one pass, Rich progress bar per extra) → config-file write (`~/.optica/config.toml` — **created if absent, merged into if present**: values collected this run are written, values not collected are left untouched, and nothing is ever removed. A prompt skipped with Enter therefore **preserves** any existing value rather than clearing it, and a key supplied on a re-run is written even though the file already exists) → summary.

#### Registry and resolution

Setup is data-driven, not hardcoded per extra — adding a future extra means adding a registry entry, not editing code in several places (`pyproject.toml` still needs a manual edit per new extra; that is a pip limitation, not a design gap).

```python
TASK_REGISTRY = [
    {"task_id": "classify", "display_name": "Image Classification",
     "cli_group": "classify", "api_namespace": "optica.classify",
     "tier5_class": "Classifier", "relevant_extras": ["web", "clip"],
     "task_group_extra": None},
]

# Schema: display_name, default, size_estimate, enables — required for every entry.
#         pip_extra XOR index_url. group/universal optional.
EXTRAS_REGISTRY = {
    "web":  {"display_name": "Browser UI", "default": True,
             "pip_extra": "optica[web]", "size_estimate": "~5MB",
             "enables": ["optica label", "optica curate", "optica run (label/curate modes)"]},
    "clip": {"display_name": "CLIP filtering", "default": False,
             "pip_extra": "optica[clip]", "size_estimate": "~600MB",
             "enables": ["optica fetch --mode clip", "optica run --mode clip"]},
    # torch variants — universal (every task's train/export needs them) and
    # mutually exclusive within group "torch":
    "torch-auto": {"display_name": "PyTorch stack (auto-detect)", "default": True,
                   "group": "torch", "universal": True, "size_estimate": "~250MB–2.5GB",
                   "index_url": None,   # torch-auto only: resolved in the do phase from the decide-phase scan
                   "enables": ["optica train", "optica export", "optica run"]},
    "torch-cpu":  {"display_name": "PyTorch stack (CPU only)", "default": False,
                   "group": "torch", "universal": True, "size_estimate": "~250MB",
                   "index_url": "https://download.pytorch.org/whl/cpu",
                   "enables": ["optica train", "optica export", "optica run"]},
    "torch-gpu":  {"display_name": "PyTorch stack (GPU)", "default": False,
                   "group": "torch", "universal": True, "size_estimate": "~2–2.5GB",
                   "index_url": "https://download.pytorch.org/whl/cu<XXX>",  # CUDA build pinned at the pre-implementation gate
                   "enables": ["optica train", "optica export", "optica run"]},
}
# The "onnx" entry (default True) is added with the ONNX/REST fast-follow.
```

Resolution (generic, build now) — complete as written; no preprocessing step is assumed:

```python
def _members(group, reg):
    return {k for k, v in reg.items() if v.get("group") == group}

def _expand_excludes(names, reg):
    """A group name expands to every member; plain keys pass through.
       (--include-extras takes specific variants only — enforced at parse.)"""
    out = set()
    for n in names or []:
        m = _members(n, reg)
        out |= m if m else {n}
    return out

def _collapse_groups(names, reg):
    """Reduce each mutually-exclusive group to its default member."""
    out = {n for n in names if reg[n].get("group") is None}
    for g in {reg[n].get("group") for n in names} - {None}:
        out |= {k for k in _members(g, reg) if reg[k]["default"]}
    return out

def resolve_setup(args, task_registry, extras_registry):
    if args.all_tasks:            T = {t["task_id"] for t in task_registry}
    elif args.tasks is not None:  T = set(args.tasks)          # "" -> set()
    elif len(task_registry) == 1: T = {task_registry[0]["task_id"]}
    else:                         T = interactive_task_select(task_registry)

    task_relevant = set().union(*(t["relevant_extras"] for t in task_registry
                                  if t["task_id"] in T)) if T else set()
    universal = {k for k, v in extras_registry.items() if v.get("universal")}
    relevant  = task_relevant | universal     # torch is never task-relevant; it is universal

    if   args.all_extras:  base = _collapse_groups(relevant, extras_registry)
    elif args.no_extras:   base = set()
    elif (args.tasks is not None or args.all_tasks                    # any extras or task
          or args.include_extras is not None                          # flag => no prompting;
          or args.exclude_extras is not None):                        # base is the defaults
        base = {e for e in relevant if extras_registry[e]["default"]}
    else:
        base = interactive_extras_select(relevant, extras_registry)

    inc = set(args.include_extras or [])          # specific variants only (parse-enforced)
    exc = _expand_excludes(args.exclude_extras, extras_registry)
    # an explicit include displaces any other member of the same group
    inc_groups = {extras_registry[e].get("group") for e in inc} - {None}
    base = {e for e in base if extras_registry[e].get("group") not in inc_groups}

    return T, (base | inc) - exc
```

Modifiers apply in a **fixed order** (resolve base → include → exclude), so command-line flag order never changes the outcome. `--include-extras`/`--exclude-extras` operate on the global extras namespace (union semantics, no conflict errors from scope).

**Group semantics.** `torch` is a group name, not a registry key, and exclude-side expansion happens **inside** `resolve_setup` so the block above is complete as written. The two directions are deliberately asymmetric: `--exclude-extras torch` removes **every** variant, while `--include-extras` takes a **specific variant** — a bare group name there is a hard error, since silently choosing a multi-gigabyte variant the user did not name is worse than refusing. Expansion therefore lives inside `resolve_setup` on the exclude side only; the include side is validated at parse. An explicit include of one variant **displaces** any other member of that group already in `base` — so `--all-extras --include-extras torch-cpu` yields `torch-cpu` rather than a conflict. Naming two members of one group explicitly is a **hard error**.

**Torch is universal, not task-relevant.** Every task's `train`/`export` needs it, so it carries `universal` and is unioned into `relevant` regardless of task selection; it is deliberately absent from any task's `relevant_extras`, and a future task needs to add nothing to reach it. `interactive_extras_select` therefore receives the full torch → web → clip set the prompt sequence above requires. The consequence, stated plainly: **`--no-extras` has setup install no torch** — which leaves an environment that cannot train or export **unless torch is already present**, as it is for anyone who ran `pip install optica[clip]` and got the stack transitively. `--include-extras torch-cpu` (or any variant) has setup install it.

**Every field the described behaviours read is carried here.** `size_estimate` feeds the review step's download total; **`clip`'s `~600MB` covers `open-clip-torch` and its weights, not the torch stack it pulls transitively, which the Review shows as a separate line rather than folding into the total. That line reads `torch-auto`'s `size_estimate` — the closest existing figure, since both cover *whatever this platform resolves to* — and is an estimate rather than a promise about what pip will fetch, because the transitive pull comes from the default index rather than from any variant's `index_url`;** `enables` feeds both the completion message's *"used by"* and the incomplete message's *"Affected:"* — one field, two renderings; `index_url` builds the pip command per variant. `torch-gpu`'s CUDA index is version-specific and moves between PyTorch releases (`cu126`, `cu130`, `cu132`), so the exact build is a **pre-implementation-gate item**, like timm's layer names.

#### `--include-extras` / `--exclude-extras` parsing

- **Separator:** comma-separated (`--include-extras web,clip`); a repeated flag is also valid. Per the global value-separator convention.
- **Input vocabulary:** registry keys only (`web`, `clip`, `torch-auto`, …). A pip name (`optica[clip]`, `open-clip-torch`) → named suggestion error ("Did you mean 'clip'?"). Bare `torch` → "Did you mean 'torch-auto'?" (an alias was evaluated and rejected — it would give `torch` two meanings, since `--exclude-extras torch` already means the whole group).
- **Redundant:** a combination that adds nothing beyond what is already selected or excluded is silently accepted — no warning, no error. `--skip-keys` alongside any extras flag is the common case: the extras flag has already made setup non-interactive, so the key prompts never fire. The line against `--upgrade`, which errors in the same situation, is that a flag asking for something **already true** is a no-op, while one asking for something **impossible in the resolved mode** is an error. **`--ci` errors with the extras-selection flags for the same reason as `--upgrade`** — it performs no installation at all, so an extras selection is impossible in its resolved mode rather than redundant with it.
- **Empty/null:** `--include-extras ""` → silent no-op (handles shell variable expansion, e.g. `"$EXTRAS"` when unset); `--include-extras` with no value at all → wrapped error with an example, per the standing flag-with-no-value rule; never a raw Typer traceback.
- **Typos:** close match (`difflib.get_close_matches()`, similarity cutoff 0.6) → suggestion error; no close match → hard error listing all valid registry keys. Never silently ignored.
- **Group handling:** `--exclude-extras torch` matches the whole torch group; `--include-extras` takes a specific variant. Entries within a group are mutually exclusive — specifying more than one is an error.
- **Conflict:** the same extra in both `--include-extras` and `--exclude-extras` → hard error, compared **after** group expansion, so `--include-extras torch-cpu --exclude-extras torch` is the same error as naming `torch-cpu` in both. **`--exclude-extras torch` alongside a selected `clip` is *not* a conflict:** `--exclude-extras` governs what setup installs, not what ends up on the machine, and `open-clip-torch` pulls the torch stack transitively whatever setup does. Setup honours the flag; the **completion message** reports the stack as present-but-not-installed-by-setup rather than absent. **`--all-extras` with `--no-extras` is also a hard error:** the pair is impossible in any resolved mode rather than redundant with it, by the same test that makes `--upgrade` and `--ci` errors alongside the extras flags.

#### Torch hardware safety prompts

Setup scans hardware **in the decide phase** — at step 4, after the API-key prompt and before the Review — whenever a torch stack is in play. Two mismatches fire a **safety prompt**, both requiring `torch-cpu` or `torch-gpu` to have been selected (suppressible by `--force`; each prints a copy-paste-ready corrected command on abort, per the standing rule):

- **`torch-cpu` requested, CUDA-capable GPU present** — a performance concern:
  ```
  Your system has a CUDA-capable GPU (detected: NVIDIA RTX 3080, CUDA 13.0).
  You requested torch-cpu — this may limit performance.
  Proceed with CPU? [y/N]:
  ```
- **`torch-gpu` requested, no CUDA-capable GPU** — higher stakes (CUDA-dependent operations will fail at runtime):
  ```
  No CUDA-capable GPU detected on your system.
  You requested torch-gpu — CUDA-dependent operations will fail at runtime.
  Proceed with the GPU build anyway? [y/N]:
  ```

**Under a non-interactive invocation these prompts cannot be answered, so they auto-abort.** Setup raises `OpticaSetupError` naming the hardware mismatch and printing the invocation that would work — `optica setup --include-extras torch-cpu` for the GPU-requested-without-GPU case. This is the standing rule applied, not an exception to it: a safety prompt still fires with nobody at the terminal, and **`--force` remains the only thing that suppresses it**, proceeding with the requested build. `--yes` has no role in `optica setup` and does not reach here. The abort is the unanswerable prompt's **outcome**, not an independent hard error — which is why `--force` removes it: suppressing the prompt removes the abort with it, rather than overriding an error. `--force` still does not override hard errors elsewhere in setup, environment resolution and mismatch included. *Rejected: waiting on stdin, which hangs a CI job indefinitely; and proceeding silently, which installs a multi-gigabyte build whose CUDA operations fail at runtime.*

Output reports actual detected values (`torch 2.14.0 (CUDA 13.0)`), never the internal variant key. Setup builds the correct `pip install` command with the right index URL at runtime, so no static pinning is needed.

#### Idempotence

Four behaviors when packages are already present:
- **Skip (default):** an already-installed compatible version is skipped silently — no prompt. Re-running setup does not reinstall multi-GB packages. **Build variant is the exception:** compatibility ignores it, so an installed build that does not match the detected hardware reaches the Review's build-variant states instead — and accepting one does install a different build.
- **Upgrade:** with `--upgrade`, newer compatible versions are surfaced in the review step with per-package `[y/N]` prompts. `--upgrade` is a **mode flag, not a prompt-answering flag** — it makes the prompts appear; it does not answer them, which is why it is interactive-only (see *Interactivity is binary*).
- **Repair:** an installed set that is **incompatible** — the pairing rule broken, or a package that will not import — is not skipped. Setup fires a **safety prompt before installing anything**, on the hardware-mismatch prompt's shape: interactive only, auto-aborting with `OpticaSetupError` when nobody can answer, naming the offending pair and printing the working invocation, and suppressed by `--force`, which proceeds with the repair. Repair installs the pairing setup would have installed on a clean machine, from the hardware-appropriate index. **The message distinguishes a version mismatch from a package that will not import** — the second can come from a broken driver or a corrupt wheel, which reinstalling the pairing may not fix.
- **Reinstall:** arbitrary force-reinstall stays deliberately unexposed — users needing it go to pip directly. **Repair** above is the one scoped exception: it reinstalls only what restoring a compatible pairing requires, and only from the incompatible state.

**"Compatible" means the installed set satisfies the torch↔torchvision pairing rule in Tech Stack and imports successfully.** The four setup packages are deliberately unpinned, so there is no version floor to compare against — the pairing is the constraint that actually exists, and PyPI is already declared authoritative over it. `timm` and `scikit-learn` carry no pairing constraint, so for them compatibility reduces to the import clause: any installed version is compatible provided it imports. Under `--upgrade`, a *newer compatible* version means a newer release that still satisfies the pairing; a newer release that would break it is not surfaced. *Rejected: a version floor derived from the September 2026 snapshot, which would decay and would need a gate item to maintain.*

Review-step states (per package): `already installed ✓` / `will install` / `already installed — upgrade available [y/N]` / `already installed — incompatible, repair [Y/n]` / `already installed (CPU build) — GPU build available [y/N]` / `already installed (GPU build) — no CUDA GPU detected, install CPU build [Y/n]`. **The build-variant states fire wherever the decide-phase safety prompt has not already settled the question** — an already-installed stack on the Skip path, `torch-auto` included, since `torch-auto` fires no safety prompt; the question has been put only where the requested variant itself mismatches the hardware (`torch-cpu` on a CUDA-capable machine, `torch-gpu` with none), and there, answered or suppressed by `--force`, these states do not repeat it. The last three are **interactive-only**, per *Interactivity is binary*: with nobody at the terminal the incompatible state aborts as *Repair* describes, and the build-variant states degrade to a line in the completion message instead of prompting.

**Completion message (do-phase outcome, lean — no package names or versions):** one of seven states — `✓ Setup complete.` / `…complete.` + a passive "N packages have upgrades available. Run `optica setup --upgrade` to review." / `…complete — all packages already up to date.` / that plus the upgrade note / `…complete — 2 packages installed, 3 already present.` / (upgrade run) `…complete — 1 package upgraded, 2 upgrades declined.` / (repair run) `…complete — torch stack repaired.` That state line is the headline; beneath it the message reports **feature availability**, not a binary "ready for X": a Core-pipeline section and a per-extra feature section (installed Y/N + "used by"). The Core-pipeline section distinguishes three cases rather than two — the torch stack installed by setup, already present and left alone, or present without setup having installed it (`optica[clip]` supplies it transitively) — and, on the first two of these, which the decide-phase hardware scan reaches, names the build in use where the installed build does not match the detected hardware: a CPU build on a CUDA-capable machine, or a GPU build with no CUDA GPU present. The transitive path is not one of them: no variant is selected and no stack is already present, so the scan never runs and there is no detected hardware to compare the build against. Feature availability rather than a binary state, because partial installs are normal — a clip-mode user, whose pipeline never opens a browser, is not in a degraded condition.

**Incomplete message** (structure: what failed → affected commands → retry command → passive upgrade note). **The headline counts extras, not packages** — an extra may contain more than one package (`web` contains two), and the failure line, the affected-commands line and the retry command are all per-extra, so counting packages would put the only package-shaped number in a message that is otherwise entirely about extras:

```
⚠ Setup incomplete — 1 extra failed.
  CLIP filtering failed to install.
  Affected: optica run --mode clip, optica fetch --mode clip
  Run `optica setup --include-extras clip` to retry.
```

Retry-command rules: reconstruct from **resolved selection** (what the user chose), not raw `sys.argv`; include only what failed; render interactive sessions as non-interactive flags (an onboarding benefit — it teaches the flag syntax); reconstruct the torch variant from selection (`auto` → `torch-auto`); `--upgrade` and `--yes` are never included in a retry command (they are session-level choices).

#### Install state is not a tier

The five documentation tiers (Python API) are an **onboarding concept, not an installation one** — they say where to start, not what gets installed. A tier-aware setup ("which tier are you?") was considered and **rejected**: the tier a user starts at is not the tier they stay at, so under-installing on a stated starting tier would produce missing-dependency errors on graduation. Extras stay feature-gated by capability, cutting across tiers. The README should map install state to tier entry points — a documentation consequence, not a setup behavior; the completion message stays lean and reports feature availability only.

---

### Input & Acquisition

#### Input Manager

Four sub-components, all producing an `ImageFolder`-compatible structure:
- **Local Adapter** — organized folders, flat folder, or CSV/JSON manifest. A flat folder's images and a manifest's rows are **copied** into `dataset/`; an already-organized `--dataset` is **read in place and never copied** (see *Image validation pipeline* → *Ownership rule*, which is what makes the conversion and resize stages report rather than write on that path). Originals are untouched on every route.
- **Fetch Adapter** — Flickr, Open Datasets. Default 50 images per class (configurable via `--images-per-class`/`-i` or the `images_per_class` config key). Rate-limit aware, verbose progress.
- **Curation Adapter** — bridges the Fetch Adapter and the Curation Server (curate mode).
- **CLIP Adapter** — replaces human curation with open-clip-torch scoring (clip mode).

`--source` routing dispatches through a **registry/dictionary keyed on source name** with a single registration point (not an if-chain scattered across files), so a post-V1 source touches one file. This is an implementation discipline binding on how `input/fetch.py` is written.

#### Label mode — detection order

**Inside `optica run --mode label`**, this order decides whether labeling runs before training:
1. `--folder` provided → trigger labeling internally, then train.
2. `--manifest` provided → skip labeling if all rows have `class`; trigger labeling if no rows have `class`; **error if mixed** (see `--manifest`).
3. `--dataset` provided → it must exist and contain class subfolders; skip labeling, go straight to train. **A `--dataset` path that does not exist is a hard error naming the path, never a fall-through to case 4** — an explicit flag is never silently ignored, and falling through would make `--dataset ./datset` succeed against a `./dataset/` the user never named.
4. No `--dataset` given, and `./dataset/` present and valid → skip labeling, go straight to train.
5. None of the above → fail with a precondition error listing all valid options.

The same detection logic resolves which input a standalone command operates on, but **what happens afterward differs by command and must not be read off this list**: standalone `optica label` labels its resolved input and stops — that is its whole job, however it was invoked — while standalone `optica train` trains on its resolved dataset. Only `optica run` continues from one stage into the next, which it does by design.

**`optica train` accepts only inputs that are already trainable:** `--dataset`, a `./dataset/` it finds, or a **fully-labeled** `--manifest`, which materializes to a dataset before training. `--folder`, and a manifest with any unlabeled row, are precondition errors under `train` — both need a labeling session, which is `optica label`'s job to run and `optica run`'s to sequence. Detection-order case 1 is therefore unreachable from standalone `train`, and case 2 only in its skip-labeling branch.

`--folder` vs `--dataset`: `--folder` is a flat folder needing labeling; `--dataset` is an already-organized structure. They can be combined (`optica run --mode label --folder ./images --dataset ./new-dataset -c cat,dog`). A flat folder passed via `--dataset`, or `--folder` pointing at an already-organized folder, is an error. The organized-folder-via-`--folder` error names the detected subfolders:

```
✕ ./images/ appears to already be organized into subfolders: cat/, dog/, bird/
  --folder expects a flat folder of unlabeled images.
  If your dataset is already organized, use --dataset instead:
  optica train --dataset ./images
```

**Dispatch.** Given a flat, unlabeled folder, `run` dispatches to the **labeling path** — the same server and page `optica label` uses, not the `label` command, which labels its resolved input and stops however it was invoked. Curation is not a candidate: its browser UI is built on per-class tabs or dropdown, per-class selection, and a per-class low-selection warning, all of which presuppose images already grouped by class, and the Curation Adapter bridges the Fetch Adapter to the Curation Server. A flat folder has no grouping for it to present. `-c` is required whenever `run` dispatches to labeling, exactly as for standalone `label` — and resolved the same way: the class-name prompt where a prompt can fire, a hard error where one cannot, both before the server starts.

**Mode default.** `--mode` defaults to `curate` when acquiring by fetch and to `label` when `--folder` or `--manifest` is given, and the resolved mode is reported in the run's output — `Mode: label (default for local input)`. The `default_mode` config key supplies this value **only where the resolved command accepts `--mode` and the configured value is legal for the invocation as a whole** — `label` is not legal under `optica fetch`, and no value is legal under a command that takes no `--mode`. **Legality is evaluated per invocation, not per command:** `default_mode = clip` is legal for the *command* `run` yet not for `optica run --folder ./images`, and applying it there would turn a valid invocation into a hard error — which the guarantee below forbids. Where it does not apply the contextual default above stands and the configured value is ignored; because the resolved mode is always reported, an ignored setting is visible rather than silent. No config setting can turn an otherwise valid invocation into an error. Within a resolved mode, `--dataset` takes its role from that mode and from whether an input source was given: in label mode it is the **input** when no `--folder`/`--manifest` is present and the **destination** when one is; in curate and clip mode it is always the destination for organized output.

**No acquisition needed — resolved before the mode is.** Because `--mode` selects an acquisition path, a run that acquires nothing never resolves one. An **explicit** `--dataset` pointing at an already-organized dataset short-circuits acquisition — but only when **no input-source flag is present**: `--folder` or `--manifest` means acquisition was explicitly requested, so `--dataset` is the destination, as in the combined form above. When it does fire, `run` begins at training and reports `Acquisition: skipped (--dataset provided)` in place of a mode line. Three boundaries make this safe to state as a short-circuit rather than as a mode:

- **Bare `./dataset/` presence does not trigger it.** Adopting a directory left from an earlier run would silently break `optica run -c cat,dog`, whose documented behavior is to fetch. That case stays as detection case 4, reachable inside `--mode label`.
- **An explicit `--mode curate` or `--mode clip` overrides it,** which is how fetching into an existing dataset folder remains expressible; the `dataset/` conflict check then applies as normal.
- **`--classes` alongside a short-circuited `--dataset` is not a special case.** The asymmetric validation in *`--classes` against an already-organized dataset* applies unchanged — a class named with no matching folder is a hard error, folders absent from `--classes` are a confirmed train-on-a-subset.

*Rejected: requiring an explicit `--mode label` alongside local input, which puts a round trip in front of the most common local workflow; adding a fourth mode for the no-acquisition case, which would carry no information `--dataset` does not already carry and make the pair redundant; and treating `--dataset` as a general mode signal — outside the short-circuit its meaning still depends on the mode it would otherwise be used to determine.*

**Exactly one input source per invocation.** `--folder` **xor** `--manifest` **xor** neither, where neither means acquisition by fetch. `--dataset` is not an input source under this rule — it is the destination, except in the short-circuit case where nothing is acquired. Supplying more than one source is a hard error stating that combining input sources is **unsupported in V1**, not that the combination is invalid. Combining them would put a fully-labeled manifest beside an unlabeled folder — the partial-label case already hard-errored within a single manifest — and would spread collision and deduplication rules across origins. *Stated as a rule rather than as a rejected pair: a new input route then inherits the constraint instead of having to be remembered.*

**`--mode curate` or `--mode clip` with `--folder` or `--manifest`** is a hard error in V1. Both acquire by fetch, and neither accepts local input; clip in particular scores fetched candidates against a single class prompt and thresholds them, which is not the same operation as classifying local images across several prompts. The error states that these modes require fetched input rather than describing the combination as invalid, and includes the copy-paste corrected command.

#### `--manifest`

A distinct flag for CSV/JSON input (not routed through `--dataset`). CSV: `path` + optional `class` columns. JSON: array of objects with `path` + optional `class`. A manifest is **disposable input** — used only to build the file list, never rewritten; labeled output is copied into `dataset/<class>/` exactly as `--folder` does, originals untouched. A fully-labeled manifest passed to `optica label` is a **hard error**, not a correction pass. The manifest session ID is the file path + content hash, so a modified manifest starts a fresh session automatically.

- **Un-organized manifest** (no `class` on any row) → triggers labeling (detection-order case 2).
- **Mixed manifest** (some rows labeled, some not) → **V1 keeps a flat hard error** naming affected rows. (The partial-label flow is post-V1 — the harder "partially-organized data" category.)
- **Fully-labeled manifest + `--classes` under `train`** → the same asymmetric validation used for organized datasets (below), applied to manifest classes.

**Materialization.** A **fully-labeled** manifest materializes before training: each row's image is copied to `dataset/<row.class>/`, by the same copy mechanism `--folder` uses, originals untouched and the manifest never rewritten. (The un-organized case is already covered — labeling produces output that is copied the same way.) Materialization is what makes `--manifest` and `--folder` converge on one downstream path, and it means manifest input reaches the `dataset/` write path under the same conflict rules.

**Filename collisions.** Two distinct sources can target one path in `dataset/`. A manifest is the obvious case — `/a/img.jpg` and `/b/img.jpg`, both class `cat`, both target `dataset/cat/img.jpg`. A flat folder has unique basenames by construction, but **that guarantee is about source names, not written ones**: `photo.bmp` and `photo.jpg` are distinct sources that both land on `dataset/cat/photo.jpg` once the BMP converts (see *Image validation pipeline*). The rule therefore runs on **post-conversion target names**, on every path. Collisions are resolved by **deterministic suffixing in row order** (`img.jpg`, `img_2.jpg`, `img_3.jpg` — the global `_x` suffix used for checkpoints and exports), with the count reported on completion so the renaming is never silent. *Rejected: erroring on collision, which would reject the ordinary case of same-named files in different source directories.*

**Format is decided by extension** — `.csv` or `.json`, never by content sniffing; any other extension is a hard error naming the two. **CSV requires a header row**, comma-delimited, read with `csv.DictReader` semantics; the first row is always read as the header, so a headerless file fails the `path` column check like any other file lacking it — there is no separate headerless detection, and none is needed once the error reports what the first row actually contained. **Columns beyond `path` and `class` are ignored, not rejected** — manifests exported from other tools routinely carry extras, and rejecting them would break the common case for no benefit.

**Columns.** `path` and `class` remain the only accepted names, matched **case-insensitively with surrounding whitespace trimmed** — normalization, not aliasing. When a required column is absent, the error states that the first row was read as the header and names the columns it found — no judgment about which of them is a plausible alias:

```
✕ Manifest is missing the 'class' column.
  The first row was read as the header. Found: path, label — rename the intended column to 'class' and try again.
```

*Rejected: an alias registry (`filepath`, `file`, `image_path`, `label`, `category`, `target`…), which never stops growing and makes every addition a guess about intent.*

**Path semantics.** Relative paths resolve against **the manifest file's own directory**, not the working directory, so a manifest can sit beside its images and be run from anywhere. **URLs are not supported in V1**; a row whose `path` is a URL is a hard error naming the row, and the message states that URLs are unsupported rather than that the path is invalid — supporting them later then contradicts nothing. Doing so would turn `--manifest` into an acquisition path, duplicating the Fetch Adapter's downloads, retries, and partial-fetch state behind a flag documented as local input.

**Duplicates and contradictions.** Paths resolve to absolute form **before** comparison, so `./a.jpg` and `a.jpg` are one file.

- **Exact duplicate** (same path, same class) → deduplicated, count reported.
- **Contradictory** (same path, two different classes) → **hard error** naming the rows and both classes. Unguessable, and choosing one silently would poison the dataset.

**Missing and unreadable rows** need no manifest-specific rule: a row whose file is absent or undecodable is caught by **pre-flight verification** and reported with its reason alongside any other unreadable input, files untouched.

#### Class-count validation

Training on fewer than 2 classes is meaningless, so a single collapsed **"fewer than 2 classes resolved"** check (0 and 1 are invalid identically) applies uniformly across `fetch`, `label`, `train`, and `run`, and to the **inferred-from-folders** case (a dataset resolving to one class subfolder hits the same error). It fires as **early as possible** — at fetch time, not deferred to train — so a user never fetches a full class before learning the run can't train. `fetch` **cannot infer classes at all** (nothing to infer from), so where `--classes` is absent it **surfaces the class-name prompt where a prompt can fire, and raises a hard error where one cannot** — under `--yes`, or non-interactively. This is the standing fallback hierarchy applied (*try prompt → clean wrapped error → never a raw traceback*, CLI Layer & Conventions), and it is why `MissingParameter` on `--classes` is one of the parser errors the global handler redirects to a prompt; `--yes` errors rather than hanging on it, per the same rule. The same disposition governs `optica label`, which equally cannot infer classes; `train` resolves them from folders and is never caught by it. The two errors — the first for a resolved list below 2 classes, the second for the case where no prompt can fire:

```
✕ --classes requires at least 2 class names. Got: cat
```
```
✕ --classes is required for fetch — nothing to search for.
  Example: optica fetch --classes cat,dog
```

**Class-count enforcement on the labeling-trigger paths** (`optica label` directly, `--folder` under `run`, unlabeled `--manifest` under `run`): **in V1 the 2-class minimum is enforced wherever a session's class list is set** — at session start, and at the resume prompt's adopt-the-new-list branch — as well as at completion, where a session cannot be **marked complete** until at least 2 classes exist. The 2-class minimum is a property of a trainable dataset, enforced uniformly above, rather than a fact about what a session might later become; so every operation that sets a session's classes must satisfy it. **There is therefore no scoped exception in V1** — the minimum is a property of the session regardless of how it was invoked: the relaxation that lets a session *start* below 2 arrives with the fast-follow live add-class feature, not before. Separately, and **only for the `train`/`run` entry points**, training also cannot proceed until that condition is met. This does not apply to standalone `optica label`, which never trains regardless of how the session ends.

#### `--classes` against an already-organized dataset — asymmetric validation

Whenever `train` resolves to an already-organized dataset (via `--dataset`, the default `./dataset/`, or a prior curate/clip run) **and** `--classes`/`-c` is also given, Optica cross-validates the two **asymmetrically**:

- **Named in `--classes` but no matching folder** → **hard error**, blocks training (almost always a typo or stale flag):
  ```
  ✕ --classes does not match the dataset folder structure.
    In --classes but no matching folder: pug
    In dataset/ but not in --classes: golden_retriever
    Fix the --classes list, drop --classes, or rename the folders, and try again.
  ```
- **Folder present but not named in `--classes`** → **not an error** — a legitimate "train on a subset" case, allowed only after an explicit confirmation naming what's included and excluded (never silent; exclude list truncates past 10, `--yes` auto-picks Y):
  ```
  --classes requests training on: cat, dog, bird (3 of 10 folders found)
  Excluded from this run: fish, hamster, lizard, parrot, rabbit, snake, turtle

  Proceed with the 3 requested classes only? [Y/n]
  ```
- **Order of evaluation:** if both occur, the hard error always fires first — a subset question is never asked while an unresolved typo remains.
- Exact match (same set, order-independent) → proceed silently.
- `optica curate --classes …` → warning, flag ignored (curate reads the fetched staging structure).

#### `optica run` resumption and preconditions

When `optica run` detects staged content from a prior interrupted run, it shows a top-level prompt before doing anything:

```
Previous session found:
  ✓ Fetch complete — 150 images across 3 classes
  ✓ Curation complete — 120 images selected
  ✗ Training incomplete — interrupted at epoch 3/10

Resume from last completed step (training)?
[R] Resume   [C] Choose step   [S] Start fresh
```

R resumes from the last incomplete step; C shows a step selector — the four pipeline steps with their status (complete / incomplete / not started), where a step whose inputs are absent is listed but not selectable and says why. **Selecting a step earlier than the last completed one discards the later steps' staging, behind a confirmation**, since re-running an earlier step invalidates what followed it; `--yes` auto-picks R at top level, so this branch never arises unattended; S clears staging and starts clean. When `optica run` calls steps internally, their standalone step-level resume prompts are suppressed (the top-level prompt handles it); warnings and safety prompts still fire (see Implementation Note 19).

**Precondition validation:** every command validates its preconditions before executing and raises a helpful error with fix instructions if unmet — `optica curate` checks staged images exist; `optica train` checks a valid dataset structure; `optica export` checks a trained checkpoint exists; `optica label` checks a flat folder or manifest exists and **resolves `-c` classes the way `fetch` does** — prompting where a prompt can fire, hard-erroring where one cannot. *(In V1 the classes must exist before the browser opens, supplied by flag or at the prompt — the live in-browser class-definition feature that would lift that requirement is a fast-follow addition, so the precondition stands.)*

#### Fetch sources

- **Flickr** — official `flickr.photos.search`. `FLICKR_API_KEY` (requires a Flickr Pro subscription). 3,600 requests/hour per key; same pause/resume pattern.
- **Open Datasets** — Google Open Images. The label mapping and metadata come from **GCS** via httpx; **the image bytes do not** — Open Images is a list of URLs to images hosted elsewhere, predominantly `staticflickr.com`, and the bytes are fetched from there. **No API key on either path.** A label-mapping file is cached in `~/.optica/` on first use and verified on every load (deleted and re-downloaded if corrupt); its exact name and format are deliberately unspecified here, being a pre-implementation-gate item — see the Open Images bucket-structure note under Implementation Notes. **Per image, `Thumbnail300KURL` is preferred, with `OriginalURL` as the fallback where that value is empty** — the thumbnails are ~640×480, comfortably above the 384px maximum any backbone consumes. They are regenerated on request, so the same URL is not guaranteed to return identical bytes twice. `training_data_hash` is unaffected, covering structure rather than contents. **Dead URLs are expected rather than exceptional**, the list being older than the current state of the hosting site, so the fetch **fills to target**: candidates are drawn until `--images-per-class` valid images are collected or the class's candidate pool is exhausted, whichever comes first. **An exhausted pool needs no new failure path** — the shortfall reaches the imbalance warning and the post-deduplication floor re-check like any other short class. Soft cap: warn if `--images-per-class` exceeds `max_open_datasets_per_class` (default 500) per class, before fetch begins; `--yes` auto-confirms.

*(The per-source endpoint, rate-limit and authentication verification items under Implementation Notes are implementation-verification markers on the pre-implementation gate, not open design. **Bing Image Search was a V1 source until Microsoft retired the Bing Search APIs on 11 August 2025**; no keyed web-image source replaces it in V1 — Brave and SerpApi were both considered and rejected as new vendor commitments inside V1 — and a general web-image source is a fast-follow item.)*

#### Undefinable classes in auto modes

Auto modes require concrete, searchable, visual class names. A **blocklist** (case-insensitive) catches negating terms (`not`/`non`/`no…`), catch-alls (`other`, `misc`, `unknown`, …), abstract quality terms (`good`, `bad`, `defective`, …), relative/personal terms (`mine`, `custom`, …), placeholder labels (`class_a`–`class_z`, `label_1`–`label_9`, …), single characters or lone numbers, and abstract non-visual concepts (`safe`, `valid`, `positive`, …). Seed list (implementation extends it):

`other, unknown, misc, miscellaneous, none, undefined, various, else, rest, good, bad, normal, abnormal, defective, damaged, broken, working, faulty, mine, yours, safe, unsafe, valid, invalid, correct, incorrect, positive, negative`

False positives are expected (e.g. `positive`/`negative` in medical imaging). The blocklist triggers a **user-definition prompt**, not a hard block — users override by defining the term concretely. Flow: **blocklist check** → **user-definition prompt** for blocklisted names → **group or separate** sub-terms → **image count** per sub-term (`images_per_class` divided across the sub-terms by floor division, **minimum 10, and the minimum wins**: in the grouped case `images_per_class` becomes a per-sub-term floor rather than a group total, so the group's total may exceed it — intended, and the resolved counts are shown at the confirmation step before any fetch) → **overlap warning** (substring detection, after blocklist resolution; N re-opens **the step that produced the overlapping names** — the user-definition prompt where an overlapping name is a sub-term, the class-list prompt where it is a top-level `-c` name — preserving every other answer, including group-or-separate and the per-sub-term counts, and resuming at the overlap check rather than restarting) → **confirmation step** showing the final resolved class list before any fetch. **CLIP filtering for the grouped case runs after the fetch**, not in this sequence — each image is scored against all sub-terms and keeps its original class label — which is why the grouped path's clip dependency is checked at entry rather than discovered when the scoring begins (see Exceptions). Clean cases (no blocklist, no overlaps) still show confirmation; `--yes` skips it for clean cases only. **The user-definition prompt is the sequence's one non-defaultable step**, so it fires wherever a prompt can fire and raises `OpticaValidationError` where one cannot, naming the blocklisted class and that a concrete definition is required — the same disposition the Python API takes, and the reason an unattended run with a blocklisted `-c` name refuses before any fetch begins rather than blocking on stdin. The group-or-separate pooled-class model is the same mechanism a post-V1 class-merge feature would reuse as a new entry point.

#### Class imbalance and image validation

**Before training, whatever produced the dataset**, if any class holds fewer than **50% of the largest class** (ratio 2.0), warn. Counts are measured after deduplication, for the same reason the hard floor is re-checked there — a class of 45 that is 30 duplicates is not a class of 45:

```
⚠ Class imbalance detected:
  cat: 45 images
  dog: 8 images
  [F] Fetch more for 'dog'   [C] Continue with auto class weighting   [A] Abort
```

**F requests the shortfall** — enough to bring the named class up to the largest class's count; curation's *Fetch More* banner likewise requests enough to restore `images_per_class` selected. **If the fetch yields no new images, that is reported and the prompt re-presents without F**, so an exhausted source cannot loop the user back to the same prompt with the same counts indefinitely.

**`[F]` appears only where the images came from a fetch** — the curate and clip paths, and `optica run` when it acquired. On a dataset the user brought (`--dataset`, `--folder`, a manifest) the prompt offers `C`/`A` only, there being nothing to fetch more from. The check sits with the hard 5-image floor rather than with acquisition: both ask whether the dataset is trainable, so both must run wherever training does. C applies automatic PyTorch `CrossEntropyLoss` weighting (inversely proportional to class counts), logged as `class_weights_applied: true` with per-class weights in the training log and `checkpoint_info.json`; `--yes` auto-picks C. *(In V1 this 50% warning is the only imbalance threshold — the stricter `strict_max_imbalance` hard-error ceiling travels with `--strict` to the fast-follow, so there is no threshold-interaction question at first ship.)*

**Image validation pipeline** (all sources):

```
Per-file       — runs as early as the path allows:
  Format check → Corruption check → Size check
Class-dependent — runs once classes are assigned:
  MD5 deduplication (within-class)
```

**Placement rule: a stage runs early if and only if it does not depend on class assignment.** The three per-file stages run **before the browser opens** for `label` and `curate`, and at ingest for the paths with no UI — clip mode, manifest materialization, and `--dataset`. MD5 deduplication is within-class, and under `label` the class does not exist until the user assigns it, so it cannot move earlier.

**Fetched images are named by zero-padded sequence index within the class** — `0001.jpg`, `0002.png`, extension from the validated format — never by URL basename, which collides and would overwrite a distinct image before MD5 deduplication (a separate, later, class-scoped stage) could ever see it, leaving the reported count short with no record of why. **Numbering continues from the highest index already in the directory**, which is what makes resuming a fetch into an existing `.partial` safe.

**Ownership rule: a stage may write only where Optica owns the bytes.** Those are auto-fetch staging and the copies Optica writes into `dataset/` from `--folder` and manifest rows — and on those paths conversion and resizing take effect **at copy time**, not at pre-flight, so originals stay untouched. On `--dataset` no copy is ever made, so both writing stages **report and neither writes**: a convertible format is used as it stands, and an undersized image raises its quality warning without being resized. The corruption check is read-only everywhere — it excludes a file from the run, it never deletes one, and MD5 deduplication treats `--dataset` the same way: a byte-identical duplicate is excluded from the run, never removed from the user's folder. This is what keeps *`dataset/` — user's choice, Optica doesn't touch* true. **There is one corruption check, not two:** pre-flight *is* this stage, placed at the earliest point each path permits (see *Unreadable images — pre-flight verification*).

Default behavior: **convertible formats** — those Pillow can decode but the pipeline does not target — auto-convert silently (BMP/TIFF → JPG/PNG); corrupt files are excluded and reported per the pre-flight rules; images under **128×128px auto-resize with a quality warning** *(the warning threshold is 128px — half the 224px input of three of the four backbones, where upscaling artifacts turn significant; `efficientnet_b4` is the exception at 320/384, and the threshold does not track the backbone — hardcoded in V1 as 64px was; the `--strict` posture flag that would make sub-threshold size a hard error is a fast-follow addition).* **Deduplication is MD5, within-class only** — realistic duplicates are exact — the same file ingested twice, or the same URL fetched twice from a source that serves stable bytes — so near-duplicate detection is not worth V1 scope; within-class prevents false positives across classes. **One gap is accepted rather than hidden: Open Images thumbnails are regenerated on request, so re-fetching into a class that already holds images can land the same photo twice under differing bytes, which MD5 will not catch.** Perceptual hashing would also pull numpy + scipy in, which is why it is not free — but that cost is the same whenever it lands, so it is not what decides V1. *(This MD5 decision stands for V1; perceptual-hash near-duplicate detection travels with `--strict` to the fast-follow.)*

**Format targets and conversion.** The **targeted set is still JPEG, PNG and WebP** — these pass through untouched. Everything else Pillow can decode is convertible, and that explicitly includes anything **animated** (animated WebP, GIF, multi-frame TIFF), which converts from its **first frame**. Which target a conversion takes is decided by whether discarding information is safe: an image carrying an **alpha channel, a palette, or more than 8 bits per channel converts to PNG** (lossless); everything else converts to **JPEG at quality 90**, flattened to RGB. **A converted file is written with the extension of the format it was written in** — a BMP that converts to JPEG is stored as `.jpg`, never as `.bmp` holding JPEG bytes. That rewrite can make two distinct sources collide on one target name, so the filename-collision rule applies **after** conversion on every path. The quality figure is stated because Pillow's default is 75, which is visibly lossy on a first re-encode — and WebP is targeted rather than converted precisely so the fetched path, where WebP is now common, does not lossily re-encode most of what it downloads.

**Resize.** The 128px check **only ever upscales** — an image whose shorter side already reaches 128px is untouched, so the stage never downscales a large image onto the threshold. Below it, the image is scaled so its **shorter side reaches 128px with aspect ratio preserved** (Lanczos resampling), with no crop and no padding. The operation clears the threshold that triggered it and stops there; sizing to the backbone's input resolution belongs to the training transform, which varies per backbone (see Training → *Input resolution and normalization*).

Both stages are subject to the ownership rule above: they take effect only where Optica owns the bytes, and on `--dataset` they report without writing.

**Post-deduplication floor re-check.** Because deduplication runs after labeling, it can drop a class below the five-image floor that the labeling Finish gate certified — five labeled into `cat`, two byte-identical, four in the dataset. Class counts are therefore re-validated against the same floor **after** deduplication, and a class that falls below it is a hard error naming the class, its counts before and after, and the number of duplicates removed:

```
✕ cat fell below the 5-image minimum after duplicate removal.
  cat: 5 images → 4 unique (1 duplicate removed)
  Add more images for cat and run again.
```

Where the class was produced by labeling, the message adds that the session is resumable; deduplication also runs on the curate, clip, manifest-materialization and `--dataset` paths, which have no session to resume. It runs on `--dataset` for the same reason it runs anywhere: five byte-identical images clear the floor and train on one. A gate that certifies a condition the pipeline then invalidates would make the guarantee false — the floor is enforced at both ends or it is not enforced.

#### `dataset/` conflict — destination already populated

A pre-flight overwrite prompt fires before anything is written. Illustrated with `run --mode label --folder`; the rule below applies to every write path:

```
dataset/ already exists and will be replaced with new labels from --folder:
  cat: 50 images
  dog: 47 images
Continue? [y/N — n to exit]
> n

✕ Aborted. To use your existing dataset, rerun without --folder.
  To create a new dataset at a different path:
  optica run --mode label --folder ./images --dataset ./new-dataset -c cat,dog
```

**The check is keyed to the destination, not to the input flag.** Before any action, every command that will materialize into a dataset destination tests whether that destination exists and is non-empty — `run` in every mode and every standalone command that writes one, with no list to keep current. Keying it to `--folder` is what let eight write paths past it: each new input route had to opt in, and none did. Keyed to the destination, a new route inherits the check instead of remembering it.

**It runs at command start, before the browser opens.** This is why one upfront check covers paths that write incrementally at Finish-time: the check's subject is the **destination's current state**, which is knowable before any work begins — not the write itself. A user is therefore never asked to authorize an overwrite after an hour of labeling.

**The prompt names what is there rather than warning in the abstract** — the per-class listing shown above is the form it always takes, whatever the input route.

**"Overwrite" means replace.** The destination's existing contents are removed before writing. The copy mechanism alone would *merge* — contributing new files alongside old ones — which silently mixes stale images into training data the user believed replaced, and is worse than the deletion they consented to precisely because nothing records it. Merging into an existing dataset is not supported in V1. *(This is a **destructive** prompt under the `--yes` taxonomy, not a safety one: `--yes` does not answer it, and `--force` does not suppress it either — suppressing a prompt whose continue branch deletes data is the destructive auto-confirm that taxonomy forbids without a dedicated flag. **`--overwrite` is that flag**, and it is the only unattended route past this prompt; without it an unattended run refuses and raises `OpticaValidationError`. It is the exact CLI counterpart of the API's per-operation `overwrite=True` for this same prompt. Its default is **N**, for the same reason `.optica.toml`'s overwrite prompt defaults to N: a destructive prompt does not proceed on Enter.)*

#### CLIP Adapter (clip mode)

Model `ViT-B-32` with `openai` pretrained weights, hardcoded in V1:

```python
model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai', force_quick_gelu=True)
```

Images are scored against the template **`"a photo of a {class}"`**, with the class name normalised first — underscores and hyphens become spaces, and the name is lowercased — so `golden_retriever` renders as *"a photo of a golden retriever"*. The score is the **cosine similarity between the L2-normalised image and text embeddings**, compared directly against `clip_threshold`. It is deliberately **not** `logits_per_image`, which open-clip scales by `logit_scale` (≈100) and which would put every value far outside the 0.0–1.0 range the seven bands assume. The blocklist's grouped path scores against each sub-term with the same template. `clip_threshold = 0.25` is calibrated for **this model, these weights, and this template** — all three are variables, and Implementation Note 6's recalibration guidance covers a change to any of them.

**Filtering shortfall.** CLIP discards whatever scores below the threshold, so clip mode fetches **`images_per_class × 2`** and keeps up to `images_per_class` of what survives — one bounded over-fetch pass, never an iterate-until-satisfied loop, which on a source returning consistently low scorers would not terminate usefully. Fetch remains best-effort: a source that exhausts early simply yields fewer candidates. **The post-filter count is reported per class**, so a shortfall is visible rather than silent. Falling below `images_per_class` is not an error — the 5-image hard floor and the imbalance warning already govern whether the result is trainable. *Accepted cost: roughly double the API calls against Flickr. The 2× factor is hardcoded, not a config key — tuning it needs knowledge of the threshold's score distribution.*

Cache is open-clip-torch's default (~600MB); on first use the user is informed with a download progress indicator. **Cached weights are verified on every load; corrupt or partially-downloaded weights are deleted and re-downloaded automatically, with the cache path reported** — the same treatment the Open Images label map receives, and for the same reason: a cache Optica populated is Optica's to repair, not the user's to locate. The failure raises `OpticaCLIPLoadError` (see Exceptions), which is distinct from `OpticaCLIPError` — the latter means only that the `optica[clip]` extra is missing. `clip_threshold = 0.25` (calibrated for these weights) is validated across **7 bands**:

| Range | Treatment |
|---|---|
| Below 0.0 or above 1.0 | Hard error — invalid range |
| Exactly 0.0 | Hard error — disables filtering, defeats clip mode |
| Exactly 1.0 | Hard error — nothing passes, empty classes |
| 0.75 to <1.0 | Y/n prompt — very strict, few images will pass |
| 0.5 to <0.75 | Warn and continue |
| 0.1 to <0.5 | Normal — no warning |
| >0.0 to <0.1 | Warn and continue |

`--yes` auto-confirms warn-and-continue and auto-picks Y on the strict-end prompt. The `0.0` error, on `optica fetch`:

```
✕ --clip-threshold 0.0 disables CLIP filtering entirely.
  clip mode requires a threshold greater than 0.0.
  To skip filtering, use --mode curate instead.
```

On `optica run` the same error also offers `--mode label`, which `fetch` does not accept — the valid values are listed per the command, as the fixed-value-flag rule requires.

**Command scope.** `--mode` attaches to **`optica fetch` and `optica run` only**, and `--clip-threshold` follows the same scope. Every mode is an acquisition concern — Local Adapter for label, Fetch plus Curation Adapters for curate, Fetch plus CLIP Adapters for clip — and none of them affects training, so `train`, `label`, `curate`, and `export` do not accept it. `optica label` and `optica curate` are each a single mode by definition; `optica train --folder` already carries local input in the flag itself, leaving the mode with nothing to express.

On `fetch`, the accepted values are **`curate` and `clip`**; `--mode label` is a hard error, since fetch is remote acquisition and label mode takes local input. The error lists the valid values per the fixed-value-flag rule.

**The CLIP Adapter cannot fire redundantly.** In a two-step workflow, `optica fetch --mode clip` filters at acquisition and `optica train --dataset ./dataset` trains on the result — `train` has no mode to honour, so double-firing is prevented by scope rather than by a guard. `optica run` is likewise unaffected: one invocation resolves one mode and runs one acquisition stage. *Rejected: extending `--mode` to `train` and preventing double-firing with a runtime guard — it makes `train --mode clip` expressible in order to reject it, adding surface for the purpose of refusing surface.*

---

### Labeling & Curation

Both `optica label` and `optica curate` run a temporary local FastAPI server (from `optica[web]`) that opens the browser automatically and shuts down after confirmation. Both are **localhost-only in V1** — the server binds to `127.0.0.1`, is never network-exposed, and shuts down after use. **Only the session Optica itself opened can drive it** — a request that does not carry that session's key is refused. Those two guards are the whole of V1's browser-security surface; anything further is post-V1 rather than an implementing pass's call. Each command labels/curates and stops; neither continues into training on its own (only `optica run` spans the full pipeline).

#### Curation Server

Port from `curation_port` (default `8765`), auto-incrementing to the next free port for **up to 20 attempts**, stopping early at 65535 (the key's own upper bound); if every port in that range is taken, `OpticaBrowserServerError` names the range tried. **The resolved port is reported in the terminal whenever it differs from the configured one** — otherwise a user who set `8765` and landed on `8771` learns it only from the browser's address bar. Staging is preserved on interruption or Ctrl+C.

**Timeout:** `curation_timeout_minutes` (default 60; `0` disables). **This timer governs `optica label` too, where the reset triggers below do not exist — see Labeling UI → *Session timer triggers*.** Two warnings fire at **fixed offsets from shutdown — 30 minutes before and 5 minutes before** — which at the 60-minute default is 30 and 55, the schedule as previously stated. An offset that would fall at or before session start is suppressed; if neither fits (`curation_timeout_minutes` under about 6), a single warning fires at half the configured timeout, so **no configured value produces a silent shutdown**. The offsets are absolute rather than proportional deliberately: five minutes is how long a person needs to save their work and respond, which is a property of the user and not a fraction of the session. Both are shown in terminal and browser; the browser warning includes a "Keep Session Active" button. The timer resets on image select/deselect, tab switch, Fetch More, "Keep Session Active", or a terminal keypress. On timeout, staging is preserved (treated as a Ctrl+C interruption).

**Browser UI (curate):** image grid with click-to-toggle, Select All / Deselect All, per-class **tabs (≤6 classes with short names) or dropdown (7+ classes, or any class name over 20 characters)**, scroll arrows only on viewport overflow, viewport-aware pagination with smart ellipsis, hover zoom (280ms), a low-selection warning (<30% of fetched images selected, or fewer than 10 selected — the same two thresholds that drive the post-Confirm mass-rejection prompt) with a "Fetch More" banner (advisory only — Confirm stays active; only zero selected images in a class disables Confirm), and light/dark mode.

**The browser server's failure exception is `OpticaBrowserServerError`** (port unavailable, browser launch failure) — one class for one subsystem, since `optica label` and `optica curate` run the same server. The qualifier is what avoids colliding in meaning with `OpticaWebError` (the missing-`optica[web]`-extra exception), since bare "server" and "web" otherwise point at the same subsystem. See Exceptions.

#### Labeling UI

Same server, a different page. In V1, classes are provided via `-c` before the UI opens (required); the widget is **radio buttons for 2–5 classes, dropdown for 6+**.

> *Two distinct UI thresholds — do not harmonize.* Curation uses tabs ≤6 / dropdown 7+ (or long names); labeling uses radio 2–5 / dropdown 6+. They are different UIs with independently chosen thresholds. *(The live class-list recompute that would make the labeling threshold dynamic is part of the fast-follow live-class-definition feature; in V1 the labeling threshold is fixed at load, since `-c` classes are known up front.)*

**One browser mechanic, plus the two universal class-name rules it renders, are V1 even though the broader live-class-definition feature is a fast-follow addition:**

The two class-name rules that govern every surface — filesystem-safe validation and case-insensitive duplicate blocking — are stated in CLI Layer & Conventions → *Class-name rules*. Rule 2's **inline** forms are stated there too — the browser's rendering of the rule, not its definition.

1. **"Finish" gating — combined completion check.** "Finish" is gated on **both** conditions: fewer than 2 classes, **or** any class below the 5-image hard floor (which applies to every class, live-added or not). Both a disabled button *and* a persistent inline hint are shown (disabled buttons often don't register clicks):
   ```
   Classes: cat (12 images), dog (2 images)          [Finish — disabled]
   Every class needs at least 5 images. dog needs 3 more.
   ```
   When both conditions are unmet at once, show both in the same hint, not sequentially.

   A class that receives no images blocks Finish like any other below the floor. The recourse is to re-invoke on the same source with a corrected `-c` and **adopt the new list** at the resume prompt: a class with no entries departs without orphaning anything, and labeling continues from where it stopped.

**The labeling interaction.** One image at a time. Progress is committed to staging after each image, and a grid or batch-assign view has no per-image commit point — curate is a grid because its unit of work is a selection state across a whole class, while labeling's unit is a single assignment. The page shows the current image, the class widget, a persistent per-class count row, and a position indicator.

- **Assign** — selecting a class commits the assignment and, with **auto-advance** on, moves to the next image. A persistent *Auto-advance* checkbox, on by default, turns it off for deliberate pacing; it is session-local and never written to config.
- **Next** — always present and **always enabled**. Advancing without an assignment is precisely how an image is skipped, so this control is never conditionally disabled. Gating in this UI belongs to Finish alone.
- **Back** — returns to the previous image with its assignment shown and selected. Changing it re-commits to staging, and with auto-advance on, re-assigning returns to the position the user came from: the same rule applied consistently rather than a special case.
- **Finish** — gated on the two conditions above.

The layout reserves a secondary region alongside the focused image, unpopulated in V1. The fast-follow read-only preview strip occupies it, and a design that fills the viewport with a single image would have nowhere to put it later; the empty-state screen and add-class control fit the same frame.

**Session timer triggers.** The curation server's idle timeout governs labeling too, but its listed reset triggers are curate's — tab switch and Fetch More do not exist on this page. In labeling the timer resets on **class assignment, Back or Next, toggling auto-advance, "Keep Session Active", or a terminal keypress.** Without this, a user labeling steadily would be shut down mid-session by a timer that never saw a qualifying event.

**Finish with images left unlabeled.** Skipping is legitimate, so unlabeled images never block Finish — but they are never excluded silently either. A confirmation names the count, **split by cause**, because one number hides two different situations: a user at image 30 of 200 has not made a decision about the remaining 170, whereas a user who reached the end and passed over them has.

```
32 images will not be included: 4 skipped, 28 not yet reached.
```

`--yes` does **not** answer browser-side confirmations. It exists for unattended runs, and a user pressing Finish in a browser is present by definition; it continues to govern terminal prompts, including the `--classes` subset confirmation. *Rejected: blocking Finish until every image is labeled, which would force assignments on images the user deliberately declined.*

#### Unreadable images — pre-flight verification

Applies wherever images enter the pipeline — `label`, `curate`, manifest materialization and `--dataset` — since pre-flight *is* the per-file stage of the validation pipeline, run at the earliest point each path allows. Scope is the same everywhere; only disposition varies, and it varies by ownership rather than by command.

An image that is merely **irrelevant** needs no mechanism: in `label` the user advances without assigning, in `curate` the user leaves it unselected. A **corrupt** image is a different problem — it cannot be rendered into the page at all, so no interaction design reaches it. Curation's exclusion was presumed to cover bad images; it covers irrelevant ones only, since a grid cannot draw a thumbnail for a file it cannot decode.

Every file is therefore opened and verified **before the browser opens** — headers validated rather than fully decoded, which is cheap and happens on the path to producing thumbnails anyway. This is not a second mechanism: it is the image validation pipeline's per-file stages, run at the earliest point this path allows, per that section's placement rule. **On the auto-fetch path that earliest point is the write into staging, not a separate pass before the browser** — Optica first owns those bytes at fetch-write, and fetch precedes the browser in the same run, so the check is both *earliest permitted* and *before the browser opens* without running twice. The pre-browser pass therefore covers user-provided images. A standalone `optica curate` over already-staged images does not re-check them: they were checked when they were written. Reasons are reported as the decode attempt gives them (could not be opened, format Pillow cannot decode, truncated file, zero bytes) and are never elaborated into judgements about image quality, blur, or relevance.

**Disposition follows ownership** — the same partition the validation pipeline's *Ownership rule* draws. **User-provided images** — `label`'s folder, manifest rows, and a `--dataset` the user brought — are never staged or deleted, so unreadable files are dropped from the run, left untouched on disk, and **listed individually with their reason** (truncating past 10, as the class-subset exclude list does), because the user owns these files and can repair or replace them. **Auto-fetched images** — `curate` and `clip` — are silently deleted when rejected; an unreadable download is discarded under that same rule and reported as an **aggregate count**, since the user never chose those files and cannot act on them.

**Where it is reported.** In the terminal before launch, again as a dismissible notice on the page's first load, and in the completion line's details clause when non-zero. The browser notice is not redundant: a user spends the session looking at the browser with the terminal behind it, and would otherwise see 200 images where the folder held 202 with no way to learn why.

**Zero readable images aborts before the browser opens,** with the count and reasons. Opening a UI onto an empty session, so the user discovers the problem by finding nothing to do, repeats the failure the pre-flight check exists to prevent. Zero is the only shortfall determinable up front — whether a class will clear the five-image floor depends on assignments not yet made.

*Rejected: lazy detection on render, which moves the per-class counts under a user already being held to the Finish gate; and deleting unreadable user-provided files, which the deletion rule forbids outright.*

#### Terminal-side completion for browser steps

`curate` and `label` produce **no terminal output when they finish** — the browser closes and the terminal is silent, leaving piped/unattended runs with no record. V1 closes this by reusing the existing `✓ X complete — details` / `✗ X incomplete — reason` vocabulary, printed the moment a browser step hands control back:

```
✓ Labeling complete — 45 images labeled across 3 classes
```
```
✗ Labeling incomplete — session ended with 1 class (minimum 2 required)
```

This reuses existing vocabulary (no new format) and doesn't conflict with the `optica run` resume summary, which fires only for interrupted sessions on a later invocation. *(It applies to standalone `curate`/`label` invocations as well as inside `optica run`: a standalone invocation in a script is the case with no other record.)*

#### Deletion, staging, and interruption

Deletion rules: auto-fetched images are silently deleted if rejected; **user-provided images are always copied, originals untouched** (never staged or deleted). Auto-fetch staging lives at `~/.optica/staging/<class_name>/`. Interruption handling:

- **Fetch interrupted** — staged images preserved and the class directory left as `.partial`, resume prompt next run; "Start fresh" always available.
- **Curation interrupted** — staged images **and in-progress deselections** preserved, resume prompt; "Start fresh" available. Timeout treated as interruption.
- **Labeling interrupted** — progress saved incrementally to `~/.optica/staging/labeling/<session_id>.json` after each image; session ID = a digest of the folder path (folder labeling) or of the manifest path plus its content hash. Resume prompt on next `optica label` for the same source; "Start fresh" always available, and "adopt the new list" when `-c` disagrees with the session's stored classes (see *Staging shapes*).
- **Training interrupted** — checkpoints handle recovery (see Training).
- **Export interrupted** — exports write to `<output>/.<export-folder-name>.partial/` and rename it to `<output>/<export-folder-name>/` in one OS operation (atomic — the complete folder appears or nothing does). **The temp folder is a sibling of its final path, inside `--output`, because a rename is atomic only within one filesystem** — a temp under `/tmp` or `~/.optica/` with `--output` on a different mount degrades silently to copy-then-delete, which is the partial-output state this design exists to prevent, and it would degrade only on some users' machines. This is the same `.partial`-then-rename convention fetch uses for `~/.optica/staging/<class_name>.partial/`. Partial output is never visible, and any `.partial` folder left in `<output>` by an interrupted run is removed before the next export writes.
- **`optica run` interrupted** — the R/C/S top-level prompt (see Input & Acquisition).

**Mass rejection** (after Confirm in the browser): two independent triggers — percentage (any class with <30% of fetched images selected) and absolute minimum (any class with fewer than 10 images selected). Each fires with its own message; the terminal prompt offers F (fetch more, reopen curation) / C (continue anyway) / A (abort, staging preserved). Picking **C raises a confirmation** — `Continue with the current selection? [y/N]` — defaulting to N, since continuing past a mass-rejection warning is the consequential branch. Answering N returns control to F/C/A. Both prompts are registered in the `--yes` table, which is the source for what each takes — leaving the second unanswerable would strand an unattended run at exactly the point `--yes` exists to get past.

#### Staging shapes

**Three staging shapes, differing in kind.** Auto-fetch staging is `~/.optica/staging/<class_name>/` — a *directory of image files* that curation reads directly, whose shape is the directory layout itself. The other two are *state files*, specified below. Training state is not staging (it lives with the checkpoint in `./checkpoints/` as `checkpoint_info.json`), export needs none because its atomic write substitutes for resumability, and the Open Images label map in `~/.optica/` is a verified cache rather than session state.

**Fetch completion.** Fetch writes into `~/.optica/staging/<class_name>.partial/` and renames each directory to its final name when that class's fetch completes — including when a source is exhausted and yields fewer than `images_per_class`, which is a *completed* fetch rather than a partial one. **The resume prompt for an interrupted fetch belongs to `optica fetch` (and to `optica run`, which sequences it); every other command that reads staging — `optica curate` standalone above all — reports the incomplete fetch and proceeds with what is there, never offering to resume it.** The presence of a `.partial` directory therefore means interrupted, which is what lets the `optica run` resume summary tell an interrupted fetch from a finished one; resuming fetches into the same directory and renames on completion. `config --clear-staging` lists `.partial` directories alongside complete ones, and a command that reads staging while one is present reports the incomplete fetch before proceeding. This reuses export's atomic-move pattern rather than adding a state file. *Rejected: comparing staged image counts against `images_per_class`, which cannot distinguish an interrupted fetch from an exhausted source — it would offer, on every subsequent run, to resume a fetch that can never produce more.*

**Labeling session file** — `~/.optica/staging/labeling/<session_id>.json`, one per source. A folder path cannot be a filename, so the session ID is a **digest** of the identifying inputs and the readable source path is recorded inside the file, where `config --clear-staging` reads it to list something meaningful.

```json
{ "version": 1,
  "source": "/home/u/images", "source_type": "folder",
  "created": "…", "updated": "…",
  "classes": ["cat", "dog"],
  "auto_advance": true,
  "position": "/home/u/images/IMG_0413.jpg",
  "entries": { "/home/u/images/IMG_0001.jpg": {"state": "labeled", "class": "cat"},
               "/home/u/images/IMG_0002.jpg": {"state": "skipped"} } }
```

- **Absence from `entries` means *not yet reached***, which is what makes the Finish confirmation's split between skipped and unreached computable. Skip is a recorded state, not a gap.
- **Assignments reference classes by name.** The file is rewritten in full on every commit regardless, so a rename — which arrives with live class definition — is a map over data already being rewritten rather than a new cost, and case-insensitive duplicate blocking guarantees names are unique. *Rejected: stable class IDs, whose only advantage is a cheaper rename that is not actually expensive, paid for with indirection in a file whose readability matters most when a resume has gone wrong.*
- **`classes` is a list that may grow and whose entries may be renamed**, so that live class definition persists to it on every add and rename without a shape change.
- **A session file that cannot be read or parsed is a hard error, not a recoverable prompt.** `OpticaLabelingError` for the labeling session file and `OpticaCurationError` for `curation.json` — the class is the subsystem whose contract the file belongs to — carrying the file path and, in the fix line, the remedy: delete it and start clean, forfeiting that session's progress. Recovery is not attempted — the file records per-image decisions, and a partially-parsed one would silently discard some of them, which is worse than losing all of them visibly.
- **A `-c` list that disagrees with `classes` is a conflict, not an override.** The session ID digests the identifying inputs — the source path, plus the manifest's content hash where the source is a manifest — and never `-c`, so re-invoking the same source with a different `-c` resumes the same session. The mismatch is detected before any image is read and the resume prompt carries a third option alongside Resume and Start fresh: **adopt the new list**. Adopting deletes every entry assigned to a departing class — absence from `entries` already means *not yet reached*, so those images return to the queue to be relabeled under the corrected names, and no new state is introduced. Per the standing rule that conflict prompts fire before any action. `--yes` picks Resume, as its table already records; adopting is never automatic.
- **Ordering is path-sorted and deterministic**, so the image list is not stored; **`position` records a path, not an index**, so files added or removed between sessions shift nothing. **On resume `position` resolves to the first unlabeled image at or after it in path order** — which covers the case where the recorded file is itself gone, since the next unlabeled entry is then simply the one that follows it; if nothing remains, the session is complete. One rule rather than a special branch for removal.
- **The pre-flight exclusion list is deliberately not persisted.** Pre-flight re-runs on resume and reaches the same verdict; storing it would create a second source of truth able to disagree with the disk.

**`version` mismatch is a hard error.** Both session files open with `"version": 1`; a file whose version this build does not recognize gets the same disposition as one that cannot be parsed — a hard error naming the path and instructing the user to delete it and start fresh, in each file's own class. The field exists to be checked, and ignoring it would make it decoration. *(In V1 only version 1 exists, so this never fires; the decision is made once and the field is what a later build reads.)*

**Curation session file** — `~/.optica/staging/curation.json`. Auto-fetch staging is not session-namespaced, so exactly one curation session exists at a time and no session ID is needed.

```json
{ "version": 1, "created": "…", "updated": "…",
  "deselected": { "cat": ["…0007.jpg"], "dog": [] },
  "active_class": "cat" }
```

Records **deselected** paths rather than selected ones: it is the smaller set, and it makes images added by Fetch More default to selected with no special case. Without it, a user who answers **R** to the curation resume prompt is returned the images with every judgement discarded — a resume that restores inputs but not decisions, which is not what the prompt offers. **An entry is matched to a staged image by its class and file name, not by its full path**: staged names are unique within a class, while a class directory is renamed when its fetch completes, so a full-path match would silently return deselected images to the selection.

**Both files are written on every decision** — after each image in labeling, on each toggle in curation — by writing a temp file and moving it into place in one OS operation, the same atomicity export already uses. *Rejected: debouncing curation writes, which would place the mechanism's only gap precisely at abrupt endings, the case it exists for, and would depend on page-unload handlers to close it — note that this rejection also rests on local-loopback latency, and a remote server would reopen it; and persisting on tab switch alone, which stores nothing for a user who curates a single class and never switches.* Per-toggle persistence makes each toggle a server round-trip rather than client-held state committed at Confirm — negligible on localhost, but a real change to the interaction model.

**"Start fresh" deletes the staging and any state file that accompanies it.** For an interrupted fetch there is no state file — the `.partial` directory is itself the state, and deleting it is the whole operation. *Accepted limitation:* it does not clear that class's entries in `curation.json`, which is curation's file rather than fetch's — and since a re-fetch numbers from `0001` again, a deselection recorded before a start-fresh applies to whichever new image takes that name, which then opens already deselected. Closing that crosses a subsystem boundary and is post-V1.

> *Accepted limitation — single-session staging.* Auto-fetch staging is unnamespaced beneath a per-user `~/.optica/`, so exactly one curation session can exist at a time; `curation.json` inherits that constraint rather than introducing it. The labeling session file, namespaced by source digest, is unaffected. Should a later server serve concurrent sessions, the change is scoped and known: staging becomes session-scoped and the curation file follows it. Not designed for now — recorded so it is found by reading rather than by colliding with it.

---

### Training

#### Training Engine

```
1. Load + stratified split of dataset (random_state generated once, saved to checkpoint for reproducible resume)
2. Apply transforms (augmentation on by default)
3. Load pretrained base model (timm)
4. Freeze base layers
5. Replace classification head
6. Phase 1: train head only (1 - finetune_ratio of total epochs, minimum 1)
7. Phase 2: unfreeze last layers, fine-tune (finetune_ratio of total epochs; no minimum — Phase 2 is the phase skipped where the allocation leaves 0)
   — early-stopping counter resets at phase boundary
8. Track progress (Rich live display)
9. Log metrics per epoch (JSON) — written incrementally after each epoch
10. Save top N checkpoints — each save evaluates the held-out test split for that checkpoint
```

The steps are classification-specific as written, but `engine.py` must be built as a **generic training loop that accepts task-specific components — loss function, metric computation, head architecture — as injected inputs**, not hardcoded assumptions. This is an implementation discipline, no extra code: adding a post-V1 task means supplying new injection points, not rewriting the loop. Relatedly, `models.py` **separates `load_backbone()` (generic, timm) from `configure_head()` (task-specific)**, and head replacement takes `num_classes` as an **explicit parameter** rather than inferring it — so post-V1 can call `replace_head(model, num_classes=old + new)` without a signature change. **For classification, `configure_head()` stays timm-native** — `replace_head(model, num_classes=N)` is `model.reset_classifier(num_classes=N)`, producing exactly the parameter names `timm.create_model(base_model, num_classes=N)` builds. This is a constraint, not an implementation preference: the exported `model.pt` is a `state_dict` whose documented two-line reconstruction depends on those names matching (see Export → *Artifact contents*), so a custom head here would silently break every exported artifact. The `load_backbone()`/`configure_head()` split exists for post-V1 **task** types, not to make classification's head non-standard.

**Two-phase training:** `finetune_ratio = 0.70` (Phase 2 uses 70% of epochs, Phase 1 the rest), the phases always sum to `--epochs` exactly — `phase1 = max(1, floor(epochs × (1 - finetune_ratio)))`, `phase2 = epochs - phase1`, and if that leaves `phase2 = 0` — reachable only at `epochs = 1` — **Phase 2 is the phase skipped**, which is the `--epochs 1` case below. Allocation uses `floor` with an explicit clamp rather than `round`, so no half-value case arises (`epochs = 5`, `finetune_ratio = 0.70` → 1 + 4; `epochs = 10` → 3 + 7; `epochs = 2` → 1 + 1). The 1-epoch minimum applies only to phases that exist: at `finetune_ratio` exactly `0.0` or `1.0` the edge cases below govern and one phase is skipped. `finetune_ratio = 0.0` → warn, head-only (no Phase 2); `1.0` → warn, no head warmup (no Phase 1); `--epochs 1` + default ratio → confirm prompt (Phase 2 skipped if Y; `--yes` confirms); `--epochs 1` + `0.0` → warn only. Early stopping resets at the Phase 1 → 2 boundary — each phase has its own independent window.

**Optimization.** V1's loss is `CrossEntropyLoss`, **unweighted by default** — the inverse-frequency weighting described in Input & Acquisition applies only when the user selects C at the imbalance warning, and is the exception rather than the norm. The optimizer is the `optimizer` config key: default `adamw`, permitted `adamw` / `adam` / `sgd`, with hyperparameters **fixed in V1 and exposed at no tier** rather than configurable (AdamW `weight_decay = 0.01`, Adam `weight_decay = 0`, SGD `momentum = 0.9`; every other optimizer hyperparameter — `betas`, `eps`, `nesterov`, `dampening` — stays at its PyTorch default). **There is no learning-rate scheduler in V1** — a decision, not an omission: the two-phase structure already supplies the rate schedule, and a scheduler would need its own specified interaction with the per-phase early-stopping reset. **Phase 2 runs at `learning_rate × 0.1`** — a hardcoded multiplier rather than a config key, because unfreezing backbone blocks at the head-warmup rate is the standard way to damage the pretrained weights the two-phase design exists to protect. The single `learning_rate` in `checkpoint_info.json`'s `config` block is the **base** rate — Phase 1's rate, and the value Phase 2's multiplier applies to — not a record that both phases share one rate.

**Dataset splitting.** The split at step 1 is **stratified per class**, never a random split of the pooled dataset — the 5-image hard floor makes an unstratified split unsafe, since at `val_split = 0.15` a 5-image class expects 0.75 validation images and can land with none, leaving `val_accuracy` (which ranks checkpoints) computed over a set missing that class entirely. Per class of *n* images, applied in this order: `n_val = max(1, floor(n × val_split))`; `n_test = min(floor(n × test_split), n − n_val − 1)`; `n_train = n − n_val − n_test`. Every class is guaranteed at least one training and one validation image, the remainder biases toward training, and allocation uses `floor` with an explicit minimum rather than `round` — so there is no half-value case to resolve. Worked: *n* = 5 → 4/1/0; *n* = 20 → 14/3/3; *n* = 100 → 70/15/15, the configured ratio exactly. **Small classes can hold no test images**, which is the accepted trade against the 5-image floor. Per-class split counts are written to the training log at run start, so a class with an empty test allocation is visible in the record rather than implicit.

**Test evaluation.** `test_split` is consumed: whenever a checkpoint is saved, that checkpoint is evaluated on the held-out test split and `test_accuracy` / `test_loss` are written into its `checkpoint_info.json` beside the val metrics — which keeps that file's write-at-save-time rule intact and means every checkpoint carries its own test result regardless of which rank is later exported. `model_info.json` copies both at export. **Test metrics never influence checkpoint ranking or early stopping**, which stay on `val_accuracy` and the early-stopping metric respectively; ranking on a held-out set would stop it being held out. When no class received a test allocation, both fields are `null` rather than `0`.

**Early stopping.** `early_stopping` is a patience count in epochs, and what it monitors is **`val_loss`**, with `min_delta = 0.0` — any improvement, however small, resets the counter. `val_loss` rather than `val_accuracy` because the stratified split floor permits a single validation image per class at the 5-image minimum, where accuracy takes only a handful of discrete values and patience-based stopping on it is uninformative; `val_loss` stays continuous at that scale. The two metrics do different jobs deliberately — `val_loss` decides when to stop, `val_accuracy` decides which checkpoints to keep. **No best-weight restoration occurs, and none is needed:** top-N checkpoints are saved and ranked as training proceeds and export selects from those, so the in-memory model at the moment of stopping is never what gets exported. `early_stopping = 0` disables the mechanism (see Configuration → *Numeric range validation*).

**"Last layers" per architecture** (verify exact names against timm's `model.named_parameters()` at implementation — a pre-implementation-gate item, since timm layer names change between releases):

| Flag | timm name | Layers to unfreeze in Phase 2 |
|---|---|---|
| `efficientnet-small` | `efficientnet_b0` | Last 2 MBConv blocks (`blocks[5]`, `blocks[6]`) + `conv_head` + `bn2` |
| `efficientnet-large` | `efficientnet_b4` | Last 2 MBConv blocks + `conv_head` + `bn2` |
| `resnet` / `resnet-50` | `resnet50` | Last residual layer (`layer4`) |
| `mobilenet` / `mobilenet-large` | `mobilenetv3_large_100` | Last 3 blocks + `conv_head` |

**Input resolution and normalization follow the backbone, resolved from timm.** `timm.data.resolve_model_data_config(model)` returns `input_size`, `mean`, `std`, `interpolation`, `crop_pct` and `crop_mode` for the selected model, and those values drive both the training transforms and the exported preprocessing metadata — all six are exported, not `input_size` alone. **Augmentation is on by default and replaces the centre crop with a random one**, so `crop_pct` and `crop_mode` configure the exported preprocessing rather than the default training transform. The six values are resolved per model rather than shared across the four backbones: `efficientnet_b0`, `resnet50` and `mobilenetv3_large_100` are 224px models, while `efficientnet_b4` (`efficientnet-large`) trains at **320** and tests at **384** under its default `ra2_in1k` tag. **V1 uses the training `input_size` throughout** — training, validation, export and inference from the exported artifact all preprocess at the same resolution, so `model_info.json`'s `input_size` is the single number a consumer needs and no stage has to choose between two. `efficientnet_b4`'s 384px test size is deliberately unused in V1; one resolution per model costs a little top-1 accuracy on that one backbone and removes the question entirely. Fixing all four at 224 was rejected — it would run the one model users select *for* accuracy below its pretrained resolution, and would make `model_info.json`'s `input_size` a constant field. *Accepted cost: `efficientnet-large` processes roughly twice the pixels per image, which matters most on CPU.*

**CPU batch-size prompt:** if no GPU and `batch_size > 16`, prompt before training. It is a **safety prompt** — it fires inside `optica run` too (not suppressed), and `--force` (not `--yes`) is what would suppress it:

```
⚠ Training on CPU with batch_size 32 may cause memory issues on modest hardware.
  Consider reducing: optica train --batch-size 8 or optica config --set batch_size 8
  Continue anyway? [Y/n — n to adjust batch size]
```

**OOM handling:** `MemoryError` and `torch.cuda.OutOfMemoryError` during training are re-raised as `OpticaTrainingError` with batch-size-reduction instructions. **Rich progress display** and **augmentation** (on by default, `--no-augmentation` to disable): random flip, rotation ±15°, color jitter, random crop. `random_state` is generated once at run start and saved, guaranteeing an identical split across interruptions (prevents silent data leakage on resume).

#### Terminal completion

`optica train` prints nothing on success, which leaves piped and unattended runs with no record of what was actually run — the same defect the browser steps have, and it is closed the same way, reusing the established `✓ X complete — details` vocabulary rather than a new format. The `✗` form already exists (`✗ Training incomplete — interrupted at epoch 3/10`, shown in the `optica run` resume prompt); this is its missing counterpart:

```
✓ Training complete — best val_accuracy 0.852
  Epochs: 8 of 10 (stopped early — val_loss, patience 5)
  Phases: 3 head warmup + 7 fine-tune
  Test: accuracy 0.834, loss 0.391
  Checkpoints: 3 saved in ./checkpoints/
```

The detail lines exist because each reports a value the user did not supply directly and cannot otherwise see. **Epochs** shows run-against-requested, so early stopping is visible rather than silent (`Epochs: 10 of 10` when it did not fire, with the parenthetical omitted). **Phases** shows the allocation the rounding rule produced from `--epochs` and `finetune_ratio`. **Test** reports the held-out result; where the split left classes without a test allocation it says so — `Test: accuracy 0.834, loss 0.391 (2 classes absent from test set)` — and where no class received one it reads `Test: not evaluated — no class received a test allocation` rather than printing a number over an empty set. Printed for standalone `optica train` and inside `optica run` alike, on the same reasoning the browser-step completion uses: a scripted invocation is the case with no other record.

#### Checkpoints

Top N saved per run. Folder naming: `checkpoint_val<accuracy>_epoch<n>/`, with the **global `_x` collision suffix** (`_2`, `_3`, …) — the standard sequential-collision suffix used everywhere in Optica. Collision checking is the **active `checkpoints/` folder only**; archived checkpoints are excluded.

A **Keep/Archive/Delete/Select (K/A/D/S)** prompt fires at the start of every standalone `optica train` run when any prior checkpoints exist — **it is suppressed inside `optica run`**, where one of its four branches deletes every prior checkpoint part-way through a pipeline; checkpoints accumulate across `run` invocations until the soft warning at `3 × max_checkpoints`, which is the backstop for exactly this. Unattended runs are unchanged either way — `--yes` answers K where the prompt fires, and inside `optica run` it does not fire at all — **except in a standalone run where a resumable checkpoint is present, in which case the resume prompt below fires first and K/A/D/S is skipped entirely** if the user resumes. Ordering matters because one branch is destructive: `D` and `A` would remove or move the very checkpoint the resume prompt is about to offer, so the non-destructive decision is taken first. Declining the resume starts a fresh run, and K/A/D/S then fires normally over the prior checkpoints:

```
What would you like to do?
  K  Keep all
  A  Archive all (moved to checkpoints/archive/<timestamp>/ before new training starts)
  D  Delete all
  S  Select — choose per checkpoint [K/A/D per checkpoint]
```

`--yes` auto-picks K (non-destructive). A soft warning fires when kept checkpoints exceed `3 × max_checkpoints` (default 9); `--yes` confirms it. **Archive folder timestamp is `YYYYMMDD_HHMMSS` — year-inclusive.**

**Training resume prompt.** When the active checkpoints folder holds any checkpoint marked `"interrupted": true`, `optica train` offers to resume before anything else:

```
Training was interrupted at epoch 7 of 10 (checkpoint_val0.852_epoch7).
Continue from checkpoint? [Y/n]
```

The prompt is genuinely binary — Y continues, N starts a fresh run — which is why it is Y/N where the multi-option prompts are not. `--yes` answers **Continue**, as the `--yes` table records. **The resumable checkpoint is the newest one carrying `"interrupted": true`**; older interrupted checkpoints are left alone and fall to K/A/D/S on a fresh run. What a resume restores is phase state and `random_state`; Implementation Notes 15 and 16 index both.

> *Deliberately aligned — the earlier asymmetry was removed on purpose.* Archive timestamps, log filenames and `run_id`, and export subfolder names (see Export) all carry `YYYYMMDD_HHMMSS`: **wherever a timestamp appears in a name or an identifier, it takes that form** — year-inclusive, so the timestamp dates the artifact on sight and sorts correctly across a year boundary. A field whose value is a time rather than a name or an identifier — `training_timestamp`, `export_timestamp` — is ISO-8601 and sits outside this rule. The plan previously omitted the year from exports on the grounds that exports are not long-term artifacts — a premise that was wrong on its own terms, since the export folder is the self-describing bundle users keep and share, and for those users the cost of getting the name wrong is permanent, because a name is fixed when it is written and cannot be corrected once the artifact has left. **Do not re-separate them.**

**Global ranking at export time:** all active-folder checkpoints are ranked by val accuracy; tie-break is higher epoch, then older timestamp (documented, not configurable in V1). The **export checkpoint selection prompt** (when `--checkpoint-rank` is not specified) lists available checkpoints; `--yes` auto-picks rank 1. Rank validation (via the global handler and the validate-all-upfront rule):

- `0` or negative → hard error (rank must be ≥ 1)
- non-integer → wrapped error (whole number required)
- nonexistent rank → early existence check listing available checkpoints
- multiple mixed values → validate all upfront, report all invalid at once

*(`--checkpoint` is a permanent alias for `--checkpoint-rank`; the prompt accepts multiple ranks.)*

#### `checkpoint_info.json`

Written immediately when each checkpoint is saved (not at run end); two amendments follow it — `"interrupted": true` if training is interrupted afterward, and the run-end pair `epochs_trained`/`early_stopped` described below. It travels with the checkpoint on archive, so it stays self-describing regardless of location.

```json
{
  "run_id": "20260312_143022",
  "model_family": "efficientnet-small",
  "base_model": "efficientnet_b0",
  "classes": ["bird", "cat", "dog"],
  "num_classes": 3,
  "val_accuracy": 0.852,
  "val_loss": 0.342,
  "test_accuracy": 0.834,
  "test_loss": 0.391,
  "epoch": 7,
  "training_phase": 2,
  "phase1_epochs_completed": 3,
  "phase2_epochs_completed": 4,
  "early_stopping_counter": 1,
  "training_timestamp": "2026-03-12T14:30:22",
  "interrupted": false,
  "random_state": 42,
  "class_weights_applied": false,
  "class_weights": null,
  "training_data_hash": "817f7abba1a5828f80c308d801e03cb9",
  "dataset_path": "/home/user/projects/pets/dataset",
  "config": { "epochs": 10, "batch_size": 32, "learning_rate": 0.001,
              "augmentation": true, "early_stopping": 5, "finetune_ratio": 0.70 },
  "epoch_history": [ /* epochs up to this checkpoint only */ ],
  "log_file": "~/.optica/logs/run_20260312_143022_efficientnet-small_3classes.json"
}
```

**`classes` is the origin of the class array, in sorted `ImageFolder` order** — the same order that becomes the model's output-index order, and the order `export` propagates to `class_names.json` and `model_info.json` (see Export → *Artifact contents*, where the rule is stated in full). It is written here first and read from here at export, so anything else would be inherited downstream and would silently disagree with the model's outputs.

**`class_weights` is `null` unless weighting was applied, and an array of floats index-aligned with `classes` when it was** — one weight per class, same order, matching `class_weights_applied`. The alignment is not a convention borrowed from `class_names.json` but what the consumer requires: `CrossEntropyLoss(weight=…)` takes a tensor in output-index order. *Rejected: a class-name → weight object, which would be immune to ordering drift but would add a second representation of an order the rule above already fixes once — two things that can disagree in place of one that cannot.*

**Two fields are written at run end, not at save time** — `epochs_trained` (the run's total completed epochs) and `early_stopped`. Neither is knowable when a checkpoint is saved: a checkpoint written at epoch 7 cannot know the run went on to 8. At run end they are written into **every retained checkpoint's** `checkpoint_info.json`, by the same post-save amendment that adds `"interrupted": true`, so `optica export` reads them from its single stated source and an export of a **non-rank-1** checkpoint still reports the run's totals rather than that checkpoint's epoch. Both are copied into `model_info.json` at export.

**`early_stopped` is set by the training loop, never derived.** It is `true` only where the run ended because the early-stopping patience was reached — `false` where it exhausted `--epochs`. Deriving it from `epochs_trained < config.epochs` would report a **Ctrl+C interruption** as an early stop, which it is not. An interrupted run never reaches the run-end amendment, so its checkpoints carry `"interrupted": true` and **neither of these two fields**; a consumer reading a checkpoint without them is reading one whose run did not finish.

Two fields support post-V1 incremental learning:
- **`training_data_hash`** — an MD5 of the dataset directory **structure** (folder/file names and counts, **not** file contents). The serialization is exact, because the hash must be stable across runs to serve any purpose: **MD5 over the UTF-8 sorted relative paths of every file under the dataset root, one per line, `\n`-joined, with no trailing newline.** Counts are implicit in the number of lines rather than separately encoded, and the dataset root's own name is excluded — so relocating a dataset does not change its hash, which is what `dataset_path` records separately. It lets post-V1 incremental learning detect whether the dataset changed since the checkpoint was saved. *(`num_classes` was already present in the block above and is unchanged; the `num_classes` that `replace_head()` takes in `models.py` is a different thing entirely.)*
- **`dataset_path`** (absolute) — the original training dataset path, written here at training time and **copied into `model_info.json` at export** (export itself doesn't know the training dataset; it reads `checkpoint_info.json`, exactly as `log_file` already flows). Absolute because `--dataset` can point outside the project, leaving a relative path no stable root; post-V1 incremental learning requires it (and, if the path is gone at that time, must error and prompt — never silently proceed). **Path form:** `log_file` is stored in **tilde form**, written unexpanded and expanded only on read — `~` is precisely what conceals the username. `dataset_path` cannot do the same, because `--dataset` may point outside the home directory entirely, leaving nothing for `~` to abbreviate. *Accepted cost: absolute paths leak machine-local structure into an artifact users may share, and `log_file` does not share that cost.*

#### Training log

Written incrementally after each epoch to **both locations simultaneously**:
- `~/.optica/logs/run_<YYYYMMDD>_<HHMMSS>_<model>_<N>classes.json` — global, persistent
- `<output>/logs/run_<YYYYMMDD>_<HHMMSS>_<model>_<N>classes.json` — project-local, portable. **Follows `--output`** (default `./optica-output`); a log written to a directory unrelated to the run is neither project-local nor portable

**Both locations are permanent and user-managed: no rotation, no cap, no clearing command.** This is deliberate, and the staging-versus-permanent distinction is stated at both sites on purpose — here and at `config --clear-staging`. That command exists because staging is hidden **and large** — it holds images and reaches gigabytes, so a user who cannot find it also cannot afford to leave it. A training log is a few KB of JSON, so a thousand runs is a few megabytes, and the run history is the record of what happened. **Hiddenness alone is not the criterion; hiddenness plus size is.**

`run_id = YYYYMMDD_HHMMSS`, matching the log filename exactly (year-inclusive, consistent with the archive timestamp and with export subfolder names — the same form every timestamped name and identifier carries). On interruption, `"interrupted": true` and `"interrupted_at_epoch": N` are added; completed epochs are always preserved. The log carries `classes`, `num_classes`, `dataset_path`, image counts, `random_state`, `class_weights_*`, the `config` block, per-epoch metrics, best/early-stopping fields, and `checkpoint_paths`.

> *Accepted limitation — do not "fix".* `checkpoint_paths` goes **stale** after archiving and is **not** retroactively updated. This is knowingly accepted; it is mitigated (not fixed) by `checkpoint_info.json` traveling with the checkpoint, and by a missing-path warning in `optica export`:
> ```
> ⚠ Checkpoint path no longer exists: checkpoints/checkpoint_val0.852_epoch7/
>   It may have been archived or deleted. Check checkpoints/archive/
> ```
> *(V1 ships no same-second log-filename collision handling. This is coherent: a log is written at run start and a run takes minutes, so a collision requires concurrent invocation — which the global lock file, V1-core, prevents outright. See Known Constraints.)*

---

### Export

**V1 exports one format: PyTorch `.pt`.** `optica export` produces a `model.pt` and takes **no format flag** — `--format`, the `export_format` config key, ONNX export, and REST export are fast-follow additions that arrive together. `pt` is the smallest, most portable artifact and never fails on a missing optional dependency, which is why it is the sole V1 export path. *(Every export decision below applies equally to `optica run`'s export stage, per the standing propagation rule.)*

#### Output structure

`./optica-output/` is always a **container** folder; each export gets its own named subfolder:

```
./optica-output/
├── efficientnet-small_3cls_20260312_164510/
│   ├── model.pt
│   ├── class_names.json
│   ├── model_info.json
│   └── usage_examples.md
└── logs/
    └── run_20260312_143022_efficientnet-small_3classes.json
```

The model file stays the generic `model.pt` — the **subfolder carries the identity**, giving usage examples a stable target. Subfolder naming: `<model-family>_<N>cls_<YYYYMMDD>_<HHMMSS>/`.

- Model family first (most useful at a glance); `Ncls` = class count; `YYYYMMDD_HHMMSS` = export date and time.
- **Seconds are included** — `<YYYYMMDD>_<HHMMSS>` — so two exports of the same model family and class count within one minute do not collide on the timestamp alone.
- **The year is included**, matching the checkpoint archive and log timestamps. *(These were deliberately different in an earlier version, on the reasoning that exports are short-lived; that premise was wrong — the export folder is the artifact users keep. Aligned on purpose; do not re-separate. The auto-increment guard still covers same-second collisions.)*
- **`_x` auto-increment** on collision (same model + date + time). In V1 this is the only conflict handling — a same-second re-export of an identical model silently becomes `…_2`. *(The O/S/R/A conflict prompt is a later addition; V1 uses the silent auto-increment fallback.)*

**Checkpoint identity suffix `_ckptX`** — when a non-default checkpoint rank is exported, the subfolder carries a `_ckptX` suffix (export context only, silent, automatic):

| Selection | Folder |
|---|---|
| No `--checkpoint-rank`, or `--checkpoint-rank 1` | No suffix |
| `--checkpoint-rank 2` | `…_ckpt2` |
| `--checkpoint-rank 1,2` | `…_ckpt1` and `…_ckpt2` |

**No export archiving in V1.** Exports are end products with no archiving concept — the conflict/auto-increment logic only ever sees active subfolders in `./optica-output/`. *(Do not generalize checkpoint archiving to exports; they are different.)*

#### Artifact contents

The three files beside `model.pt` are written at export from `checkpoint_info.json` and the resolved backbone config; none requires the user to supply anything.

**`model.pt` holds a `state_dict` plus its reconstruction metadata, in one dict — never a pickled `nn.Module`.** Keys: `state_dict`, `base_model`, `num_classes`, `classes`, `input_size`, `mean`, `std`, `interpolation`, `crop_pct`, `crop_mode` — **all six timm-resolved preprocessing values, not three**, so the metadata records the backbone's full resolved preprocessing rather than leaving half of it to be recomputed. **The dict contains tensors and JSON primitives only**, which is what makes it loadable under `torch.load`'s `weights_only=True` default (torch ≥ 2.6); an artifact requiring `weights_only=False` would ask its consumer to disable a security check in order to open it, and is the specific way a `.pt` fails to be portable. Reconstruction is two lines — `timm.create_model(base_model, num_classes=…)`, then `load_state_dict`. **That two-line form is only valid because `configure_head()` is constrained to stay timm-native** — the constraint, and its reason, are stated in Training → *Training Engine* alongside the `models.py` disciplines. *Rejected: a full pickled module, which needs the defining class importable at load time and does not load under the current default at all; and TorchScript, which is more portable still but introduces an export-time scripting failure for a V1 that has no such failure class, and yields an artifact that cannot be fine-tuned.*

**`class_names.json` is a bare JSON array, and its order is the model's output-index order** — position `i` is the label for output index `i`. **That order is the class subfolder names sorted, exactly as `ImageFolder` produces them**, so it is not a free choice at export: it is already fixed by the loader Training uses. The array **originates in `checkpoint_info.json`'s `classes`**, written at training time in that same sorted order and read from there at export, so the order is fixed once at the dataset load and propagates unchanged; `model_info.json`'s `classes` carries the same list in the same order — `class_names.json` is the programmatic surface, `model_info.json` the human-readable metadata. *(This governs stored output only. `--classes cat,dog,bird` is user input and keeps the order typed; the dataset's class order is the sorted folder names regardless.)*

**`usage_examples.md` is generated at export from `model_info.json`** and shows four things in order: loading `model.pt` and reconstructing the model, preprocessing an image with all six recorded preprocessing values, running inference, and mapping the output index through `class_names.json`. Generating it from the metadata beside it is what stops the example drifting from the artifact it demonstrates.

#### `--output` path handling

`--output`/`-o` (default `./optica-output`) accepts a container path and governs **all** run outputs — the export folders below and the project-local training log — not exports alone, with full path-error handling that fires on the default too:

| Situation | Behavior |
|---|---|
| Single component, exists | Use as container |
| Single component, doesn't exist | Prompt "Create it? [Y/n]" — `--yes` auto-confirms |
| Single component, is a file | Hard error |
| Single component, no write permission | Hard error (pre-export validation) |
| Multi-component, full path exists | Use as container |
| Multi-component, doesn't exist | Three-option prompt — **`N`** use the last component as the export *name* inside its parent, **`C`** create the full path as a *container*, **`A`** abort. Y/N phrasing is deliberately not used: the two behaviours are alternatives, not an affirmative and its negation. `--yes` → hard error with instructions to disambiguate |
| Trailing slash present | Always a container, never an export name. **Single component:** the slash adds nothing — a single component is a container by fiat, so the four Single-component rows govern unchanged. **Multi-component:** the three-option prompt above does not apply, since the slash removes the name-versus-container question it exists to settle; a path that does not exist prompts "Create it? [Y/n]" and `--yes` auto-confirms |

`pathlib.Path` is used throughout (OS-agnostic). *(The `--output` + `--name` combination rows are omitted — `--name` is a fast-follow addition.)*

#### `model_info.json`

```json
{
  "run_id": "20260312_143022",
  "model_family": "efficientnet-small",
  "base_model": "efficientnet_b0",
  "classes": ["bird", "cat", "dog"],
  "num_classes": 3,
  "input_size": [224, 224],
  "mean": [0.485, 0.456, 0.406],
  "std": [0.229, 0.224, 0.225],
  "interpolation": "bicubic",
  "crop_pct": 0.875,
  "crop_mode": "center",
  "val_accuracy": 0.852,
  "val_loss": 0.342,
  "test_accuracy": 0.834,
  "test_loss": 0.391,
  "epochs_trained": 8,
  "class_weights_applied": false,
  "early_stopped": true,
  "exported_rank": 1,
  "exported_rank_of": 6,
  "export_format": "pt",
  "export_folder": "efficientnet-small_3cls_20260312_164510",
  "training_timestamp": "2026-03-12T14:30:22",
  "export_timestamp": "2026-03-12T16:45:10",
  "dataset_path": "/home/user/projects/pets/dataset",
  "config": { "epochs": 10, "batch_size": 32, "learning_rate": 0.001,
              "augmentation": true, "early_stopping": 5, "finetune_ratio": 0.70 },
  "checkpoint_path": "checkpoints/checkpoint_val0.852_epoch7/",
  "log_file": "~/.optica/logs/run_20260312_143022_efficientnet-small_3classes.json"
}
```

- `export_format` is always `"pt"` in V1.
- **`input_size`, `mean`, `std`, `interpolation`, `crop_pct`, `crop_mode`** are the resolved backbone preprocessing config (see Training → *Input resolution and normalization*), not constants — the values above are `efficientnet_b0`'s. **All six are exported, not three:** evaluation and inference resize to `input_size / crop_pct` at the backbone's interpolation and centre-crop to `input_size` — training augments with random crop by default, so the centre-crop configuration describes the transform the exported model is used under, which is what the example has to teach. An example generated from `input_size`, `mean` and `std` alone teaches a different preprocessing — same model, different framing and resampling, quietly worse predictions with no error. All six are copied into `model.pt`'s metadata dict as well, so the artifact is self-describing without the folder, and all six are what `usage_examples.md` is generated from. They are exported rather than recomputed because `resolve_model_data_config` reads the `pretrained_cfg` carried by the installed timm, so a later timm can answer differently for the same tag; the exported values record what this model was trained under.
- **`class_weights_applied`** records whether the imbalance warning fired and the user chose to weight, mirroring `checkpoint_info.json`. It does not affect inference — weighting shapes training, not the forward pass — but without it a consumer holding only the export folder cannot tell the model was trained on a set where one class held under half the largest. The `class_weights` array itself stays out: it is training detail a consumer cannot act on.
- **`checkpoint_path`** is the checkpoint **folder**, as a path relative to the project root — `checkpoints/checkpoint_val0.852_epoch7/`, or `checkpoints/archive/<timestamp>/checkpoint_val0.852_epoch7/` for a checkpoint exported after archiving. A checkpoint is a folder everywhere in Optica: ranked by folder, archived by folder, designed so `checkpoint_info.json` travels inside it. The form is relative rather than absolute for the opposite reason `dataset_path` is absolute — the dataset can sit anywhere `--dataset` points and must be found again, while checkpoints always sit under the project root at a path that root determines, so a relative path survives the project being moved or copied. The same form is used by `checkpoint_paths` in the training log and by the stale-path warning in `optica export`.
- **`dataset_path`** (absolute) is copied here from `checkpoint_info.json` at export — required by post-V1 incremental learning, which needs the full class list (already present) and the original dataset path.
- There is **no** `exported_files` field in V1: it would be neutral metadata for direct-output-mode conflict detection (`--no-subfolder`, a fast-follow flag), and with one format its contents would be derivable anyway. `exported_rank`/`exported_rank_of`/`export_folder` are unaffected.

---

### Python API

#### Five tiers (documentation and onboarding structure)

| Tier | Name | Interface | Level | Entry point |
|---|---|---|---|---|
| 1 | Quick Start | CLI | Beginner | `optica run` |
| 2 | CLI | CLI | Intermediate | `optica fetch`, `optica train`, `optica export`, … |
| 3 | Simple API | API | Beginner | `optica.run()` |
| 4 | Python API | API | Intermediate | `optica.fetch()`, `optica.train()`, `optica.export()`, … |
| 5 | Classifier | API | Expert | `Classifier` class |

Two axes — interface (CLI/API) × complexity (beginner/intermediate) — plus one expert outlier (`Classifier`, which earns Expert status by giving direct programmatic control over the model object — the model, not the training loop: the optimizer and its per-optimizer hyperparameters stay fixed, see Configuration → *Config keys*). **The CLI has no Expert tier by design** — there is no CLI equivalent of holding a model object in memory and calling methods on it; Tier 2 is the CLI ceiling.

**"Zero-friction" means minimal conceptual prerequisites, not minimal flags.** A user passing `--mode clip --epochs 20` to `optica run` is still a Tier 1 user — the tier measures pipeline knowledge, not customization depth. `optica.run()` (Tier 3) shares that quality but signals a different audience (developers integrating in Python — errors not prompts, structured returns). **Simple API (Tier 3) and Quick Start (Tier 1) are distinct documentation sections**, not one merged "beginner" section — the contract differs (errors vs prompts, structured results, composability), and merging them would obscure that.

#### Canonical surface — task-namespaced from V1

The **canonical** API surface is task-namespaced — `optica.classify.run()`, `optica.classify.train()`, `optica.classify.export()`, etc. The flat forms (`optica.run()`, `optica.train()`, …) are **convenience aliases** that route via `default_task`. V1 users on the flat aliases need change nothing post-V1. The namespace ships in V1 even though only classification exists — a small structural cost for a clean, non-breaking foundation (mirroring the CLI alias pattern). *(The `task=` parameter alternative was explicitly rejected — task-specific steps like a future `annotate` make a unified surface hollow.)*

#### Simple API (Tier 3) and Python API (Tier 4)

```python
import optica
optica.run(classes=["cat", "dog"])                          # full pipeline
optica.fetch(classes=["cat", "dog"], source="open-datasets")
optica.curate()                                             # opens browser curation
optica.label(folder="./images", classes=["cat", "dog"])
optica.train(classes=["cat", "dog"])                        # classes optional if dataset/ exists
optica.export()                                             # V1: PyTorch .pt
```

Thin wrappers around pipeline components; config defaults apply as in the CLI. `classes` in `optica.train()` is optional when `dataset/` already exists (folder names are the source of truth) and required otherwise. All functions accept `verbose=True` (default) — set `verbose=False` to suppress Rich output for library use. `optica.setup()` is **not** exposed — setup belongs to the CLI only. **Prompts live in the CLI layer only; the API raises `Optica*Error` instead of prompting**; raw library exceptions (torch, PIL) are always caught and re-raised as `Optica*Error` with clear messages.

**The stage boundary governs the API identically.** *A function accepts only input its own stage can act on* — `optica.train()` rejects a flat folder or a partially-labeled manifest as a precondition error, exactly as `optica train` does, because labeling is another stage's work; `optica.label()` labels its resolved input and stops; `optica.run()` is the only function that sequences one stage into the next. The parameter-mapping rule carries the names across surfaces but not the constraint, so it is stated here rather than left to be inferred from the CLI's phrasing of it.

**The API behaves as though `--yes` were always passed.** The `--yes` table is the prompt mapping: it already records, for every prompt `--yes` answers, the answer to take when nobody is there to answer. *There is therefore no `auto_confirm=` parameter — it would be a no-op, and offering it would imply the API sometimes prompts, which the rule above forbids.*

Prompt sites resolve three ways:

- **Defaultable — taken silently.** **Every prompt listed in the `--yes` table takes its listed answer**, with no exceptions and no restatement here — that table is the source, and duplicating it into a second list is how the two come to disagree. Its `optica config --init` row is simply unreachable, config being CLI-only.
- **Destructive — raises.** The `dataset/` overwrite prompt is one of the prompts in the API's scope that `--yes` does not answer, so the API raises `OpticaValidationError` unless the caller passes **`overwrite=True`**. A general `force=` was rejected: it would be a grant whose meaning silently widens as new safety is added, and a caller who allowed a dataset overwrite in V1 would find it waiving later protections they never agreed to. Requiring the caller to clear the path instead was also rejected — it pushes destruction into user code as a bare recursive delete, where an empty path variable removes the wrong tree; `overwrite=True` removes exactly the destination Optica resolved.
- **Not defaultable — raises.** The blocklist user-definition prompt has no safe answer: the API cannot ask a caller to define what a term means mid-call. `OpticaValidationError`, naming the blocklisted class and that a concrete definition is required.

Setup's prompts and `config --init`'s are out of scope — `optica.setup()` is not exposed and config is CLI-only.

**Warnings become structured results *and* Python warnings, from one source.** Every warning the CLI would print is recorded on the returned result, and `warnings.warn` is emitted **from those entries** under an `OpticaWarning` category (subclassing `UserWarning`). One source, two surfaces, so they cannot diverge. Structured entries alone would be passive — a caller who never inspects the result would silently lose the quality signals that `verbose=False` suppresses, which is the failure this exists to prevent; `warnings.warn` alone would be unactionable, since a caller cannot branch on an English sentence. The `OpticaWarning` category lets callers filter Optica's warnings without suppressing every warning in their process.

**`dry_run=` is available on `fetch`, `train`, `export`, and `run`**, matching the CLI flag's scope, and returns the resolved plan as a structured result without writing anything. It resolves mode defaults, detection order, the acquisition short-circuit, and the destination — exactly the reasoning a caller cannot reproduce without duplicating logic that would then go stale.

#### Result types

Every Tier 3 and Tier 4 function returns a result object. This is what *"structured returns"* means in Tier 3's contract — it is what separates Tier 3 from Tier 1, not a convenience.

```python
@dataclass
class OpticaResult:                  # base — never returned directly
    warnings: list[WarningEntry]     # every warning the CLI would have printed
    dry_run: bool                    # True when nothing was written
    plan: dict | None                # resolved decisions; populated only when dry_run

@dataclass
class WarningEntry:
    code: str                        # stable identifier — "class_imbalance", "low_resolution", …
    message: str                     # the sentence the CLI prints; warnings.warn renders this
    context: dict                    # the values that produced it — class names, counts, paths
```

`code` is what makes an entry branchable and `context` is what makes it actionable; `message` is the single source `warnings.warn` emits from, so the two surfaces cannot diverge. **Codes are stable API surface** — renaming one is a breaking change.

Per-command subclasses mirror the per-command config objects:

| Type | Returned by | Fields beyond the base |
|---|---|---|
| `FetchResult` | `fetch`, `label`, `curate` | `classes`, `counts` (delivered per class, post-filter), `source`, `mode`, `dataset_path` |
| `TrainResult` | `train` | `best_checkpoint`, `best_val_accuracy`, `test_accuracy`, `test_loss`, `epochs_run`, `epochs_requested`, `phases`, `checkpoints`, `log_paths` |
| `ExportResult` | `export` | `export_folder`, `files`, `checkpoint_rank` |
| `RunResult` | `run` | `fetch`, `train`, `export` — the stage results, `None` for stages that did not run |

Everything the terminal completion block reports comes from `TrainResult`, one computation feeding both surfaces: `epochs_run` against `epochs_requested` is how early stopping stays visible, and `phases` is the allocation the rounding rule produced. `TrainResult` additionally carries `best_checkpoint` and `log_paths`, which the block does not print.

**Under `dry_run=True`** the same type is returned with every outcome field `None`, `dry_run=True`, and `plan` carrying the four resolutions a caller cannot reproduce without duplicating logic that would go stale: `mode`, `detection_order`, `short_circuit`, and `destination`.

**`optica.label()` and `optica.curate()` block on a browser, not on stdin.** They are the only API calls that wait on a human, and that is permitted — the rule forbids prompting on stdin, not opening the UI the call exists to open. Browser-side confirmations are unaffected by any parameter, exactly as `--yes` does not answer them.

#### Classifier (Tier 5)

```python
from optica import Classifier
from optica.api import FetchConfig, TrainConfig, ExportConfig

clf = Classifier(model="efficientnet-large", output="./my-output", verbose=True)
clf.fetch(classes=["cat", "dog"], config=FetchConfig(source="flickr", images_per_class=200))
clf.train(config=TrainConfig(epochs=20, augmentation=False, early_stopping=10,
                             learning_rate=0.001, batch_size=32, optimizer="adamw",
                             max_checkpoints=3, train_split=0.70, val_split=0.15, test_split=0.15))
clf.export(config=ExportConfig(checkpoint_rank=1))          # V1: PyTorch .pt

print(clf.classes, clf.model, clf.status, clf.dataset_path)
print(clf.training_history, clf.best_val_accuracy, clf.checkpoint_path, clf.export_paths)

clf.fetch(...).train(...).export(...)                       # chainable — methods return self
clf = Classifier(checkpoint_path="./checkpoints/checkpoint_val0.852_epoch7/")  # skip steps with existing data
clf.export()
```

`Classifier` is named after the task (scikit-learn convention — `Detector`, `Segmentor`, `Embedder` follow post-V1). All methods return `self` for chaining; outcomes are accessed via properties. State validation is **flexible with helpful errors over strict ordering** — advanced users legitimately skip steps, so preconditions raise `Optica*Error` with fix instructions rather than enforcing a rigid sequence. Raw exceptions are always re-raised as `Optica*Error`, with the original preserved as cause in verbose mode. `Classifier(checkpoint_path=...)` is why the CLI defers an arbitrary-checkpoint-path flag (the CLI stays rank-based in V1).

**Property shapes.** `classes: list[str]` in the sorted class order the dataset defines (see Export → *Artifact contents*) · `model: str`, the `--model` value · `status: Status` · `dataset_path: Path | None` · `training_history: list[EpochRecord]`, one entry per completed epoch, carrying the same payload the training log records · `best_val_accuracy: float | None` · `checkpoint_path: Path | None`, the best checkpoint's **folder**, in the same form `model_info.json` uses · `export_paths: list[Path]`, one entry per export folder written. A ninth property carries the warning contract into Tier 5: **`warnings: list[WarningEntry]`**, accumulated across calls in invocation order — `Classifier` methods return `self` rather than a result object, so without it the tier built for programmatic callers would be the only one unable to branch on a warning. Same entries, same source as the Tier 3/4 results and `warnings.warn`.

**`status` is a high-water mark, not a position in a sequence** — `empty` → `data_ready` → `trained` → `exported`, each meaning *this stage has been completed at least once*. It never moves backwards within a `Classifier`'s life, and it is what preconditions are checked against, which is what makes *"flexible with helpful errors over strict ordering"* implementable: a caller who skips a stage gets an error naming the missing state, not a rejection for being out of order.

**Config-object parameters track CLI long flag names mechanically** — drop the leading `--`, hyphens become underscores: `--clip-threshold` → `clip_threshold`, `--images-per-class` → `images_per_class`. **Negative flags map to the positive parameter, inverted** — `--no-augmentation` → `augmentation=False` — and config-only keys with no CLI flag keep their config-key names. The remaining exceptions are flags that are inherently CLI-only: `--yes`, `--ci` and `--force` have no equivalent — the API never prompts, so there is nothing for them to answer or suppress — and `--quiet` folds into `verbose=False`. **`--overwrite` is not among them**: it maps mechanically, like any other flag, to the per-operation `overwrite=True` described below. **The verbosity mapping loses information, stated here rather than resolved**: the CLI's three levels collapse into the API's two — `verbose=True` is the default level and `verbose=False` is `--quiet`, so what a caller cannot express is `--verbose`'s extra detail. A `verbosity=` parameter was considered and rejected as API surface V1 does not need. Accordingly `ExportConfig`'s checkpoint parameter is **`checkpoint_rank`, with no `checkpoint` alias** — the CLI keeps that alias to protect surface users already depend on, whereas `ExportConfig` ships in V1 with no legacy to preserve, and shipping an alias on day one would manufacture the very ambiguity the CLI carries only out of obligation. *(`FetchConfig(strict=...)` and multi-format `ExportConfig(formats=[...])` are omitted from V1 — `--strict` and multi-format export are fast-follow. Post-V1, `optica.detect.*` is the canonical namespace, with flat forms as aliases.)*

**Where a parameter goes is a separate rule from what it is called.** **Method arguments identify *what* a call operates on; config fields tune *how*; constructor arguments are what persists across every call on the object.** So inputs, destinations and per-call safety — `classes`, `folder`, `manifest`, `dataset`, `mode`, `overwrite` — are **method arguments even when config-backed**; `model` and `output` are **constructor** arguments, being settings every operation on a `Classifier` shares; and everything else carrying a Config keys (V1) entry is a **config field**. Without this the naming rule governs spelling while placement is invented per function.

**`overwrite=` is a method argument, defaulting to `False`, on exactly the callables that can write `dataset/`** — `optica.run()`, `optica.label()`, `optica.curate()`, `optica.train()` where a manifest materializes into a dataset, and `optica.fetch()` where `mode="clip"` writes `dataset/` — clip mode has no browser stage between the fetch and the write, so the write is fetch's own — plus the `Classifier` methods of the same names. It is deliberately **not** on a config object or the constructor: the mapping rule sends `--overwrite` to a **per-operation** `overwrite=True`, and either of those homes would make it not per-operation.

**Import-time contract.** `import optica` succeeds with no extras installed — it is the precondition of `pip install optica` followed by `optica --version` working, and of the Tier 5 example's `from optica import Classifier` and `from optica.api import ...` lines resolving at all. The import binds the **full public surface eagerly**: the flat aliases, the `optica.classify` namespace, `Classifier`, and the `optica.api` config objects are real attributes the moment it returns. The lazy boundary is at the **dependency** level, never the symbol level, so type checkers and IDE completion see the whole surface with no stub file. Torch-typed signatures stay visible to static analysis without a runtime import, via `from __future__ import annotations` and a `TYPE_CHECKING` guard. *Rejected: resolving names through a module-level `__getattr__`, which trades a few milliseconds of import time for a surface no tooling can see; and emitting a warning at import when setup has not run, since a library that prints on import cannot honour `verbose=False` — the user has not called anything yet.*

**Error timing.** Missing-extra errors surface at call time, never at import — `optica.train()` without the ML stack raises `OpticaTorchError`. `Classifier(checkpoint_path=…)` validates that the path is a checkpoint **folder** containing `checkpoint_info.json` — raising `OpticaConfigError` if it does not exist, and `OpticaValidationError` if it exists but is not a checkpoint, a bare `.pt` file being the latter. The distinction matters because `clf.export()` reads `run_id`, `val_accuracy`, `epoch`, `dataset_path` and the `config` block from `checkpoint_info.json`; a file that does not carry it cannot be exported from, so accepting one would defer the failure to the operation the object was constructed to perform. Validation does not load the checkpoint: an existence check needs no torch, and `torch.load` happens in the first method that needs the model. Constructing a `Classifier` therefore never requires torch.

## Part III — Implementation

### Code Structure

```
optica/                          ← repo root
├── src/
│   └── optica/                  ← installable package
│       ├── __init__.py          ← Simple API surface (Tier 3) + flat aliases
│       ├── exceptions.py        ← all exception classes (public + internal)
│       ├── cli/
│       │   ├── main.py          ← Typer app entry point; registers classify group + flat aliases only
│       │   ├── classify.py      ← classify subcommands (self-contained)
│       │   ├── config.py        ← config subcommands (delegates staging ops to Input Manager)
│       │   └── setup.py         ← optica setup command
│       ├── config/
│       │   ├── manager.py       ← Config Manager (priority resolution)
│       │   ├── schema.py        ← pydantic-settings models
│       │   └── defaults.py      ← built-in default values
│       ├── input/
│       │   ├── local.py         ← Local Adapter
│       │   ├── fetch.py         ← Fetch Adapter (Flickr, Open Datasets) — registry dispatch
│       │   ├── curation.py      ← Curation Adapter (curate mode)
│       │   ├── clip.py          ← CLIP Adapter (clip mode)
│       │   ├── validation.py    ← image validation pipeline
│       │   ├── manager.py       ← Input Manager (label-mode detection order)
│       │   └── sessions.py      ← staging session stores (labeling/<session_id>.json + curation.json)
│       ├── training/
│       │   ├── engine.py        ← Training Engine (injected components)
│       │   ├── models.py        ← load_backbone() + configure_head(); replace_head(num_classes=…)
│       │   │                    (configure_head() is constrained timm-native for classification —
│       │   │                     see Training → Training Engine; the exported model.pt depends on it)
│       │   ├── transforms.py    ← torchvision transforms + augmentation
│       │   ├── splits.py        ← train/val/test splitting
│       │   └── checkpoints.py   ← checkpoint save/load/archive
│       ├── export/
│       │   ├── manager.py       ← Export Manager (calls pytorch.export() directly in V1)
│       │   └── pytorch.py       ← .pt export      (onnx.py, rest.py join with the ONNX/REST fast-follow)
│       ├── server/
│       │   ├── app.py           ← FastAPI app (curation + labeling)
│       │   ├── routes.py        ← API routes
│       │   └── static/          ← curation.html, labeling.html, shared.css, shared.js, curation.js, labeling.js
│       │                        (vanilla HTML/JS, no build step — see Tech Stack. Timeout warnings,
│       │                         Keep Session Active, light/dark and pagination are shared by both pages;
│       │                         per-page files hold only what differs. Not inlined: two copies of the
│       │                         shared behaviour is a drift surface.)
│       ├── api/
│       │   ├── simple.py        ← Simple API (Tier 3) / Python API (Tier 4)
│       │   └── classifier.py    ← Classifier class (Tier 5)
│       └── utils/
│           ├── logging.py       ← Rich logging + verbosity
│           ├── system.py        ← GPU / venv / OS detection
│           ├── progress.py      ← Rich progress bars
│           └── lockfile.py      ← global lock file (~/.optica/optica.lock)
├── tests/  (unit/, integration/, conftest.py with synthetic pretrained=False fixtures)
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md              ← dev setup incl. optica setup --ci and venv note
├── LICENSE
└── .github/workflows/ci.yml
```

The implementation disciplines attach to specific files here: `engine.py` takes injected components; `input/fetch.py` uses registry dispatch — `export/manager.py` calls `pytorch.export()` directly in V1, and the registry arrives with the second format rather than being built for one; `models.py` splits `load_backbone()`/`configure_head()`; `cli/classify.py` is self-contained. `input/clip.py` is present because clip mode is V1-core.

*Two structural notes for implementation (not blockers, but the tree doesn't yet accommodate them):* the canonical `optica.classify.*` namespace has no dedicated module (only the flat `api/simple.py`), and the `TASK_REGISTRY`/`EXTRAS_REGISTRY` have no stated home. Both should be placed when the API namespace and setup registry are built.

**Naming conventions:** `snake_case` for variables, functions, modules; `PascalCase` for classes and exceptions (`Classifier`, `OpticaConfigError`); descriptive names for public API, terse for locals; private helpers prefixed with `_`.

**`pyproject.toml`:** Hatchling backend (auto-detects `src/`), entry point `[project.scripts] optica = "optica.cli.main:app"`. `requires-python = ">=3.11"` with 3.11–3.13 the target (not 3.14). `>=min, <next_major` bounds for every dependency it declares (concrete values from the pre-implementation gate); **torch is never declared directly in `pyproject.toml`** in V1, though the `clip` extra reaches it transitively. The `[test]` extras group (`pytest`, Ruff, mypy) is the non-user-facing CI extra.

**CI/CD:** `pip install optica[test]` → `optica setup --ci` (config init only — no package install, no environment detection, no prompts; see `optica setup` → *`--ci`*) → `pytest`, with `pretrained=False` synthetic fixtures keeping tests offline. `--ci` survives the setup redesign unchanged. **CI runs as a version matrix** across the minimum and maximum declared versions of what each leg installs — Core plus `optica[test]` — since testing only the latest version cannot catch use of an API absent from the declared minimum. The extras groups are outside it (see Tech Stack). **The torch stack never reaches CI:** `optica[test]` carries pytest, Ruff and mypy only, and `--ci` installs nothing, so any test needing torch is marked `@pytest.mark.slow` and **runs locally rather than in CI** — `@pytest.mark.slow` is a standard pytest marker, not something introduced here; this line states which tests carry it. *(A scheduled job that installs CPU torch and runs the pipeline tests is the fast-follow: it would give real coverage without putting a multi-minute install on every PR.)*

---

### Exceptions

All exception classes live in `src/optica/exceptions.py`, one file, with the universal `Optica*` prefix (no separate unprefixed internal classes). `OpticaWarning` lives there too, despite subclassing `UserWarning` rather than `OpticaError`: a separate module holding one warning class is the kind of split this consolidation exists to avoid, and keeping the whole `Optica*` diagnostic vocabulary in one file is what makes it checkable. **V1 uses a flat hierarchy with exactly one documented nested branch** — the principle *and* its single exception must both appear, because a "flat" statement alone would contradict the diagram and a diagram alone would lose the rule.

```
OpticaError
├── OpticaMissingExtraError        # any required extra not installed
│   ├── OpticaTorchError           # torch stack missing → optica setup
│   ├── OpticaWebError             # optica[web] missing
│   └── OpticaCLIPError            # optica[clip] missing
├── OpticaCLIPLoadError            # CLIP model load failure (corrupt/interrupted weights)
├── OpticaConfigError              # invalid config values, missing required keys
├── OpticaTrainingError            # training failure, bad dataset, OOM
├── OpticaExportError              # export failure
├── OpticaFetchError               # API key missing, rate limit, network failure
├── OpticaValidationError          # inputs or destination state the caller must resolve:
│                                  #   image validation all-rejected, below the hard floor,
│                                  #   class-count and manifest-shape violations, mutually
│                                  #   exclusive input flags, dataset/ overwrite refusal,
│                                  #   blocklist prompt in a non-prompting context
├── OpticaSetupError               # optica setup: environment resolution and mismatch,
│                                  #   hardware detection, install failure
├── OpticaBrowserServerError       # browser server (label + curate): port unavailable, browser launch failure
├── OpticaLabelingError            # labeling session file unreadable, corrupt, or an unrecognized version on resume
└── OpticaCurationError            # curation.json unreadable, corrupt, or an unrecognized version

OpticaWarning (UserWarning)        # API warning category — deliberately not an OpticaError
```

Assembled from four decisions:
- **`OpticaMissingExtraError` has three children in V1, not four** — `OpticaONNXError` travels with ONNX to the fast-follow (nothing can request a format that doesn't exist). The one nested branch lets a caller catch any missing-extra condition at one point.
- **`OpticaCLIPError` means only "the `optica[clip]` extra is missing"**, consistent with its siblings. Its former second role — CLIP **model-load failure** — is split off into the **new `OpticaCLIPLoadError`**, parented to `OpticaError` (not `OpticaFetchError`, because CLIP weights load during training and inference too, so filing it under fetch would misclassify most occurrences). The two need different messages — *install `optica[clip]`* vs a corrupt-weights report — and one message cannot serve both. **On corrupt weights Optica deletes and re-downloads them itself**, the same treatment the Open Images label map gets, reporting the cache path it acted on; the path is resolved from open-clip at runtime rather than hardcoded, since the cache is open-clip's and not Optica's to fix in place. *Rejected: instructing the user to delete a file whose location the plan never gives — which is what a label map is spared and multi-hundred-megabyte weights were not.*
- **The browser-server class is `OpticaBrowserServerError`**, chosen over bare `OpticaServerError`. The names never literally collided; the *meanings* did — "web" and "server" point at the same subsystem, so the qualifier is what separates them. It names the subsystem rather than a caller: `optica label` and `optica curate` share one server, and a caller-named class would misreport half its failures. Pattern with `OpticaCLIPLoadError`: **descriptive names for operational failures, extra-named classes for missing dependencies.** (Renaming `OpticaWebError` instead was rejected — it is the regular member of the missing-extra siblings, so changing it would add the irregularity rather than remove it.)
- **`OpticaSetupError` exists because setup is a subsystem, not a caller.** Same reasoning that produced `OpticaBrowserServerError` — one class for one subsystem, named descriptively because its failures are operational rather than dependency-related. Without it, setup's hard errors (no venv found in non-interactive mode, more than one found, an active environment Optica is not running from, hardware detection failure, install failure) fit nothing in the hierarchy, and setup is the plan's largest interactive subsystem and its documented CI entry point.

**Lazy imports (the mechanism the whole optional-extras architecture rests on).** All non-Core dependencies are imported lazily at point of use. Any `ImportError` from a missing extra is caught and re-raised as the appropriate `OpticaMissingExtraError` subclass with a clear install instruction; a raw `ImportError` traceback never reaches the user. Applies equally to the CLI and the API. `pip install optica` followed by `optica --version` must work with no torch present. Per-dependency messages:

| Exception | Message |
|---|---|
| `OpticaTorchError` | `This operation requires the Optica ML stack. Run: optica setup` |
| `OpticaWebError` | `This operation requires the web extras. Run: optica setup or pip install optica[web]` |
| `OpticaCLIPError` | `CLIP filtering requires the clip extra. Run: optica setup --include-extras clip or pip install optica[clip]` |

*(The CLIP message names `--include-extras clip`; there is no `optica setup --clip` flag. The ONNX message leaves V1 with ONNX export.)*

**Messages name the capability, never the command or flag that requested it.** The same `OpticaWebError` is raised by `optica label` and by `optica.label()`; the same `OpticaCLIPError` is raised by `--mode clip`, by `mode="clip"`, and by the blocklist's grouped path under `--mode curate`. A message written in either surface's vocabulary is wrong on the other — and, as the CLIP case shows, can be wrong on its own surface too, by naming a trigger the user did not use.

**The composite entry points check required extras up front.** `optica run` and `optica.run()` resolve their required extras from the invocation's arguments — `--mode clip` requires clip, the label and curate paths require web, the train and export steps require torch — and raise before fetching begins. **`--mode curate` additionally requires clip when any `-c` name is on the blocklist**, because the blocklist's grouped path runs CLIP filtering; blocklist membership is a test on the class names, which are invocation arguments, so this is knowable at entry even though the grouping answer that consumes it comes later, and the check fires at entry accordingly. *(Accepted cost: a curate user with a blocklisted name installs the clip extra even if they would have answered "separate". In exchange the grouping prompt never has to withdraw an option, and no run fails after the user's attention has been spent.)* This is the standing *check before any action* principle applied to dependencies rather than to file conflicts: whether the pipeline can complete is fully determined at invocation, so a failure knowable at entry must fire at entry. It matters most on `run` because `run` is the only command that interleaves attended and unattended stages: the user's attention is required at the curation or labeling step, and again at the train step only if a safety prompt fires there (Implementation Note 19), while a missing-extra failure would land at the train step regardless — after the curation attention has been spent and released. The abort is therefore not observed but discovered on return. Under `--mode clip` there is no attended stage at all and the whole pipeline is unattended from the start, but the argument does not depend on clip; without it the user has additionally done real curation work before walking away. Single-step commands are deliberately **not** guarded (*do not harmonize*): each reaches its first dependency within seconds of invocation, so a guard would duplicate the lazy-import error without changing when the user sees it. **`optica fetch --mode curate` with a blocklisted `-c` name is the one exception, and it takes the entry check.** There the dependency is not reached in seconds: the blocklist flow runs the user-definition prompt, group-or-separate, the per-sub-term counts, the overlap check and the confirmation, the fetch then completes in full, and only then does the grouped path score images and raise. A lazy-import error would land after the run's work is done and its API quota spent — the outcome the entry check exists to prevent — and blocklist membership is knowable at entry on `fetch` for exactly the reason it is on `run`.

**Every hard error carries a class.** The rule: **a hard error's class is the subsystem whose contract it violates**, not the command it was raised from — `optica run` can raise any of them. `OpticaValidationError` is the input contract specifically, which is what makes it broad without being a catch-all: it is bounded by the other classes, not by a list.

| Error family | Class |
|---|---|
| Manifest shape — contradictory rows, URL row, missing `class` column, fully-labeled manifest to `optica label`, mixed manifest | `OpticaValidationError` |
| Fewer than 2 classes; below the 5-image floor, including the post-deduplication re-check | `OpticaValidationError` |
| Mutually exclusive input flags — `--folder` with `--manifest`, `--dataset` given a flat folder | `OpticaValidationError` |
| `dataset/` overwrite refusal and the blocklist user-definition prompt, both in a non-prompting context | `OpticaValidationError` |
| Split-sum mismatch, numeric range violation, `clip_threshold` out of range, unknown config key | `OpticaConfigError` |
| Environment resolution and mismatch, hardware detection, install failure | `OpticaSetupError` |
| Missing API key, rate limit, network failure | `OpticaFetchError` |
| Port unavailable, browser launch failure | `OpticaBrowserServerError` |
| Labeling session file unreadable, corrupt, or an unrecognized version on resume | `OpticaLabelingError` |
| `curation.json` unreadable, corrupt, or an unrecognized version | `OpticaCurationError` |

The table lists families, not every error: **anything not in it is classified by the rule above** — the subsystem whose contract it violates. **`OpticaCLIPLoadError` is the one class that rule does not reach:** CLIP weights load during fetch, training and inference alike, so no single subsystem's contract is the one violated, which is why it is parented to `OpticaError` directly rather than filed under fetch. `OpticaError` is raised directly only where no subsystem's contract is the one violated, which is a signal the hierarchy is missing a class rather than a licence to use the base class routinely — `OpticaCLIPLoadError` is that signal already answered.

**Exit codes.** V1 is designed to be scripted — `--yes`, `--ci`, and the terminal completion messages all exist for unattended runs — and the exit code is what a CI job or container build actually branches on.

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Any `OpticaError` |
| `2` | Usage error — a malformed invocation. Click raises every parser error as a `UsageError`, whose own exit code is `2`, so this code is the framework's and the plan matches it rather than contending for it |
| `3` | User abort — a declined prompt, or an `✗ X incomplete` completion |
| `130` | Interrupted (SIGINT), per shell convention |

`3` is distinct from `1` because under `--yes` a prompt should never have appeared: a pipeline that exits `3` has hit a prompt that was declined, which is a different problem from a broken config. **`3` rather than `2`:** `2` is Click's own code for parser errors, which the plan matches rather than contends for, and a declined prompt is not a parser error — collapsing the two would leave a CI script unable to tell a malformed command line from a prompt it could not answer. The global handler catches `click.UsageError` at the base rather than a named list, so `2` stays exactly and only Click's and the separation is structural rather than dependent on an exhaustive catch-list. **Codes are not per exception class** — the class is available to a Python caller through `except`, and the post-V1 subclass families would churn any code-to-class mapping a CI script came to depend on.

Post-V1, per-component subclass families (`OpticaFetchError` → APIKey/RateLimit/Network; `OpticaTrainingError` → OOM; `OpticaExportError` → ONNXValidation) attach backwards-compatibly — existing `except OpticaFetchError` still catches. These are not V1 content; the V1 flat classes are simply designed to admit them later without breakage.

---

### Coding Style

**Async/await:** async only in FastAPI route handlers; all other code is synchronous (only one async component exists, so async throughout would add complexity for no benefit).

**Error handling:**
- All exception classes in `src/optica/exceptions.py` with the `Optica*` prefix; standard Python exceptions for general cases (`ValueError`, `FileNotFoundError`).
- **Never continue silently past an error; batch related validation errors before raising.**
- All errors include actionable fix instructions; raw tracebacks never reach end users.
- In `--verbose`, the original exception is included as cause (`raise OpticaError(...) from original_exc`).

Every error follows a three-line structure — what went wrong / why (one sentence) / how to fix (specific command). Fixed-value-flag errors additionally list valid options (and "Default: X" where applicable):

```
✕ No dataset found at ./dataset
  Optica expects class subfolders inside this directory.
  Run: optica label --folder ./my-images -c cat,dog
  Or create subfolders manually: dataset/cat/, dataset/dog/
```

**Type hints:** full coverage, modern syntax (`str | None`, `list[str]`, `dict[str, int]`), consistent with the Python 3.11–3.13 target.

**Docstrings:** Google style, on all public functions and classes (private `_` helpers excluded), powering the auto-generated API reference. *These are inseparable from the code they document — written during implementation, so they carry no independent classification.*

**Inline comments:** explain why, not what. For example:

```python
# MD5 checked per-class only — avoids removing valid images shared across classes
image_hash = hashlib.md5(image_data).hexdigest()
```

*(This example is accurate for V1 — deduplication is MD5-based, within-class, per the standing decision.)*

**Logging:** Rich for all user-facing output; the standard `logging` module per-module (`logging.getLogger(__name__)`) for internal debug. `--verbose`/`--quiet` control Rich output globally, accepted in either position. **They govern progress and status output only.** Warnings, safety prompts and errors display at every level — nothing about verbosity suppresses them (Implementation Note 19), and `--verbose` adds detail rather than unlocking messages `--quiet` withheld. Rich output reports actual detected values, never internal registry keys.

---

### Implementation Notes

Items requiring verification or special attention during implementation. **Notes 1–6, 9–11, 13, 14, 19 and 20 are work** — verification against external sources, or cross-cutting instructions with no single owning section. **Notes 7, 8, 12, 15, 16, 17 and 18 are cross-references**: each names a decision specified in full in the section that owns it and exists only to make it findable from here. A cross-reference carries no body of its own, so there is nothing for it and its owning section to drift apart on. *(Numbering is preserved — notes are referenced by number elsewhere in this document.)*

1. **Global Typer exception handler — build first.** A global handler catches **`click.UsageError` at the base** (every parser error Typer raises subclasses it), redirecting to prompts where applicable (`MissingParameter` on `--classes`) and producing clean wrapped errors otherwise; `click.Abort` is handled separately and exits `130`. It must be implemented **before any other CLI work ships** — every other flag decision's error behavior executes through it.
2. **Global lock file — hard-block concurrent commands.** `~/.optica/optica.lock` holds PID + command name + run ID. Lock present with a live PID → hard block:
   ```
   ✕ Optica is already running in another terminal.
     Command: optica run (PID 48291)
     Wait for it to complete, or terminate it before running a new command.
   ```
   Lock present with a dead PID → silent cleanup, then proceed. **Exempt:** `optica config --view`, `optica config --set`, `optica --version`. **Blocked (all write commands):** `run`, `train`, `fetch`, `export`, `curate`, `label`, `setup`, `config --init`, `config --clear-staging`. (Per-project scoped locks for full multi-terminal support are post-V1.) This is also why V1 needs no same-second log-filename collision handling — concurrent invocation is what a collision would require, and the lock prevents it.
3. **timm layer names** — verify each model's exact Phase 2 unfreeze layers via `model.named_parameters()` before implementing `training/models.py` (pre-implementation-gate item; layer names change between timm releases).
4. **Flickr API details** — verify current endpoints, rate limits, authentication, and pricing tiers before implementing `input/fetch.py` (pre-implementation-gate item; high external decay).
5. **Open Images GCS bucket structure** — verify current bucket URL, label-mapping format/location, and image URL structure before implementing Open Images access — **specifically whether V7's image CSVs still carry the `OriginalURL` and `Thumbnail300KURL` columns**, which the Input section's fetch path now depends on; they are confirmed in the dataset's own V2/V3-era READMEs and were not verifiable for V7 (pre-implementation-gate item).
6. **CLIP threshold calibration** — `clip_threshold = 0.25` is calibrated for ViT-B-32/openai weights; the calibration is against the model, the weights **and** the `"a photo of a {class}"` prompt template together, not the model alone; if a post-V1 configurable variant of any of the three is added, recalibration guidance must be documented.
7. **`checkpoint_info.json` write timing** → Training → *`checkpoint_info.json`*.
8. **Training log write timing** → Training → *Training log*.
9. **Export atomic write** — write to `<output>/.<name>.partial/`, then rename to `<output>/<name>/` in one OS operation. The temp folder **must** be a sibling of the final path: a rename is atomic only within one filesystem. Stale `.partial` folders in `<output>` are cleaned before the next export writes. Partial output must never be visible.
10. **Blocklist extensible** — the seed list is a starting point; make adding terms easy.
11. **`--yes` registration is per-prompt, not per-command.** `--yes` must reach `optica config` so it can auto-confirm the non-destructive `config --init` **create** prompt, and it must **not** answer the destructive overwrite or staging-clear prompts on that same command. *(A per-command rule would make the `config --init` create-confirmation unimplementable, which is why registration is scoped to prompts.)*
12. **`optica setup --ci`** → `optica setup` → *`--ci`*.
13. **Open Images label mapping** — verify integrity on every load; delete and re-download automatically with a status message if corrupt.
14. **Manifest labeling session ID** = hash of manifest file path + file content; a modified manifest starts a fresh session automatically.
15. **Phase tracking in checkpoints** → Training → *Checkpoints* and *`checkpoint_info.json`*.
16. **`random_state` generation and resume** → Training → *Dataset splitting* and *Checkpoints*.
17. **Class weights on imbalance** → Input & Acquisition → *Class imbalance and image validation*, and Training → *Optimization*.
18. **OOM handling** → Training → *OOM handling*.
19. **Safety warnings and safety prompts always fire inside `optica run`** — step-level resume prompts are suppressed there, and so is the checkpoint K/A/D/S prompt — housekeeping with a destructive branch, suppressed on those grounds rather than on any walk-away guarantee; safety items are not suppressed. Warnings (OOM, imbalance, finetune-ratio extremes) display and nothing suppresses them; safety **prompts** (the CPU batch-size prompt) fire and are suppressed only by `--force`. The two are named separately because the distinction decides what `--force` does.
20. **Redundant flags are no-ops** — e.g. `--exclude-extras clip --skip-keys` and similar redundant combinations are silently accepted, no warnings or errors.

#### Two gates before implementation

Two review passes run before implementation begins:

- **Post-V1 readiness pass.** Before ship, review every V1 decision for post-V1 implications — vocabulary that won't extend to new task types, output structures assuming classification, config taxonomy needing new categories. Run after ship, these decisions are already locked and changing them is breaking, so the pass only has value beforehand. (Populated as decisions land; e.g. `--only`'s file-group vocabulary under future export formats, the `--strict` hard-error structure extending to post-V1 behaviors.)
- **Pre-implementation verification pass — always last.** Re-verify only what can **decay between design and implementation**: package versions (the September 2026 snapshot ships on a weeks-to-months cadence), the `>=min, <next_major` dependency bounds (including whether FastAPI has reached 1.0, which changes the `<1.0` ceiling), the torch/CUDA variant names in the setup registry **and `torch-gpu`'s `index_url`, whose `cu<XXX>` placeholder must be resolved here to a CUDA build that exists at implementation time** (new torch releases drop old CUDA versions, so neither the name nor the index survives indefinitely), the open-clip-torch API surface, **whether the `download.pytorch.org` CUDA wheels declare the same exact `torch==` pin as the PyPI wheels — the pairing rule in Tech Stack derives compatibility from that declaration, and it has been verified only on PyPI**, and Click's restriction of variable-length `nargs` to positional arguments (which the comma value-separator convention depends on — verified against Click 8.5.0 / Typer 0.27.2, to be re-confirmed against the pinned versions). An open list — add items as design decisions surface new external dependencies. Its output is `pyproject.toml` content and verified install commands.

## Part IV — Reference

### Key Decisions

Most name the rejected alternative and why, to prevent re-proposal.

- **Aliases are permanent and task-aware.** `optica run` etc. are permanent aliases for `optica classify run` etc.; alias resolution consults `default_task` rather than hardcoding `classify`, so post-V1 task values slot in without restructuring the CLI. Low cost now, high cost to retrofit.
- **Mode naming: `label` / `curate` / `clip`**, over `auto1`/`auto2` — each names the path it runs rather than how much work the user does, so every mode matches something that already exists: `optica label`, `optica curate`, the CLIP Adapter. No hierarchy implied, post-V1 extensible. *Rejected: `manual`, which describes effort rather than path and is false whenever `--mode label` resolves to an already-organized dataset — labeling is skipped and no manual work occurs; and `local`, which names the input source, a distinction the input flags already carry and which the mode slot would duplicate.*
- **Transfer learning over scratch training.** Pretrained ImageNet weights give strong results on small datasets with short training on consumer hardware. Scratch training (`--model none`) is post-V1.
- **timm over the torchvision model zoo.** torchvision needs separate imports per architecture with inconsistent APIs; timm's unified `create_model()` covers all V1 and planned models in one dependency.
- **open-clip-torch over OpenAI's official CLIP.** OpenAI's release is largely unmaintained; open-clip-torch is active, offers more sizes, benchmarks better, and is fully local. Default ViT-B-32/openai — fastest, lowest RAM (~600MB), good enough for filtering.
- **TOML over YAML/JSON for config.** Python's native config format; human-readable, supports comments, no indentation footguns.
- **Local JSON logs over SQLite or wandb.** Zero extra dependencies, human-readable, no account, sufficient for V1's single-machine scope. Written to both global and project-local locations.
- **MD5 deduplication over perceptual hashing, within-class only.** Realistic duplicates are exact (same URL fetched twice), so near-duplicate detection does not earn V1 scope — that, not dependency weight, is what decides it. Perceptual hashing would also pull numpy + scipy in, and Core's 6-package lightness is an explicit value; but the cost is identical whenever the feature lands, so it cannot be the reason V1 says no and the fast-follow says yes. Within-class prevents cross-class false positives. *(Perceptual-hash near-duplicate detection with `dedup_threshold` is deferred to the fast-follow, arriving with `--strict`. **Whether numpy and scipy then enter Core or arrive behind an opt-in extra, leaving Core at six, is a fast-follow decision this plan deliberately does not prejudge.**)*
- **`dataset/` as a reserved folder.** Optica requires class subfolders inside it; loose images there trigger a clear error rather than silent misinterpretation.
- **`dataset/` size warning threshold 128px.** The default-mode image-validation warning fires at 128px — half the 224px input of three of the four backbones (`efficientnet_b4` is 320/384), where upscaling artifacts turn significant. The threshold is a single hardcoded value and deliberately does not follow the backbone. Reasoning is independent of `--strict`; V1 hardcodes it (as 64px was) with no config key.
- **Copy, never move or link, into `dataset/`.** "Originals untouched" is a stated requirement, so move is out. Symlinks are unreliable on Windows and break silently if the original moves; hardlinks fail across filesystems, forcing a conditional copy fallback anyway. The real cost — storage duplication at scale — is surfaced by a disk-usage note at copy time (`Copying 1,200 images (2.3 GB) to dataset/ — originals untouched`). A best-effort `--link` flag is a post-V1 addition.
- **Tabs→dropdown at 7 classes (curation).** Up to 6 short-named tabs fit; at 7+ or any name over 20 chars, a dropdown is cleaner. This is the *curation* threshold — labeling uses a distinct radio 2–5 / dropdown 6+ threshold. Two UIs, two thresholds — not to be harmonized.
- **Two-tier config (global + project-local).** Global for defaults and API keys; optional project-local for overrides (committed, not gitignored). Familiar pattern (ESLint, git). API keys never in the project-local file.
- **Lightweight `pip install`; platform-dependent packages via `optica setup`.** Core is 6 lightweight packages. The deferral applies specifically to the **platform-dependent** torch stack (index-URL constraint), not to "heavy packages" generally — FastAPI, uvicorn, onnx, onnxruntime are ordinary pip extras precisely because that constraint doesn't touch them.
- **`optica setup` is always global, never per-project.** Per-project configuration is `optica config --init`. No `--local` flag.
- **Async only in FastAPI routes.** Only one async component exists; async elsewhere adds complexity for no benefit.
- **Flexible Tier-5 `Classifier` with state validation over strict ordering.** Advanced users legitimately skip steps; state validation gives helpful errors rather than enforcing a rigid sequence.
- **`optica relabel` deferred to post-V1.** An edge case of an edge case; the manual workaround (move files between folders) exists. V1 command surface stays small. (Its eventual scope — rename/merge/unmerge/reassign — is larger than "move files.")
- **Prompts live in the CLI only; the API raises errors.** The API behaves as though `--yes` were always passed, so no `auto_confirm=` equivalent exists; only the destructive `dataset/` overwrite needs an explicit `overwrite=True`.
- **`--yes` never drives `optica setup`.** Setup's interactivity is binary — any relevant flag makes it fully non-interactive — so `--yes` has no role.
- **Checkpoint naming: val accuracy + epoch + `_x` auto-increment.** Collision checking is active-folder only; `run_id` links checkpoints to their log; global ranking by val accuracy at export.
- **A checkpoint is a folder, and `checkpoint_path` always names one** — relative to the project root, at every site: the training log's `checkpoint_paths`, `model_info.json`, the stale-path warning, the Tier 5 constructor, and `clf.checkpoint_path`. *Rejected: a `.pt` file in the constructor, which cannot supply the `checkpoint_info.json` that `export()` reads.*
- **`random_state` fixed per training run.** Generated once, saved, reloaded on resume — guarantees identical splits across interruptions, preventing silent data leakage.
- **Auto class weighting on imbalance.** When any class is below 50% of the largest, the user may continue with automatic `CrossEntropyLoss` weighting — transparent, logged, no extra data.
- **Step commands expose the pipeline's user-facing stages; `optica run` runs whichever of them an invocation still needs (a governing meta-rule).** The split exists to let users choose how much of the pipeline they want, not to keep commands small. A command therefore accepts only what its own stage can act on — `optica train` takes an organized dataset or a fully-labeled manifest, never a flat folder, because labeling is another stage's work. **This rule governs whether a future capability becomes its own command or stays inside one.**
- **CLI flag rule for training hyperparameters (a governing meta-rule).** A parameter gets a CLI flag if a non-advanced user is likely to adjust it per-run for practical reasons; it is config-only if tuning it needs ML knowledge or it's set once per project. Applied: `--epochs`, `--batch-size`, `--model`, `--no-augmentation` are flags; `learning_rate`, `early_stopping`, `finetune_ratio`, `optimizer` are config-only. **This rule governs future flag decisions.**
- **Open Images via direct HTTP.** No extra dependency (reuses httpx); metadata and label mapping from GCS, image bytes from the `staticflickr.com` URLs the dataset lists; label mapping cached and verified on load.
- **Task-namespaced Python API from V1, over a `task=` parameter.** `optica.classify.run()` canonical, flat aliases routing via `default_task`. A unified `task=` surface would be hollow once task-specific steps (e.g. `annotate`) exist.
- **Five documentation tiers, over four.** The 4-tier option (splitting CLI into basic/advanced) framed a workflow difference as a skill ladder. The 5-tier structure separates interface × complexity with one expert outlier.
- **`web` extra name, over `server` or `browser`.** `server` overclaims (Optica hosts nothing in V1); `browser` undersells (misses the future REST export). `web` is accurate for V1 and forward-compatible.
- **`OpticaCLIPLoadError` as a second CLIP exception, and `OpticaBrowserServerError` named for its subsystem rather than a caller.** Descriptive names for operational failures; extra-named classes for missing dependencies. (See Exceptions.)
- **Feature-based extras in V1, over task-grouped extras.** Extras are grouped by *capability* (`web`, `clip`, `onnx`) rather than by task. Task groups arrive with the first post-V1 task type, which is the point at which the distinction first means anything. `optica[classification]` is deliberately **not** offered in V1: with one task type it would resolve to exactly the same package set as `optica[all]`, so it would signal a boundary that does not yet exist.
- **`optica[test]` as a lean, non-user-facing extra named `test`, over `[dev]`.** `[dev]` would grow to hold docs tooling and slow every CI matrix leg; docs tooling gets its own `[docs]` extra when the site lands.
- **`dataset_path` absolute, routed via `checkpoint_info.json`.** Absolute because `--dataset` can point outside the project; written at training, copied to `model_info.json` at export.

---

### Known Constraints

- **`dataset/` is reserved** — loose images placed directly there trigger an error, not silent misinterpretation.
- **API keys never in `.optica.toml`** — always `~/.optica/config.toml` or env vars. `flickr_api_key` is a real config key — spelled like every other key, and `optica config --view` masks the value while keeping the source annotation, so a user can tell *where* a key came from without disclosing it. The rule is enforced at both ends — `config --init` never emits the key, and a key found in a project-local file is rejected at config-load time.
- **Staging is auto-fetch only** — user-provided images are always copied, never staged or deleted.
- **Curation server is localhost only, and only the session Optica opened can drive it** — binds to `127.0.0.1`, never network-exposed, refuses a request without that session's key, shuts down after use.
- **Aliases are permanent** — never deprecated or removed; this extends to the Python API aliases, and `--checkpoint` is kept as a permanent alias after the `--checkpoint-rank` rename.
- **`optica setup` is always global** — never per-project; no `--local` flag.
- **Platform-dependent packages not in `pip install optica`** — torch, torchvision, timm, scikit-learn are installed hardware-appropriately by `optica setup`; `optica[clip]` is the one path that reaches three of them without it, since `open-clip-torch` declares them. Setup owns them because of the torch index-URL constraint (which does not apply to the ordinary pip extras).
- **`open-clip-torch` is optional** — never imported at module top level; always lazily guarded, re-raised as `OpticaCLIPError` if missing.
- **`optica relabel` is post-V1** — do not implement in V1.
- **No Weights & Biases (wandb)** — post-V1 only.
- **No nested subfolders inside class folders** — a hard error in V1, deliberately not auto-resolving the flatten-vs-promote ambiguity (the two readings are genuinely different actions; silently picking either risks misclassifying a real dataset). The message names both paths and lists every detected nested folder:
  ```
  ✕ Nested subfolders found inside class 'cat' (outdoor/, indoor/) — unsupported.
    Flatten: move images up into dataset/cat/ directly, or
    Separate: rename folders as their own top-level classes:
      dataset/cat/outdoor/ → dataset/cat_outdoor/
      dataset/cat/indoor/  → dataset/cat_indoor/
  ```
- **No training from scratch** — `--model none` is post-V1.
- **Async only in FastAPI routes** — do not introduce async elsewhere.
- **Hard training floor — 5 images per class** — training is refused if any class has fewer than 5, with an educational error (the browser Finish button gates on this floor together with the 2-class minimum, showing both at once).
- **Hard training floor — 2 classes minimum** — fewer than 2 resolved classes is refused across `fetch`/`label`/`train`/`run` and the inferred-from-folders case.
- **Global lock file** — only one write command runs at a time; a second is hard-blocked while the first holds `~/.optica/optica.lock` (`config --view`, `config --set` and `--version` are exempt). See Implementation Notes.
- **Undefinable class names in auto modes** — blocklist enforced, confirmation step required, user-definition prompt for abstract names.
- **`--yes` does not bypass browser curation** — `--mode clip` is the fully non-interactive acquisition path. *(This constraint is what makes clip mode core: it is the only non-interactive path from "no images" to "trained model" — with one exception: a blocklisted class name pauses for sub-term definition, which `--yes` cannot answer, the prompt having no safe default. That is why the prompt raises `OpticaValidationError` wherever no prompt can fire — always in the Python API, and on the CLI whenever the run is unattended — rather than defaulting.)*
- **CLIP threshold calibrated for ViT-B-32/openai** — `clip_threshold = 0.25`; calibrated for the model, the weights **and** the `"a photo of a {class}"` prompt template together — a post-V1 change to any of the three may require recalibration.
- **CLIP threshold is a single global value** — applied uniformly across classes; CLIP scores aren't directly comparable across visual concepts, so one threshold may over- or under-filter a given class. *Accepted V1 imperfection*; per-class thresholds are post-V1.
- **MD5 deduplication is within-class only** — the same image in two classes is not detected (a known accuracy risk from contradictory labels). Within-class MD5 stands for V1; cross-class and perceptual-hash deduplication are post-V1/fast-follow.
- **Search query quality** — class names are used directly as search queries; ambiguous names may return irrelevant images. curate relies on human review, clip mode on CLIP filtering — neither prevents poor fetches upfront. Use specific names.

---

### CLI Flag Reference (V1)

| Long | Short | Default | Notes |
|---|---|---|---|
| `--source` | `-s` | `open-datasets` | `optica fetch`, `run` only. `flickr`, `open-datasets` |
| `--classes` | `-c` | inferred from folders (`train` only) | Required for `fetch`/`label`, **which cannot infer it** — absent, it raises the class-name prompt where a prompt can fire and a hard error where one cannot; inferred for `train` when `dataset/` exists; warned and ignored by `curate`, which reads the fetched staging structure. `run` takes the disposition of the stage it starts from. Comma-separated; quote per value: `--classes "orange cat",dog` |
| `--model` | none | `efficientnet-small` | `optica train`, `run` only. No alias — conflicts with `-m` conventions. `efficientnet-small`, `efficientnet-large`, `resnet`, `resnet-50`, `mobilenet`, `mobilenet-large` — `resnet`/`resnet-50` and `mobilenet`/`mobilenet-large` are alias pairs, one model each |
| `--epochs` | `-e` | `10` | `optica train`, `run` only |
| `--images-per-class` | `-i` | `50` | `optica fetch`, `run` only. Images per class to fetch |
| `--output` | `-o` | `./optica-output` | `optica train`, `export`, `run`. Container folder for all run outputs — exports and the project-local training log |
| `--dataset` | `-d` | `./dataset` | `optica fetch`, `label`, `curate`, `train`, `run`. Organized dataset folder |
| `--folder` | none | none | `optica label`, `run` only. Flat folder for labeling. Distinct from `--dataset` |
| `--manifest` | none | none | `optica label`, `run`; `train` only when fully labeled. CSV or JSON manifest file |
| `--mode` | none | contextual | `label`, `curate`, `clip`. `optica fetch`, `run` only — `fetch` accepts `curate`, `clip`. **Default is contextual**: `curate` when acquiring by fetch, `label` when `--folder` or `--manifest` is given |
| `--checkpoint-rank` | none | **none — prompts** | `optica export`, `run` only. **Absence is not rank 1**: it raises the export checkpoint selection prompt, which `--yes` answers with rank 1 (see Training → *Checkpoints*). Accepts multiple: `--checkpoint-rank 1,2,3`. `--checkpoint` retained as a permanent alias |
| `--no-augmentation` | none | off | `optica train`, `run` only. Disables all data augmentation |
| `--batch-size` | none | `32` | `optica train`, `run` only. Hardware-dependent — reduce if OOM on CPU |
| `--clip-threshold` | none | `0.25` | CLIP confidence threshold for clip mode. `optica fetch`, `run` only — follows `--mode` |
| `--verbose` | none | off | Global, either position. Adds detail to progress and status output; does not affect warnings, prompts or errors |
| `--quiet` | none | off | Global, either position. Suppresses progress and status output only; warnings, prompts and errors still display |
| `--yes` | `-y` | off | Global; not applicable to `optica setup`. Answers **Y** to every Y/N prompt in scope — not the prompt's default — and takes the listed option for multi-letter prompts; see the `--yes` behaviour table. Never destructive prompts — the `dataset/` overwrite takes `--overwrite` |
| `--force` | `-f` | off | Global; bypasses safety prompts only — **never destructive prompts**, which each take their own dedicated flag. Does not suppress warnings or override hard errors |
| `--overwrite` | none | off | `optica run`, `fetch` (under `--mode clip`), `label`, `curate`, `train` (manifest materialisation) — every path that writes `dataset/`. Authorizes the `dataset/` overwrite prompt unattended, which neither `--yes` nor `--force` does. Maps to the API's per-operation `overwrite=True` |
| `--dry-run` | none | off | `optica fetch`, `train`, `export`, `run` only |
| `--set` | none | — | `optica config` only — set a config key: `optica config --set epochs 20` |
| `--init` | none | — | `optica config` only — create a project-local `.optica.toml` |
| `--view` | none | — | `optica config` only — show resolved config with source annotations |
| `--clear-staging` | none | — | `optica config` only — list and clear all staging contents, with confirmation |
| `--global` | none | off | `optica config --set` only — forces write to global config |
| `--version` | none | — | Print installed Optica version |
| `--include-extras` | none | — | `optica setup` — comma-separated extra keys to add |
| `--exclude-extras` | none | — | `optica setup` — comma-separated extra keys to remove |
| `--all-extras` | none | off | `optica setup` — install all relevant extras. Errors with `--no-extras` |
| `--no-extras` | none | off | `optica setup` — install no extras. Errors with `--all-extras` |
| `--upgrade` | none | off | `optica setup`, interactive only — errors with the extras-selection flags. Check for and surface upgradeable packages |
| `--ci` | none | off | `optica setup` — config init only: no package install, no environment detection, no prompts. Errors with the extras-selection flags. See `optica setup` → *`--ci`* |
| `--skip-keys` | none | off | `optica setup` — skips API key prompts entirely |

> *Note on `-f`:* only `--force` claims `-f` at first ship. When `--format` arrives at the fast-follow it will need its own resolution (`--force` keeps `-f` as the global flag that shipped first; `--format` takes a different short form or none, following the `--strict` precedent of declining an alias rather than colliding). No collision exists in V1. `-s` belongs to `--source`, which is why `--strict` deliberately has no alias — consistent, not accidental.

---

### Documentation

Three documentation layers ship with V1; the fourth (the docs site) is a fast-follow addition. *(The classification is per-layer: docstrings are inseparable from the code, README and CHANGELOG are core, and the docs site is deferred — the README already tells a complete documentation story for first ship.)*

- **Docstrings** — Google style, all public functions and classes, written during implementation as a coding-style requirement (inseparable — no independent classification). Power the auto-generated API reference.
- **README** — ships with V1. Covers installation (including the two-step `pip install` + `optica setup` flow and the `requirements.txt` limitation note), quickstart, and examples across **all five tiers** — with **Quick Start (Tier 1) and Simple API (Tier 3) as distinct sections**, not merged, since their contracts differ. Includes a **CLI reference summary** (the 33-row flag table above), maps **install state to tier entry points** (the tier structure being a documentation concept), and carries the `--yes`-doesn't-bypass-curation note and search-query guidance. PyPI renders the README as the project page — it is the entry point for all five tiers, so it is load-bearing for the ship.
- **CHANGELOG.md** — ships with V1. Minimum entry: `## [0.2.0] — Initial release.` Core by release convention, near-zero cost.

**Docs site (fast-follow):** MkDocs + Material, auto-generating the API reference from docstrings, with hand-written guides. Deferred because the README already covers installation, quickstart, all-tier examples, and a CLI reference summary — a complete V1 documentation story — and the site is purely additive (it reads docstrings and markdown that already exist, so building it later costs nothing extra). Its grown obligations travel with it: mapping install state to tier entry points (also a README obligation) and documenting the accepted `requirements.txt` limitation.

Documentation is a first-ship priority for the layers that ship, not an afterthought — but that priority does not by itself force every layer to block the first ship.
