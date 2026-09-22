# Build log

Append-only. Two kinds of entry: assumptions made where the plan was silent, and
a line at each pass boundary. Not a specification, and not authority over
`spec/optica-plan-v1-core.md`.

This file is the reason a mid-build gap does not need a hard stop. If an
assumption is not written here, it was made silently — which is the one outcome
the gap rule exists to prevent.

## Assumption entries

```
### <short name>
**Pass:** N   **Date:** YYYY-MM-DD   **Where:** path/to/file.py:function
**Missing:** what the plan does not say
**Assumed:** what was done instead
**Why:** the reasoning, including any alternative rejected
**Reversible?** what would have to change if this is overruled
```

## Pass boundary entries

```
### Pass N — closed
**Date:** YYYY-MM-DD
**Built:** modules completed
**Milestone:** the pass's "done when" condition, and whether it was met
**Left open:** anything deferred, and to which pass
**Assumptions logged this pass:** count, with names
```

---

## Pass 0

### Proposed plan change — `Thumbnail300KURL` fallback condition
**Pass:** 0   **Date:** 2026-09-12   **Where:** plan § "Fetch sources"; affects `input/fetch.py` (pass 2)
**Missing:** nothing missing — this is a **verified contradiction** of the plan,
raised under `CLAUDE.md` § "The plan is read-only". Not applied to `spec/`.
**Found:** the plan says `OriginalURL` is the fallback "where that column is
**absent**". Measured against the live V7 files, the column is never absent — it
is present in all 12 headers of every image-metadata CSV. What varies is the
value: empty on **539 of 21,856 sampled rows (2.47%)**. `OriginalURL` is 100%
populated; zero rows have both empty. Evidence in `notes/verified.md` § task 3.
**Proposed wording:** "with `OriginalURL` as the fallback **where that value is
empty**" (replacing "where that column is absent"). One clause, no structural
change; the preference order and the per-image scope are already correct.
**Why it matters:** implemented literally, the fallback never fires and ~1 image
in 40 is fetched from an empty URL. Fails as a dead-URL case rather than loudly,
so it would be absorbed by the fill-to-target loop and never surface as a bug.
**Reversible?** Trivially — it is a single branch condition in the fetch path.

### Open Images metadata is far larger than the plan's "~100KB" figure
**Pass:** 0   **Date:** 2026-09-12   **Where:** plan § "Fetch sources"; affects pass 2
**Missing:** the plan describes the cached Open Images artifact as "A ~100KB
label-mapping file … cached in `~/.optica/`", and deliberately leaves its exact
name and format to the pre-implementation gate.
**Found:** neither label-mapping candidate is ~100KB —
`oidv7-class-descriptions.csv` is **501,178 B**, `oidv7-class-descriptions-boxable.csv`
is **12,064 B**. Separately, mapping a class to *image URLs* requires an
image-metadata CSV: **608.8 MiB** (V7's "Train" link) or **2,560.3 MiB** (the
V6-named train file). Sizes in `notes/verified.md` § task 3.
**Assumed:** nothing yet — pass 0 writes no code. Flagged for pass 2, which owns
`input/fetch.py` and must decide whether to stream/range-query the large CSV, use
per-class annotation files, or cache a derived index. The "~100KB" sentence is
sound for the label mapping alone but must not be read as covering image lookup.
**Reversible?** Yes — it is an acquisition-strategy decision local to pass 2.

### `optica setup` cannot pass `--index-url` for all four Tier 3 packages
**Pass:** 0   **Date:** 2026-09-12   **Where:** plan §§ "Package install split", "Registry and resolution"; affects `cli/setup.py` (pass 5)
**Missing:** the plan has setup install four packages (`torch`, `torchvision`,
`timm`, `scikit-learn`) and says each variant's `index_url` "builds the pip
command per variant", without saying how a single command reaches packages the
variant index does not serve.
**Found:** `timm` and `scikit-learn` do **not** exist on
`download.pytorch.org/whl/cu130` — both return `No matching distribution found`.
Because `--index-url` *replaces* PyPI rather than supplementing it, one command
carrying `--index-url <variant>` for all four fails.
**Assumed:** nothing yet — pass 5 owns this. The two candidate shapes are adding
`--extra-index-url https://pypi.org/simple`, or splitting into two commands
(torch stack from the variant index, then `timm`/`scikit-learn` from PyPI). The
split is likely preferable: `--extra-index-url` lets pip choose between indexes
per package, which can silently pull a PyPI `torch` over the variant one.
**Reversible?** Yes — confined to the command construction in `cli/setup.py`.

### `notes/passes/pass-4.md` wrongly claims to be the first pass needing torch
**Pass:** 0   **Date:** 2026-09-12   **Where:** `notes/passes/pass-4.md` line 3
**Found:** pass-4.md opens "**The first pass that needs torch.** Install it
before starting." This is wrong. **Pass 0 task 4 needs torch and timm actually
installed** — it instantiates the four backbones and reads
`model.named_parameters()` and `resolve_model_data_config()`, which cannot be
done without the packages present. Pass 0 tasks 1 and 2 also concern torch,
though those need only wheel *metadata* and so are answerable without an install.
So pass 4 is not the first pass to need torch in either sense.
**Action taken:** logged only. `pass-4.md` is **not** corrected — recording the
contradiction here was the instruction, and pass-4.md is a derived artifact under
`notes/`, not authority over anything.
**Consequence:** none for pass 4's own work. The line is misleading only if read
as a sequencing constraint, which it is not; pass 0 already installed the stack
into a throwaway probe venv (see `notes/verified.md` § task 4) rather than into
`.venv`, precisely so pass 1's "no torch present" milestone stays meaningful.

### `notes/passes/pass-0.md` step 4's description of `.gitignore` is stale
**Pass:** 0   **Date:** 2026-09-12   **Where:** `notes/passes/pass-0.md` step 4
**Found:** step 4 asks that ten entries be **added** to `.gitignore` and warns
that "the existing file ends without a trailing newline, so append a newline
first or the first new entry will fuse onto `.env`". As committed, `.gitignore`
already carries all ten — `dataset/`, `checkpoints/`, `optica-output/`,
`.smoke/`, `.claude/settings.local.json`, `build/`, `*.py[cod]`,
`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` — plus `.env.*` and `.vscode/`,
which step 4 does not mention. Git status was clean at session start, so this is
committed state and not an uncommitted edit. The trailing-newline hazard is
therefore moot: there is nothing to append.
**Action taken:** step 4 verified and recorded as a no-op; no edit made, no
entry duplicated. `pass-0.md` not corrected (derived artifact, log-only).

### Version classifiers are assigned to two different passes
**Pass:** 0   **Date:** 2026-09-12   **Where:** `CLAUDE.md` § "Build order" vs `notes/passes/pass-0.md` step 5
**Missing:** `CLAUDE.md`'s pass table lists "version classifiers" under **pass
6**; `pass-0.md` step 5 asks for "the Python version classifiers for 3.11, 3.12
and 3.13" in **pass 0**. Neither defers to the other.
**Assumed:** written in pass 0, per `pass-0.md` step 5, since it is the more
specific instruction for this pass and the classifiers are a precondition for a
coherent `pyproject.toml` rather than a documentation task. Pass 6 then verifies
them against the CI matrix instead of authoring them.
**Why:** the alternative — leaving `pyproject.toml` without classifiers through
five passes — makes every intermediate `pip install -e .` describe a package
that claims no Python support, and pass 1's milestone runs exactly that command.
**Reversible?** Yes, trivially; it is three lines of metadata.

### The plan's pre-implementation gate is broader than pass 0's four tasks
**Pass:** 0   **Date:** 2026-09-12   **Where:** plan § "Two gates before implementation"
**Missing:** the plan's pre-implementation gate names more items than pass 0
verifies: package versions (**done** — re-checked, snapshot still accurate), the
`>=min,<next_major` bounds including whether FastAPI has reached 1.0, the torch
variant names and `torch-gpu` `index_url` (**done** — `cu130`), the
open-clip-torch API surface, and Click's restriction of variable-length `nargs`
to positional arguments. `pass-0.md` scopes pass 0 to four tasks, so the
remainder has no owning pass.
**Assumed:** the unclaimed items stay unverified in pass 0 and attach to the
pass that first depends on them — Click `nargs` to pass 1 (it underpins the
comma value-separator convention in the CLI skeleton), open-clip-torch's API to
pass 4 (`input/clip.py`), FastAPI's 1.0 status to pass 3 (`server/`). Flickr API
endpoints and rate limits (Implementation Note 4) likewise belong to pass 2.
**Why:** pass 0 is explicitly scoped and `CLAUDE.md` forbids building outside the
current pass's scope; verifying a fact five passes before its consumer also risks
it decaying again before use.
**Reversible?** Yes — each is an independent check, recordable in
`notes/verified.md` whenever it is run.

### Correction — the pass-4.md entry above overstated the probe venv's state
**Pass:** 0   **Date:** 2026-09-12   **Corrects:** *"`notes/passes/pass-4.md`
wrongly claims to be the first pass needing torch"*, above (this file is
append-only, so that entry stands as written and this entry overrides it).
**What was wrong:** that entry's closing sentence reads "pass 0 already
installed the stack into a throwaway probe venv (see `notes/verified.md`
§ task 4)". Both halves are false at the time of writing. The probe venv at
`C:/dev/optica-probe` exists and runs Python 3.11.9, but it holds only `pip`
and `packaging` — **no torch and no timm**. And `notes/verified.md` has no
"§ task 4"; task 4 is **still unchecked**.
**What is true:** the *plan* for the probe venv is as described — torch and timm
go there and never into `.venv`, so pass 1's "`optica --version` with no torch
present" milestone stays a real check rather than a vacuous one. That is a
decision taken, not a state reached. The venv was created early because tasks 1
and 2 use its `pip` for wheel-metadata and index queries, which need no torch.
**Why the error matters more than its size:** it asserted a verification result
that did not exist, and pointed at a citation that did not exist, in the file
whose whole purpose is to stop exactly that. It is the same failure mode
`CLAUDE.md` records six instances of — a document checked against itself rather
than against the world. Nothing had been built on it, so the cost was zero this
time.
**Standing rule this reinforces:** do not write a pass's outcome in past tense
before the command has run. `notes/verified.md` § task 4 may be cited only once
it exists.

### `mobilenetv3_large_100`'s "Last 3 InvertedResidual blocks" is ambiguous
**Pass:** 0   **Date:** 2026-09-12   **Where:** plan § "Training" → *"Last layers" per architecture*; affects `training/models.py` (pass 4)
**Missing:** the plan names mobilenet's Phase 2 set as "Last 3 InvertedResidual
blocks" without indices. Verified against timm 1.0.29, the last stage
`blocks[6]` is a **`ConvBnAct`**, not an `InvertedResidual` — `blocks[1]`
through `blocks[5]` are the InvertedResidual stages and `blocks[0]` is a
`DepthwiseSeparableConv`. The two readings select different layers:
- **literal** ("InvertedResidual" is meant as the type): `blocks[3,4,5]`, 2,755,312 params
- **positional** ("last 3 blocks"): `blocks[4,5,6]`, 2,780,008 params

**Assumed:** nothing — pass 0 writes no code, and pass 4 owns `models.py`.
Recommendation for pass 4: take the **positional** reading, `blocks[4,5,6]`.
Freezing is naturally expressed as a suffix of the stage list, the plan's
efficientnet rows are positional (`blocks[5], blocks[6]`), and excluding the
final `ConvBnAct` while unfreezing everything before it would leave the last
convolution in the network frozen beneath trainable layers.
**Why it matters:** the difference is small in parameter count but not in
behaviour, and the plan's phrase is unambiguous for the efficientnets
(`blocks[6]` there *is* an InvertedResidual) which is exactly what makes it easy
to apply the wrong reading to mobilenet without noticing.
**Reversible?** Yes — one index list in `models.py`. Values in
`notes/verified.md` § task 4.

### `bn2` is absent from the efficientnets' documented unfreeze set
**Pass:** 0   **Date:** 2026-09-12   **Where:** plan § "Training" → *"Last layers" per architecture*; affects `training/models.py` (pass 4)
**Missing:** both `efficientnet_b0` and `efficientnet_b4` carry a top-level
`bn2` immediately after `conv_head` (module order: `conv_stem`, `bn1`, `blocks`,
`conv_head`, `bn2`, `global_pool`, `classifier`). The plan's Phase 2 group is
"`blocks[5]`, `blocks[6]` + `conv_head`" and does not mention `bn2`, so a
literal implementation unfreezes `conv_head` while leaving its own BatchNorm
frozen. 2,560 params on b0, 3,584 on b4.
**Assumed:** nothing yet — pass 4's call. Recommendation: include `bn2`. A
conv and its immediately following norm are one unit for fine-tuning purposes,
and the plan's omission reads as an oversight rather than an intent, since no
rationale is given for splitting them.
**Reversible?** Yes — one prefix in the unfreeze list.

### `EXTRAS_REGISTRY` `size_estimate` values are wrong for `torch-cpu`
**Pass:** 0   **Date:** 2026-09-12   **Where:** plan § "Registry and resolution"; affects `cli/setup.py` registry (pass 5)
**Missing:** nothing missing — measured values now exist where only estimates
did. `size_estimate` feeds the setup review step's download total, so the
numbers are user-facing.

| Entry | Declared | Measured (Linux / Windows) | Verdict |
|---|---|---|---|
| `torch-cpu` | `~1GB` | 0.29 GB / 0.21 GB | **3–5× overestimate** |
| `torch-gpu` | `~2GB` | 2.40 GB / 2.08 GB | close, slightly low |
| `torch-auto` | `~1–2GB` | 2.40 GB / 2.08 GB | top of range too low |

**Assumed:** nothing changed in pass 0 — the registry is pass 5's file and
`CLAUDE.md` forbids building outside the current pass. Recommendation for
pass 5: `torch-cpu` `~250MB`, `torch-gpu` `~2–2.5GB`, `torch-auto`
`~250MB–2.5GB`. `torch-cpu` is the one that actually misleads: overstating the
CPU download 4× pushes a user toward a GPU install they may not need.
**Reversible?** Yes — three string literals. Breakdown in
`notes/verified.md` § task 2.

### Pass 0 — closed
**Date:** 2026-09-12
**Built:** no implementation code, as specified. Deliverables are
`notes/verified.md` (machine record, step 1, and all four verification tasks
answered) and `pyproject.toml`'s three step-5 edits: sdist exclusions for
`spec/` and `notes/`, `markers = ["slow: requires torch"]`, and the Python
3.11/3.12/3.13 classifiers. `version` left at `0.1.1`, untouched.
**Milestone:** *"`notes/verified.md` holds four answered entries plus the machine
record, and `pyproject.toml` is in place."* — **met.**
- Step 1: the **prepared** `pyproject.toml` is the one committed; checked
  against Tech Stack (Core is exactly 6, `click`/`pydantic` absent). No
  replacement needed.
- Step 4 (`.gitignore`): verified a **no-op** — all ten entries were already
  committed, no duplicates, file already ends with a newline. See the stale-
  description entry above.
- Task 1: gate did **not** fire. Both indexes declare `torch==2.14.0`. Plan
  unchanged.
- Task 2: measured on both platforms and all three indexes, per-item. Two
  earlier attempts were rejected as invalid and are recorded rather than
  deleted.
- Task 3: columns confirmed for V7, with the V7→`2018_04` link cited from the
  V7 page itself.
- Task 4: run in the probe venv at `C:/dev/optica-probe` (torch 2.14.0+cpu,
  timm 1.0.29, `pretrained=False`, no weights fetched). **`.venv` was left
  without torch and re-checked afterwards**, so pass 1's milestone stays a real
  check.
**Left open:**
- Plan wording change proposed for the `Thumbnail300KURL` fallback → **pass 2**.
- Open Images metadata size vs the "~100KB" framing → **pass 2**.
- `optica setup`'s pip command shape, and the `size_estimate` revisions →
  **pass 5**.
- mobilenet unfreeze reading, and `bn2` inclusion → **pass 4**.
- Unclaimed pre-implementation-gate items (Click `nargs` → pass 1,
  FastAPI 1.0 → pass 3, open-clip-torch API → pass 4, Flickr API → pass 2).
**Entries logged this pass:** 11 — thumbnail-fallback plan change;
open-images-metadata size; setup `--index-url`; pass-4.md torch claim;
pass-0.md `.gitignore` staleness; version-classifier pass overlap;
pre-implementation-gate breadth; the correction to the pass-4.md entry;
mobilenet unfreeze ambiguity; efficientnet `bn2`; `size_estimate` values.
Of these, **two are assumptions** (classifiers written in pass 0; unclaimed
gate items deferred to their consuming passes); one is a **proposed plan
change** awaiting a decision; one is a **correction** to an earlier entry in
this file; the rest are findings handed to later passes.
**Next:** pass 1 — `exceptions.py`, `utils/`, `config/`, CLI skeleton, the
**global Typer exception handler first**, exit codes, minimal `ci.yml`.

---

## Pass 1

### The global exception handler's mechanism — `app.exception_handler()` does not exist
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/cli/main.py:OpticaTyper.__call__`
**Missing:** the plan specifies the handler twice (§ "Error handling and prompt
conventions", Implementation Note 1) as "a global handler via
`app.exception_handler()`". **That method does not exist on `typer.Typer`** —
0.27.2 exposes exactly `add_typer`, `callback`, `command`, and Typer has never
shipped an `exception_handler`; it is FastAPI's API. Verified in
`notes/verified.md` § "`typer.Typer` has no `exception_handler()` method".
**Assumed:** the plan's **behaviour** is implemented in full and only the
spelling changes. `cli/main.py` defines `OpticaTyper(typer.Typer)` overriding
`__call__` to run `super().__call__(..., standalone_mode=False)` inside the
global `try/except`, which is what makes Click propagate exceptions to us
instead of printing and exiting on its own. The contract the plan states is
unchanged: `UsageError` caught **at the base** (not a named list), `Abort`
handled separately at `130`, no raw traceback ever reaching the user.
**Why:** the alternative — a `main()` wrapper function — would force
`[project.scripts]` to `optica.cli.main:main`, and the plan fixes that entry
point as `optica.cli.main:app` in § "Code Structure". Subclassing keeps `app` the
name the entry point resolves, keeps `@app.command()` working, and puts the
handler on the one code path every invocation takes. *Rejected: `sys.excepthook`,
which Typer already owns and overwrites in `Typer.__call__`; and a decorator per
command, which is the "named list" failure mode the plan rejects, one level up.*
**Reversible?** Yes — the handler is one method on one class, and the
exception-to-exit-code mapping it drives is a single table.

### `click` is not importable — the vendored class is the only one Typer raises
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/cli/main.py` imports
**Missing:** the plan writes the handler's catch as `click.UsageError`, and
`CLAUDE.md` § "Settled points" justifies excluding `click` from the dependency
list on the grounds that it "arrive[s] transitively through `typer`". **It does
not.** typer 0.27.2 vendors Click as the private `typer._click` and declares no
dependency on it; `import click` fails in a Core install. Verified in
`notes/verified.md` § "Typer 0.27.2 vendors Click".
**Assumed:** import `UsageError`, `BadOptionUsage` and `MissingParameter` from
`typer._click.exceptions`, and treat the private path as a pinned contract rather
than an incidental detail — `tests/unit/cli/test_main.py` drives a real parser
error through the app and asserts the handler caught it, so a Typer bump that
moves the module fails a test instead of silently letting tracebacks through.
**Why:** `CLAUDE.md`'s instruction (do not add `click`) survives its own broken
premise, and for a sharper reason than the one given: installing real Click would
add a **second, unrelated** `UsageError` class while Typer kept raising the
vendored one, so `except click.UsageError` would stop firing with no error
anywhere. Core stays at six packages. *Rejected: catching the public
`typer.TyperException` instead — it is the base of the whole vendored tree, so it
would also swallow non-usage `ClickException`s and hand them exit `2`, which is
exactly the over-broad catch the plan's "at the base, not a named list" wording
exists to get right.*
**Reversible?** Yes, and cheaply: one import line, guarded by a test that names
the failure.

### ASCII fallback for the four status glyphs
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/utils/logging.py:Markers`
**Missing:** the plan's output format uses four non-ASCII markers — U+2715
(error), U+2713 (success), U+2717 (incomplete), U+26A0 (warning) — and says
nothing about terminals that cannot encode them.
**Found:** on this machine (console codepage cp1255) writing U+2713 to **stdout**
raises `UnicodeEncodeError`, through Rich as well as through `print()`;
`sys.stdout.errors` is `surrogateescape` while `sys.stderr.errors` is
`backslashreplace`, so stderr survives and stdout does not. Measured in
`notes/verified.md` § "Non-ASCII status glyphs crash on a non-UTF-8 Windows
stdout".
**Assumed:** `utils/logging.py` tests each glyph once against the target stream's
encoding and substitutes ASCII where it cannot be encoded — U+2715 to `X`, U+2717
to `x`, U+2713 to `+`, U+26A0 to `!`. The glyphs are used unchanged wherever the
stream can carry them, which is every UTF-8 terminal, all three CI runners' UTF-8
paths, and any redirect to a file opened as UTF-8.
**Why:** an unhandled `UnicodeEncodeError` on a status line is a raw traceback
reaching the user, which plan § "Coding Style" forbids unconditionally, and it
fires on a stock Windows console for output the user did nothing unusual to ask
for. Windows is a named best-effort target, so "it only breaks on Windows" is not
a reason to leave it. *Rejected: forcing UTF-8 onto the stream, which produces
mojibake on a legacy console rather than a crash — quieter, not better; and
`errors="backslashreplace"` on stdout, which renders a literal escape sequence
where a mark belongs and is strictly harder to read than `X`.*
**Reversible?** Yes — one mapping in one module, and no caller spells a glyph
itself.

### `ExitCode` placed in `exceptions.py`
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/exceptions.py:ExitCode`
**Missing:** the plan gives the exit-code table but no home for it;
§ "Code Structure" describes `exceptions.py` as "all exception classes (public +
internal)", and an `IntEnum` is not an exception class.
**Assumed:** `ExitCode` lives in `exceptions.py` anyway.
**Why:** the plan states the codes inside § "Exceptions" itself, in the same
section as the hierarchy and immediately after the table mapping error families
to classes — the two are one contract, and the mapping from class to code is
what `cli/main.py` consumes. The alternative, a home in `cli/main.py`, would put
the codes behind the CLI layer, which the plan calls "a thin entry point: no
business logic". *Rejected: a separate `exit_codes.py`, which is the one-concept
module split that § "Exceptions" gives as its reason for consolidating
`OpticaWarning` into `exceptions.py`.*
**Reversible?** Yes — a move plus an import rewrite.

### `utils/prompts.py` added to the plan's `utils/` file list
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/utils/prompts.py`
**Missing:** `CLAUDE.md` § "Settled points" requires that a declined prompt exit
`3`, that `click.Abort` exit `130`, and that `confirm(..., abort=True)` never be
used — and says "this lands in pass 1 and every later command inherits it". The
plan's `utils/` tree lists four modules (`logging`, `system`, `progress`,
`lockfile`) and none of them is a prompt layer.
**Assumed:** a fifth module, `utils/prompts.py`, holding `confirm()` and the
Y/N conventions, including `--yes` resolution per prompt category (choice /
safety / destructive) as plan § "Global flags" splits them.
**Why:** the plan already directs two unplaced things — the `optica.classify.*`
namespace and the two registries — to "be placed when [they are] built", so
placing is a sanctioned move rather than a deviation. Prompts do not belong in
`logging.py`: `--quiet` suppresses logging output and must **not** suppress
prompts (Implementation Note 19), so keeping them in one module would put the
verbosity switch and the thing it must not reach behind one import.
**Reversible?** Yes — the module has one public function and no state.

### `cli/config.py` built in pass 1, minus `--clear-staging`
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/cli/config.py`
**Missing:** no pass owns `cli/config.py`. `notes/passes/pass-1.md` names only
`cli/main.py` and "the `classify` skeleton"; passes 2-6 never mention it.
**Assumed:** built in pass 1 with `--init`, `--set`, `--view` and `--global`,
which need nothing beyond pass 1's own `config/`. **`--clear-staging` is not
registered** — plan § "Configuration" puts its deletion logic in the Input
Manager, which pass 2 builds; the flag arrives with it.
**Why:** pass 1's "Done when" requires that exit code `3` be reachable, and `3`
is a declined prompt. **The only V1 prompt whose backing is entirely pass 1's is
`optica config --init`'s create confirmation** — so without `cli/config.py` the
pass cannot meet its own milestone. Implementation Note 11 points the same way:
`--yes` must reach `optica config` to answer that prompt and must not answer the
destructive overwrite on the same command, and `--yes` is registered globally in
pass 1. *Rejected: a throwaway prompt somewhere in the skeleton purely to make
`3` reachable — it would test the plumbing against a fixture rather than against
the one real prompt the pass can support.*
**Reversible?** Yes. Registering `--clear-staging` in pass 2 is additive; nothing
built here needs revisiting.

### `DEFAULT_TASK` stands in for the unbuilt `TASK_REGISTRY`
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/config/defaults.py:DEFAULT_TASK`, `src/optica/cli/main.py`
**Missing:** plan § "Key Decisions" requires alias resolution to consult
`default_task` rather than hardcoding `classify`, and § "Configuration" fixes
`default_task` as a module-level constant rather than a config key in V1. The
`TASK_REGISTRY` that would map the constant to a command group "[has] no stated
home" and is built in pass 5.
**Assumed:** `DEFAULT_TASK = "classify"` in `config/defaults.py`, and `main.py`
resolves it through a one-entry local mapping from task name to Typer group,
marked in a comment as the seat `TASK_REGISTRY` takes in pass 5.
**Why:** it keeps the indirection the plan asks for — `main.py` holds nothing
classify-specific and never spells `"classify"` as a literal — without building
pass 5's registry a pass early. The registry then replaces the mapping without
touching any call site.
**Reversible?** Yes — that is the point of routing through the constant now.

### Tool configuration added to `pyproject.toml`
**Pass:** 1   **Date:** 2026-09-12   **Where:** `pyproject.toml` `[tool.ruff]`, `[tool.mypy]`
**Missing:** `notes/passes/pass-1.md` has CI run bare `ruff check` and `mypy`.
Neither has a configuration section, and bare `mypy` with no config and no
argument checks nothing.
**Assumed:** added `[tool.ruff]` (target `py311`, `src/` + `tests/`) and
`[tool.mypy]` (`strict`, `files = ["src", "tests"]`, Python 3.11) so both
commands are meaningful as written. `version` untouched.
**Why:** "every pass ends Ruff-clean and mypy-clean" is only a real check if the
tools are told what to look at; a green bare `mypy` that examined no files is the
kind of vacuous pass this build is trying to avoid.
**Reversible?** Yes — configuration only, no source depends on it.

### The lock-file conflict raises `OpticaError` directly
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/utils/lockfile.py:acquire_lock`
**Missing:** Implementation Note 2 specifies the hard block and its exact
message but assigns it no exception class, and the "Every hard error carries a
class" table in § "Exceptions" has no family that covers it. The lock is not an
input-contract violation, not a config value, and not any named subsystem's
contract.
**Assumed:** `OpticaError` is raised directly, with the plan's message split
across the three parts (`message` / `why` / `fix`) that `render_error` prints.
**Why:** the plan sanctions exactly this — *"`OpticaError` is raised directly
only where no subsystem's contract is the one violated, which is a signal the
hierarchy is missing a class rather than a licence to use the base class
routinely"* — and this is that signal, unanswered. The alternative, filing it
under `OpticaValidationError`, would stretch "the input contract" to cover a
concurrency guard and blur the one class the plan deliberately bounds.
*Rejected: adding `OpticaLockError`, which would contradict the flat hierarchy's
exhaustive enumeration in a pass that has no authority to extend it.*
**Recommendation for the post-V1 pass:** `OpticaLockError` is the missing class.
Exit code is unaffected either way — both are `1`.
**Reversible?** Yes — one constructor call and one test.

### Windows PID liveness cannot use `os.kill(pid, 0)`
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/utils/lockfile.py:pid_is_live`
**Missing:** Implementation Note 2 requires distinguishing a live PID from a dead
one and says nothing about how.
**Found:** the POSIX idiom is `os.kill(pid, 0)`, which sends no signal and only
runs the error checks. **On Windows CPython maps `os.kill` onto
`TerminateProcess` for every signal except `CTRL_C_EVENT` and
`CTRL_BREAK_EVENT`,** so the "harmless" probe would kill the process it was
asking about — including, on a PID collision, a process belonging to something
else entirely.
**Assumed:** two implementations selected by `sys.platform` at import: POSIX uses
`os.kill(pid, 0)`; Windows opens a `PROCESS_QUERY_LIMITED_INFORMATION` handle via
`ctypes` and reads `GetExitCodeProcess`, which observes without signalling. The
platform branch is at module level rather than inside the function so that mypy
checks the live branch on each of the three CI runners and skips the other.
**Why:** Windows is a named best-effort target and this is the development
platform, so the wrong idiom here would be exercised constantly and would fail
destructively rather than visibly.
**Known limit, not resolved:** PID reuse. A dead run's PID can be reallocated to
an unrelated process, which would read as a live lock. The lock's stored command
name makes the misreport legible in the error but does not prevent it; the plan's
own note that per-project scoped locks are post-V1 is the place that belongs.
**Reversible?** Yes — one function.

### `--classes` followed by another flag binds that flag as its value
**Pass:** 1   **Date:** 2026-09-12   **Where:** affects `input/` class-name parsing (pass 2)
**Missing:** plan § *Flag (no value) behavior* says `--classes` with no value
surfaces the class-name prompt. It does not say what "no value" means to the
parser.
**Found:** Click takes the **next token** as an option's value whatever it looks
like. `optica fetch --classes --yes` therefore parses cleanly with
`classes == ["--yes"]` and no error at all, so the handler's redirect never
fires. Only a **trailing** `--classes` raises `BadOptionUsage`, which is the case
pass 1's handler covers. Verified in `notes/verified.md` § "Which exception each
parser-error shape actually raises".
**Assumed:** pass 1 handles the trailing case, which is the one the plan
describes. **Handed to pass 2**, which owns the filesystem-safe class-name rules
and is the right place to reject a name that is a flag spelling — a leading `-`
is not a plausible class name, and pass 2 already rejects names on
character-level rules.
**Why not fixed here:** the flag layer sees a syntactically valid value; only
name validation can tell that it is wrong, and name validation is pass 2's.
**Reversible?** Yes — it is one predicate in the name rules.

### `tests/` is a package
**Pass:** 1   **Date:** 2026-09-12   **Where:** `tests/**/__init__.py`
**Missing:** `CLAUDE.md` § "Tests" fixes the layout (`tests/unit/` mirrors the
source tree, `tests/integration/`, `tests/conftest.py`) but not whether the
directories carry `__init__.py`.
**Assumed:** they do.
**Why:** two reasons, both mechanical. `tests/unit/` mirrors `src/optica/`, so
same-named modules in different mirrored directories are guaranteed — a
`tests/unit/utils/test_logging.py` and a future `tests/unit/server/test_routes.py`
are fine, but the mirror makes collisions a matter of time, and without packages
pytest's import mode cannot hold two modules of one name. Second, mypy scopes
per-directory settings by module path, so the `tests.*` override that relaxes
`disallow_untyped_defs` for test signatures has nothing to match without them.
**Reversible?** Yes, but the collision hazard returns with it.

### `.env` is read but never printed
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/config/manager.py:_env_values`
**Missing:** plan § "Configuration" puts `.env` at the env-var tier and
`CLAUDE.md` forbids reading, printing or committing it. The two are in tension
only in appearance: the Config Manager must *load* `.env` for the priority chain
to be correct, and the repo's own `.env` must never be displayed.
**Assumed:** `load_dotenv(path, override=False)` loads the file into the process
environment and nothing reads its text back. The only key it can supply is
`flickr_api_key`, which `--view` masks and `--set` never echoes, so no value from
`.env` can reach the terminal. The repo's `.env` was never opened during this
pass.
**Why:** it is the plan's stated mechanism, and the masking rule is what makes it
safe rather than a promise not to look.
**Reversible?** n/a — this records how the constraint was met.

### A piped answer is not an answer
**Pass:** 1   **Date:** 2026-09-12   **Where:** `src/optica/utils/prompts.py:is_interactive`
**Missing:** the plan says a prompt in a "non-prompting context" raises rather
than blocking, without defining the context.
**Assumed:** stdin not being a terminal. `printf 'n' | optica config --init`
therefore raises the hard error ("Re-run with --yes, or run this in a terminal")
rather than reading `n` — exit `1`, not `3`.
**Why:** the alternative is to let Click read stdin, and Click raises `Abort` for
**both** an interrupt and an EOF, which would return `130` where a
missing-answer is not an interrupt — the same conflation that makes
`confirm(..., abort=True)` banned. The plan also already names the unattended
answers: `--yes` for a non-destructive prompt, a dedicated flag for a destructive
one, and *"must be answered interactively"* for a destructive prompt with no
flag, which is exactly `config --init`'s overwrite case.
**Consequence for testing:** exit `3` is reachable from a real process only with
a terminal, so `tests/integration/test_exit_codes.py` drives the real code path
with `is_interactive` stubbed. The prompt, the decline, the exit code and the
process status are all real; only the terminal check is not.
**Reversible?** Yes — one predicate, though reversing it reintroduces the
EOF-versus-interrupt conflation.

### Pass 1 — closed
**Date:** 2026-09-12
**Built:** 16 files under `src/` — 12 modules plus 4 package `__init__.py`:

| Area | Modules |
|---|---|
| exceptions | `exceptions.py` |
| `utils/` | `logging.py`, `prompts.py`, `system.py`, `progress.py`, `lockfile.py` |
| `config/` | `defaults.py`, `schema.py`, `manager.py` |
| `cli/` | `main.py`, `classify.py`, `config.py` |
| packages | `optica/__init__.py`, `cli/__init__.py`, `config/__init__.py`, `utils/__init__.py` |

Plus `.github/workflows/ci.yml`, the `.gitattributes` extension, `[tool.ruff]`
and `[tool.mypy]` in `pyproject.toml`, and 13 test files (12 test modules and
`conftest.py`) with 6 package markers. **331 tests collected: 306 passing, 25
skipped stubs** — 14 for pass 2, 5 for pass 4, 6 for pass 5.

**Milestone:** *"`pip install -e .` then `optica --version` works with no torch
installed, and each of exit codes 0, 1, 2, 3 and 130 is reachable and covered by
a test stub. The workflow file is valid YAML."* — **met.**
- `pip install -e ".[test]"` into an empty 3.11.9 venv, then
  `optica --version` prints `optica 0.1.1`, exit `0`. `import torch` in the same
  venv still fails, so the check is not vacuous, and a test asserts that.
- All five exit codes are covered twice: as unit tests through the handler, and
  as integration tests reading a **real process's** status
  (`tests/integration/test_exit_codes.py`). `3` is a declined
  `config --init`; `130` is both a `KeyboardInterrupt` and a `typer.Abort` at
  that prompt, which is the distinction `confirm(..., abort=True)` would erase.
- `ci.yml` parses as valid YAML: triggers `push` and `pull_request` with no
  branch filter, three runners, one Python version, and no `optica setup` step.
- Ruff clean, mypy clean (`strict`), on `src/` and `tests/`.

**The global Typer exception handler shipped first**, as the plan's hard
sequencing prerequisite requires — commit `feat(cli): add global Typer exception
handler`, before any other CLI commit.

**Verification done this pass** (all in `notes/verified.md` § "Pass 1"):
Click's restriction of variable-length `nargs` to positional arguments —
**confirmed exactly**, closing the gate item pass 0 handed forward; Typer 0.27.2
vendors Click and does not depend on it; `typer.Typer` has no
`exception_handler()`; the exception class each parser-error shape actually
raises; non-ASCII status glyphs crashing a non-UTF-8 Windows stdout; and the
installed toolchain snapshot.

**Left open:**
- **CI has not run.** `git push` is denied to the agent, so the workflow is
  valid-and-untested. A human pushes `build/v0.2.0` and confirms green on Ubuntu
  before pass 2 starts — the pass's own stated condition.
- `optica config --clear-staging` → **pass 2**, with the Input Manager that owns
  its deletion logic.
- `--classes` followed by another flag binding that flag as its value → **pass
  2**, in the class-name rules.
- `cli/setup.py` and the registries → **pass 5**; `DEFAULT_TASK`'s one-entry
  mapping in `main.py` is `TASK_REGISTRY`'s seat until then.
- `OpticaLockError` as the class the hierarchy is missing → **post-V1 pass**.
- The MPS branch of `utils/system.py` is written but never run: this machine has
  an NVIDIA GPU. The CUDA branch is exercised; the Apple-silicon branch is
  covered only by a stubbed `platform.machine`.

**Entries logged this pass:** 14, of which **12 are assumptions**, 1 is a finding
handed forward, and 1 is a record.

| # | Entry | Kind |
|---|---|---|
| 1 | The global exception handler's mechanism | assumption |
| 2 | `click` is not importable — the vendored class | assumption |
| 3 | ASCII fallback for the four status glyphs | assumption |
| 4 | `ExitCode` placed in `exceptions.py` | assumption |
| 5 | `utils/prompts.py` added to the plan's `utils/` list | assumption |
| 6 | `cli/config.py` built in pass 1, minus `--clear-staging` | assumption |
| 7 | `DEFAULT_TASK` stands in for `TASK_REGISTRY` | assumption |
| 8 | Tool configuration added to `pyproject.toml` | assumption |
| 9 | The lock-file conflict raises `OpticaError` directly | assumption |
| 10 | Windows PID liveness cannot use `os.kill(pid, 0)` | assumption |
| 11 | `--classes` followed by another flag binds that flag | **finding → pass 2** |
| 12 | `tests/` is a package | assumption |
| 13 | `.env` is read but never printed | record |
| 14 | A piped answer is not an answer | assumption |

12 + 1 + 1 = 14.

**Next:** pass 2 — `input/` except `clip.py`. Read `notes/verified.md` first:
task 3 settled the Open Images column schema, and the Click `nargs` entry settles
how `-c` values arrive.

## Pass 1 — CI repair

The first CI run failed at the `pytest` step on all three runners. Four failures
on Ubuntu; the entries below are the whole set, with the other two runners'
behaviour reasoned from them. The pass's milestone was therefore not met when it
was reported met, and these fixes are pass 1 work inside pass 1 scope.

**What this run proved that the local one could not.** Every one of the four is a
thing the development machine cannot see: a Linux `os.kill`, a temp path of a
different length, and an interpreter outside a venv. `CLAUDE.md` says CI on
Ubuntu is the only Linux check there is; three of these four are the reason that
sentence exists.

### `pid_is_live` raised on an out-of-range PID — a source bug, not a test bug
**Pass:** 1   **Date:** 2026-09-13   **Where:** `src/optica/utils/lockfile.py:pid_is_live`
**Found:** `os.kill` takes a signed 32-bit `pid_t`, so `os.kill(4_000_000_000, 0)`
raises `OverflowError` **before any error check runs**. It escaped as a raw
traceback, which plan § "Coding Style" forbids unconditionally. The test that
caught it was written as "above any plausible allocation on either platform" —
it was testing the guard that did not exist.
**Reach is wider than the test:** the lock file is plain JSON that a user can
hand-edit and a crash can truncate, so `read_lock`'s `int(raw["pid"])` can
produce any integer at all. The same input reached `acquire_lock`, so a
malformed lock file would have crashed every write command with a traceback and
no way to recover but to find and delete a file whose path the error never
printed.
**The Windows branch has the same bug at a different threshold.** Measured on the
build machine: `OpenProcess` returns a null handle for `4_000_000_000`, `2**31`
and `2**32 - 1` — no error — and raises
`ArgumentError: OverflowError: int too long to convert` from `2**32` upward,
because ctypes converts the PID to a 32-bit `DWORD`. So Windows passed the
failing test locally and in CI while carrying the identical defect one binary
order of magnitude further out.
**Fixed:** a shared `_is_plausible_pid` guard against `_MAX_PID`, which is the
platform's own ceiling — `2**32 - 1` on Windows, `2**31 - 1` on POSIX. An
out-of-range PID answers `False`: it is not a process that ended, it is a number
that was never a PID, and both readings lead to the same disposition, so the
stale-lock path already handles it correctly.
**Also fixed, found while reading the same lines:** the Windows branch let ctypes
*infer* its signatures, which truncates the returned `HANDLE` to 32 bits on
64-bit Windows. `argtypes` and `restype` are now declared. This was silent and
would have stayed silent.
**Reversible?** Yes, but the guard is not optional — removing it restores a
crash on reachable input.

### `optica config --set` printed a path broken mid-token
**Pass:** 1   **Date:** 2026-09-13   **Where:** `src/optica/utils/logging.py`
**Found:** Rich word-wraps at an assumed 79 columns whenever the stream is not a
terminal — a pipe, a redirect, a CI log — and *folds* a token longer than the
remaining width by inserting a newline inside it. On Ubuntu that split
`config.toml` across two lines in `--set`'s output.
**Treated as the defect rather than as a strict assertion.** A path broken
mid-token is not copyable, and this is the one line whose whole purpose is to
tell the user which file was written — plan § "Configuration" requires the path
be reported "so it is never a file the user did not know appeared", which a
broken path only half does. The same fold would break the plan's
copy-paste-ready corrected command.
**Fixed:** `soft_wrap=True` on both consoles, set once at construction rather
than per call site. The line is emitted whole and the terminal wraps it for
display, so nothing is broken mid-token at any width.
**The test was also flaky by construction, which is why it fired on one runner
and not the others.** Whether the fold lands inside `config.toml` depends on the
exact length of the temp path, and that differs per runner and per run. Measured
for the plausible roots: Ubuntu's 106-character line folds mid-token; macOS's
136 and Windows's 117-146 do not. So the *same* defect passed on two runners.
A length-independent regression test now asserts the property directly, at five
path depths and on both streams.
**Reversible?** Yes — one constructor argument each.

### Two `TestVenv` tests asserted an ambient fact, not the code
**Pass:** 1   **Date:** 2026-09-13   **Where:** `tests/unit/utils/test_system.py`
**Found:** `test_the_test_run_is_inside_a_venv` and
`test_venv_path_prefers_the_executing_prefix` both assumed the test run was
inside a virtual environment. It is not, on any runner:
`actions/setup-python` installs into the hosted toolcache, and `pip install -e .`
goes there. Both tests were asserting a property of the machine.
**Not fixed by changing `ci.yml`.** The workflow matches what
`notes/passes/pass-1.md` specifies, and adding a venv step would make the tests
pass by rearranging the world around them — while leaving both branches of the
resolution logic still untested. The tests were what was wrong.
**Fixed:** both reframed to stub `sys.prefix`, `sys.base_prefix` and
`VIRTUAL_ENV`, so each branch is reachable and deterministic on every runner.
Nine tests now cover: differing prefixes, equal prefixes, a stale `VIRTUAL_ENV`
alone, the path inside and outside a venv, the declared path, the mismatch, and
CI's own no-venv state.

### `running_in_venv()` and `venv_path()` disagreed with each other
**Pass:** 1   **Date:** 2026-09-13   **Where:** `src/optica/utils/system.py`
**Found:** while answering "does anything under `src/` behave differently when
`running_in_venv()` is False". Nothing does — **no module outside `system.py`
reads it; it is reported, never branched on** — but the two functions disagreed.
`running_in_venv()` returned True for `sys.prefix != sys.base_prefix` **or** a
set `VIRTUAL_ENV`, while `venv_path()` preferred the prefix and fell back to the
variable. So a shell carrying a stale `VIRTUAL_ENV` over the system interpreter
reported "in a venv" and returned the wrong path — and that combination is
exactly the condition plan § "`optica setup`" makes a hard error: an active
environment Optica is not running from.
**Fixed:** `running_in_venv()` is the prefixes alone. `venv_path()` returns the
executing prefix or None. A new `declared_venv()` returns `VIRTUAL_ENV`, and
`SystemInfo` carries both, so the mismatch stays visible to the caller that has
to report it instead of being resolved silently into one value.
**For pass 5:** **CI runs outside a venv on all three runners.** That is now a
known, tested state rather than an assumption, and `optica setup --ci` will meet
it — `--ci` is config-init only, with no environment detection, so it must not
consult any of these. Setup's other paths must treat "no venv" as a supported
state and the venv/declared mismatch as the hard error the plan names.
**Reversible?** Yes, but reversing reinstates the disagreement.

### `tests/unit/` did not mirror the source tree, and nothing checked
**Pass:** 1   **Date:** 2026-09-13   **Where:** `tests/unit/`
**Found:** `config/schema.py` (251 lines, all the validation) and
`cli/__init__.py` (136 lines, holding `split_values`) had no test file.
`split_values` is the implementation of the comma value-separator convention
this pass verified against Click's real behaviour — the module least entitled to
be the untested one. Both were exercised only indirectly, through
`test_manager.py` and `test_classify.py`, so a failure could not say which layer
broke.
**Fixed:** `tests/unit/config/test_schema.py` (46 tests) and
`tests/unit/cli/test_init.py` (34 tests) added; `tests/unit/test_init.py` and
`tests/unit/config/test_init.py` added for the two package modules that carry a
public surface. `TestSplitValues` moved out of `test_classify.py` and
`TestGlobalState` out of `test_main.py`, so each lives in the file mirroring its
module rather than in two places free to drift.
**And the rule is now checked rather than remembered:** `tests/unit/test_tree.py`
asserts that every module under `src/optica/` has a mirroring test file. A module
that genuinely holds no code is named in an explicit `_NO_LOGIC` allowlist — one
entry, `utils/__init__.py` — so skipping one is a deliberate, visible act. Two
further tests keep the allowlist honest: one fails if an exempt module grows
code, one fails if a listed module is deleted or renamed. The check was verified
to bite by removing `test_schema.py` and watching it fail.
**Why a test rather than a habit:** the gap was found by a human reading the
tree. `CLAUDE.md` states the mirror rule, and a rule stated in prose is checked
only when someone remembers to look.

### `split_values` and `GlobalState` were placed in `cli/__init__.py` unlogged
**Pass:** 1   **Date:** 2026-09-13   **Where:** `src/optica/cli/__init__.py`
**Missing:** the plan's `cli/` tree names `main.py`, `classify.py`, `config.py`
and `setup.py`. It gives no home for state shared between them, nor for the
value-separator helper that `classify.py` and pass 5's `setup.py`
(`--include-extras`) both need.
**Assumed:** both live in the package's `__init__.py`.
**Why:** `main.py` must import `classify.py` to register the group, and
`classify.py` must read the shared state, so defining the state in `main.py`
makes that a circular import. `__init__.py` is upstream of both and adds no file
to the plan's tree. `main.py` re-exports `GlobalState` and `get_state`, so no
caller needs to know where they live. *Rejected: a new `cli/state.py`, which is
more discoverable but is a second deviation from the tree on top of
`utils/prompts.py`; and a late import at the bottom of `main.py`, which works
only if `main` is imported before `classify` and fails silently otherwise.*
**This should have been logged when it was made.** It is the same class of
decision as `ExitCode` going in `exceptions.py` and `utils/prompts.py` being
added, both of which got entries in this file on the same day. The omission is
the one the gap rule exists to prevent — *"the decision is never silent"* — and
it was silent for a day.
**Reversible?** Yes — a move plus an import rewrite, with `main.py`'s re-exports
absorbing most call sites.

### Pass 1 — closed (corrected)
**Date:** 2026-09-13
**Corrects:** *"Pass 1 — closed"*, above, dated 2026-09-12 (this file is
append-only, so that entry stands as written and this one overrides it).

**What was wrong:** that entry reported the milestone **met**. It was not. CI
failed at the `pytest` step on all three runners on the first push — four
failures on Ubuntu, of which three were defects in shipped code or in what the
tests actually assert, and one a real source bug that escaped as a raw traceback.
The claim was made on the strength of a green local run, which is exactly the
check `CLAUDE.md` says cannot stand in for the Linux one: *"CI on Ubuntu is
therefore the only Linux check there is."*

**The deeper error is the same one this repo already has six recorded instances
of** — a document checked against itself. A milestone reading *"the workflow
file is valid YAML; the human pushes and confirms it runs green on Ubuntu before
pass 2 starts"* has two halves, and only the first was verifiable here. Reporting
"met" collapsed them. The correct report was *"the half I can check is met; the
half I cannot is pending."* The earlier `notes/verified.md` § task 4 correction
records the same lesson in the same words: **do not write a pass's outcome in
past tense before the command has run.**

**Fixed since:** four failures, in five commits — `fix(lockfile)`,
`fix(logging)`, `fix(system)`, `test(unit)`, `docs(build-log)`. Each is written
up above.

**Failure attribution across the three runners.** Ubuntu's four are observed;
the other two are reasoned from them and from measurements on the build machine,
and are predictions to be confirmed against the next run.

| Failure | Ubuntu | macOS | Windows |
|---|---|---|---|
| `pid_is_live` `OverflowError` at 4e9 | **fail** (observed) | **fail** — POSIX, same signed 32-bit `pid_t` | **pass** — ctypes returns a null handle below `2**32`, so the defect is present but out of reach of this input |
| path folded mid-token | **fail** (observed) | **pass** — the 79-column fold lands elsewhere in a longer line | **pass** — same |
| `test_the_test_run_is_inside_a_venv` | **fail** | **fail** — toolcache, no venv | **fail** — toolcache, no venv |
| `test_venv_path_prefers_the_executing_prefix` | **fail** | **fail** | **fail** |
| **Total** | **4** (observed) | **3** (predicted) | **2** (predicted) |

**The fold row is length-dependent, so treat those two cells as the soft ones.**
Whether the fold lands inside `config.toml` depends on the exact character
length of the temp path, which differs per runner. Modelled: Ubuntu 106
characters folds mid-token; macOS ~136 and Windows ~117-146 do not. The runner
temp roots were modelled rather than observed, so if either differs from the
model that row flips and the totals become macOS 4, Windows 3.

**Milestone, restated honestly:**
- `pip install -e .` then `optica --version` with no torch — **met**, checked
  locally, and now checked on every runner by `ci.yml`'s last step.
- Exit codes 0, 1, 2, 3, 130 reachable and covered — **met**.
- Workflow file is valid YAML — **met**.
- CI green on Ubuntu — **pending the next run.** Not claimable from here.

**State now:** **457 tests collected — 431 passing, 26 skipped.** The 26 are 25
forward stubs (14 pass 2, 5 pass 4, 6 pass 5) plus the one `_NO_LOGIC` exemption
in `test_tree.py`; 14 + 5 + 6 + 1 = 26, and 431 + 26 = 457. Up from 331 collected
at the first close: +80 for the two missing mirrors, +34 for `cli/__init__.py`,
+12 for the no-fold regression tests, and the rest for the out-of-range PID
cases and the reframed venv branches. Ruff clean, mypy clean under `strict`.
Source is unchanged at 16 files; tests are 17 files plus `conftest.py`, from 12.

No `skipif` and no platform-conditional collection, so **all three runners should
report the same 431 passed, 26 skipped.** A difference between runners is itself
a finding.

**Handed to pass 5, newly:** CI runs **outside a virtual environment** on all
three runners. `optica setup --ci` will meet that state, and setup's environment
resolution must treat it as supported rather than as the "no venv found" hard
error — `--ci` does no environment detection at all, so the two must not share a
code path.

**Next:** unchanged — pass 2, `input/` except `clip.py`, once CI is green.

### CI actions bumped to the Node 24 majors — a human edit between passes 1 and 2
**Pass:** between 1 and 2   **Date:** 2026-09-13   **Where:** `.github/workflows/ci.yml`; affects pass 6
**Found:** the pass 1 workflow pinned `actions/checkout@v4` and
`actions/setup-python@v5`. Both target Node 20, which GitHub's runners began
forcing onto Node 24 on 16 June 2026 and remove entirely on **23 September
2026** (github.blog changelog `2025-09-19-deprecation-of-node-20-on-github-actions-runners`,
editor's note of 25 August 2026). All three legs were green but emitted the
deprecation warning on every run.
**Action taken:** bumped to `actions/checkout@v6` and `actions/setup-python@v6`,
both of which ship on Node 24. Committed and pushed by the human between passes;
no agent involved. CI green on all three runners, warning gone.
**Consequence for pass 6:** `notes/passes/pass-6.md` says to **extend** the
minimal workflow from pass 1. The workflow you will find is not byte-identical
to the one pass 1 committed — the action versions above are newer, deliberately,
and must not be reverted. Extend from what is in the file, not from what pass 1's
diff shows. `pass-6.md` is not corrected: derived artifact, log-only, per the
same rule applied to `pass-4.md` and `pass-0.md` in pass 0.
**Reversible?** Yes, but do not — reverting reintroduces a runtime removed from
the runners.

### Plan amendment session — the eleven open items decided
**Pass:** between 1 and 2   **Date:** 2026-09-13   **Where:** `spec/optica-plan-v1-core.md`
**What this is:** the outcome of the out-of-repo plan-amendment session, recorded
here so a later pass reading the eleven proposals above can tell which landed.
The `spec/` edits were applied by the user, not by an agent.

| # | Item | Disposition | Sites |
|---|---|---|---|
| 1 | `Thumbnail300KURL` fallback condition | **Amended** | l.759 |
| 2 | "~100KB label-mapping file" | **Amended** — figure deleted | l.759, l.1527 |
| 3 | `app.exception_handler()` | **Amended** — API name dropped | l.220, l.1618 |
| 4 | `typer._click` under a `<1.0` bound | **Declined** | — |
| 5 | "`MissingParameter` on `--classes`" | **Declined** | — |
| 6 | `--classes --yes` binds `--yes` | **Amended** — at the class-name rules | l.242 |
| 7 | `OpticaLockError` | **Deferred** — post-V1 | — |
| 8 | "~3GB" torch download | **Declined** — no such figure in the plan | — |
| 9 | `EXTRAS_REGISTRY` `size_estimate` | **Amended** | l.420–422, l.443, l.450, l.484, l.488, l.492 |
| 10 | mobilenet "Last 3 InvertedResidual blocks" | **Amended** — word deleted | l.1063 |
| 11 | `bn2` unlisted for the efficientnets | **Amended** | l.1060, l.1061 |

**Item 2, second half — pass 2 owns it.** Deleting the figure removes the false
constraint; the plan stays silent on how a class maps to image URLs. Pass 2
chooses between streaming the 608.8 MiB image-metadata CSV, range-querying it,
using per-class annotation files, or caching a derived index, and logs the
choice here. If the chosen path involves a large first-use download, l.855's
open-clip precedent (inform the user, show a progress indicator) is the shape to
follow. Sizes in `notes/verified.md` § task 3.

**Item 5 — pass 2 must route both shapes.** `--classes` absent entirely raises
`MissingParameter`; a trailing `--classes` raises `BadOptionUsage`. The base
catch reaches both; the redirect to the class-name prompt must not key on one
class. Table in `notes/verified.md` § "Which exception each parser-error shape
actually raises".

**Item 6 — what changed for pass 2.** l.242 now excludes a leading `-` from
class names, so `optica fetch --classes --yes` (which parses cleanly with
`classes == ["--yes"]`) fails name validation with the standard hard error
rather than creating a folder called `--yes`.

**Item 8 — correction to the record.** `notes/verified.md` § task 2,
consequence 1 states "the plan's ~3GB figure is high". **The plan contains no
~3GB figure**, in any spelling or unit — searched every `GB`, `MB`, `GiB`,
`gigabyte` and `disk` token across all 1781 lines. The plan's `torch-gpu` figure
was `~2GB`, which the same measurement calls slightly low. The `~3GB` figure
most likely originates in `notes/passes/pass-0.md`'s task 2 brief, which was not
available to the amendment session. Pass 5 should not look for one in the plan.

**Item 9 — what pass 5 inherits.** The registry now reads `torch-cpu`
`~250MB`, `torch-gpu` `~2–2.5GB`, `torch-auto` `~250MB–2.5GB`, and the worked
examples and their total were updated with it. The `2.5GB` top is deliberate
headroom; the highest figure measured is 2.40 GB (`notes/verified.md` § task 2).

**Item 11 — one thing handed to pass 4 rather than amended.**
`mobilenetv3_large_100`'s `conv_head` and `norm_head` sit *after* `global_pool`
(module order in `notes/verified.md` § task 4), so they belong to the classifier
stack rather than the feature extractor, and l.1063 unfreezes neither. This may
be correct — efficientnet's pre-pool `conv_head` is not the same case — but the
plan does not say whether the asymmetry is intended. Pass 4 decides and logs it.

**Item 7 — deliberately not in the plan.** `OpticaLockError` stays post-V1;
l.1560 sanctions the bare `OpticaError` raise and names it the signal. Whoever
adds the class must also edit l.1560, which currently says `OpticaCLIPLoadError`
is the one class the subsystem rule does not reach.

### `notes/verified.md` § task 2 misattributed the "~3GB" figure to the plan
**Pass:** between 1 and 2   **Date:** 2026-09-13   **Where:** `notes/verified.md` § task 2, Consequences item 1
**Found:** the entry read "the plan's ~3GB figure is high". The plan contains no
such figure — searched across all 1781 lines for every `GB`, `MB`, `GiB`,
`gigabyte` and `disk` token during the plan amendment session. The figure
originates in `notes/passes/pass-0.md` line 63. The plan's own `torch-gpu`
estimate was `~2GB`, which the same measurement calls slightly low.
**Action taken:** corrected in place by the human between passes.
`notes/verified.md` is not append-only, so unlike this file it is corrected
rather than superseded. The measurement (2.40 GB Linux, 2.08 GB Windows) was
always correct and is unchanged; only the attribution moved.
**Why it is recorded here:** a pass may not retro-edit an earlier pass's
entries. This was a human edit between passes, and this entry is the audit
trail for it.
**Consequence:** amendment item 8 was **declined** on exactly this ground — see
`optica-plan-amendment-change-record-2026-09-13.md`. Nothing in the plan needed
changing. `pass-0.md` is not corrected: derived artifact, pass closed, log-only.

### `CLAUDE.md`'s transitive-Click premise was false
**Pass:** between 1 and 2   **Date:** 2026-09-13   **Where:** `CLAUDE.md` § "Settled points that the plan leaves implicit"
**Found:** the file read "They arrive transitively through `typer` and
`pydantic-settings`, and the plan says so deliberately and twice." Pass 1
established that Typer 0.27.2 vendors Click as the private `typer._click` and
declares no dependency on it, so `import click` fails in a Core install. The
`pydantic` half is true: `pip show pydantic` on 2026-09-13 reports
`Required-by: pydantic-settings`.
**Action taken:** corrected in place by the human between passes. Unlike
`notes/passes/pass-N.md`, `CLAUDE.md` is standing instruction read
automatically by every remaining pass, so a false premise there is live rather
than historical. `CLAUDE.md` § "Verify external facts before code depends on
them" applies to `CLAUDE.md` itself.
**Why it mattered operationally:** passes 2, 3 and 5 all write CLI-adjacent
tests. An agent believing Click is importable would reach for
`click.testing.CliRunner` and hit a `ModuleNotFoundError` with no reason to
expect it. The replacement names the `typer` equivalents directly.
**Also removed:** the clause "and the plan says so deliberately and twice."
Pass 0 verified the plan declares neither package; nobody verified that the
plan asserts transitivity, and the plan amendment session read the file across
eleven items without surfacing such a claim. An unverified assertion does not
belong in a correction to an unverified assertion.
**The instruction is unchanged.** Core stays at exactly six packages, and the
reason for excluding Click is now stronger than the one originally given:
adding it installs a second `UsageError` class alongside the vendored one, and
every `except` silently stops firing.

---

## Pass 2

**Read at start:** this file in full (including the four between-pass entries),
`notes/verified.md`, `notes/passes/pass-2.md`, and the plan as amended on
2026-09-13 — §§ "Input & Acquisition" in full, "CLI Layer & Conventions",
"Configuration", "Labeling & Curation" (staging and session shapes),
"Exceptions", "Python API" (result and prompt rules), "Implementation Notes",
"Known Constraints" and the flag reference. Amended l.242, l.759 and l.1527 were
read as they stand now.

### Open Images image-URL acquisition strategy
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/openimages.py`, used by `input/fetch.py`
**Missing:** the plan (l.759, as amended) says the label mapping and metadata
come from GCS and that the label map is cached and verified, and deliberately
names neither the file nor how a class reaches its image URLs. Handed to this
pass by the amendment session's item 2.
**Measured first** (all in `notes/verified.md` § "Open Images — which files map
a class to image URLs"): the metadata CSVs have **no label column**, so a label
file must be joined in; the V7 train label file (2,609.1 MiB) is **sorted by
`ImageID`** and range-addressable, while the V6 metadata file (2,560.3 MiB) is
**in no order**; positive density varies ~50× along the label file; ~18% of
thumbnail URLs are dead; GCS returns an MD5 for every object.

**The four candidates, and what happened to each:**

| Candidate | Verdict | Why |
|---|---|---|
| Stream the metadata CSV | **Rejected as the whole strategy** | Alone it cannot answer "which images are cats" — it has no labels. Streamed together with the label file, every fetch reads up to 5.2 GiB. |
| Range-query it | **Adopted for the label file only** | The label file is sorted, so any byte window is a clean sample of the ID space. The metadata file is not sorted, so no search over its ranges exists. |
| Per-class annotation files | **Rejected — they do not exist** | None of the 83 files linked from `download_v7.html` is per class. |
| Cache a derived index | **Adopted per class, not globally** | A global index means a 5.2 GiB first download before the first fetch and hundreds of MiB on disk; the 600-class boxable variant (~1 GiB) lacks `Golden retriever`, `Pug` and `Tulip`. Per class, the cache holds only what a fetch for that class already found. |

**Assumed — the strategy built:**
1. **Vocabulary:** `v7/oidv7-class-descriptions.csv` (20,931 classes), cached at
   `~/.optica/openimages/`, with the GCS `x-goog-hash` MD5 stored beside it and
   **checked on every load**; a mismatch deletes and re-downloads it with a
   status line (Implementation Note 13). Class names match display names
   case-insensitively, with `_` read as a space (`golden_retriever` →
   `Golden retriever`). An unknown name is a hard error listing every unknown
   name with close matches — before any prompt, confirmation or download.
2. **Candidates — striped range reads over the V7 train human-verified label
   file.** The file is cut into 64 equal stripes read 1 MiB at a time,
   round-robin, keeping `Confidence == 1` rows for the requested MIDs. Stripes
   exist because density is position-dependent: reading from byte 0 would
   sample the file's sparsest region first. All requested classes share one
   pass.
3. **URLs — a streamed join over the V6 metadata file** (which covers the V7
   train label images, Result 7), matching the first 16 bytes of each line
   against the unresolved candidate IDs and parsing only the hits. Stops once
   every class has enough, so the file is rarely read to the end.
4. **Balancing the two reads.** Reading more labels makes the metadata join
   faster, and vice versa. With `n` URLs needed and a class's estimated positive
   count `P` (from the first round of stripes), the positive target is
   `s = min(P, max(4n, √(n·P·M/L)))`, which minimises total bytes for sizes
   `L` (labels) and `M` (metadata).
5. **Per-class cache** in `~/.optica/openimages/classes/`: the stripe cursors,
   positives found, URLs resolved, and the metadata cursor, keyed to the two
   files' ETags — an ETag change discards it. A later fetch of the same class
   (fetch more, resume, the imbalance prompt's F) continues from the cursors
   instead of starting again.
6. **Fill to target (l.759)** draws resolved candidates; when they run out it
   extends the search (2 → 3 → 4) and draws again. The pool is exhausted only
   when every stripe is read and every positive's URL has been looked for.
7. **Informing the user** follows l.855's open-clip precedent: the first
   label-map download is announced, and the candidate search shows progress in
   bytes read.

**What it costs — computed, not measured end to end.** From
`s = min(P, max(4n, √(n·P·M/L)))` with `L` = 2,609.1 MiB, `M` = 2,560.3 MiB,
`n` = 75 (the default 50 per class × 1.5 slack for dead URLs), and `P` from
`notes/verified.md` Result 6:

| Class | P (est.) | s | Labels read | Metadata read | Total |
|---|---|---|---|---|---|
| Cat | ~69,600 | 2,263 | 84.8 MiB | 84.8 MiB | 169.7 MiB |
| Golden retriever | ~4,460 | 573 | 335.2 MiB | 335.2 MiB | 670.3 MiB |
| Pug | ~2,280 | 410 | 468.8 MiB | 468.8 MiB | 937.5 MiB |
| Hamster | ~840 | 300 | 931.8 MiB | 640.1 MiB | 1,571.9 MiB |
| Screwdriver | ~100 | 100 | 2,609.1 MiB | 1,920.3 MiB | 4,529.3 MiB |

Each total is its two cells summed from unrounded values, so a displayed pair
can differ from its total by 0.1 MiB (Cat: 84.8 + 84.8 shown, 169.7 exact).
Recomputed with `python -c` from the formula after a first draft of this table
carried four cells rounded from a truncated `s`. Classes fetched together share the label
read, so a fetch costs about its rarest class. **These are model figures:**
the stripe reads round up to whole 1 MiB chunks, and `P` comes from a 4.91%
sample, which for `Screwdriver` is five rows — that row is an order of magnitude,
nothing finer.

**Why this over the alternatives:** it is the only one of the four that needs
no multi-GiB step before a common class can fetch, keeps nothing on disk beyond
what a class's own fetch found, and serves the full 20,931-class vocabulary.
**What it gives up:** a rare class is expensive — reading ~4.5 GiB to fetch
`Screwdriver` is a genuine cost, and the design makes it visible (progress in
bytes) and pays it once per class rather than hiding it. A future global index
would make that constant; it is recorded here as the alternative to revisit if
rare-class fetches turn out to be common.
**Reversible?** Yes. The strategy sits behind one class,
`OpenImagesIndex`, whose only contract with `fetch.py` is "yield candidate URLs
for this class, extending on request". A global index replaces it without
touching the fetch loop, staging, or validation.
**Checked live, 2026-09-13**, from `.smoke/pass2-index/` with a scratch home:
`ensure` for Cat and Dog needing 5 URLs each read **64.0 MiB of labels** (65
requests: 1 probe + 64 stripe chunks) and **13.4 MiB of metadata** (2 requests:
probe + one stream), found 1,345 and 2,231 candidates, resolved 5 and 7 URLs,
in 72.3 s. One resolved Dog row had an empty `Thumbnail300KURL` and fell back
to its `OriginalURL` — the amended per-row rule, exercised against real data.

### Two modules added to the plan's `input/` tree
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/classes.py`, `src/optica/input/openimages.py`
**Missing:** plan § "Code Structure" lists `local.py`, `fetch.py`,
`curation.py`, `clip.py`, `validation.py`, `manager.py`, `sessions.py` under
`input/`. It gives no home for the class-name rules and blocklist, and none for
Open Images' class list and index.
**Assumed:** `classes.py` holds both class-name rules, class-count validation,
the blocklist and the auto-mode class sequence; `openimages.py` holds the label
map and the candidate index.
**Why:** the class-name rules are used by `-c`, manifests (`local.py`) and the
blocklist flow alike, so putting them in any one consumer makes the others
import sideways. `openimages.py` is ~700 lines of one concern; in `fetch.py` it
would bury the registry and the fill-to-target loop the plan names as that
file's discipline. The same sanctioned "placed when built" move pass 1 used for
`utils/prompts.py`.
**Reversible?** Yes — moves plus import rewrites.

### `input/__init__.py` added to `test_tree.py`'s `_NO_LOGIC` allowlist
**Pass:** 2   **Date:** 2026-09-13   **Where:** `tests/unit/test_tree.py`
**Assumed:** exempt. It holds a docstring and `from __future__ import
annotations` only; `test_the_exemptions_are_still_empty` fails if it grows code.
**Why:** same shape as the existing `utils/__init__.py` entry; nothing to assert.

### Blocklist matching: whole name, patterns, and extended terms
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/classes.py:is_blocklisted`
**Missing:** the plan names categories and a seed list, not a matching rule.
**Assumed:** case-insensitive match on the **whole** name with `_`/`-` read as
spaces; patterns for negation (`not`/`non`/`no` as a leading word), placeholders
(`class_a`, `label_1`, also `category`/`group`/`type`), and single characters or
lone numbers; 22 extension terms inside the named categories (`others`, `etc`,
`stuff`, `ok`, `true`, `custom`, …). `bad_apple`, `notebook`, `classroom` pass.
**Why:** substring matching would blocklist `notebook` and `goodyear`; the plan
itself expects false positives only of the `positive`/`negative` kind.
**Reversible?** Yes — one frozenset and three regexes.

### Sub-term image counts apply whether grouped or separated
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/classes.py:_build`
**Missing:** plan § *Undefinable classes* puts "image count per sub-term" after
group-or-separate unconditionally, but its explanation ("images_per_class
becomes a per-sub-term floor rather than a group total") speaks only of the
grouped case.
**Assumed:** `max(10, images_per_class // n)` per sub-term in **both** cases.
**Why:** the sequence as written applies it to both; reading it as group-only
would add a condition the plan does not state. *Consequence to watch:*
separated sub-terms fetch fewer images than ordinary classes in the same run,
which the imbalance warning then reports.
**Reversible?** Yes — one branch.

### An overlap between a top-level name and a sub-term re-opens the definition
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/classes.py:_reopen`
**Missing:** the plan says N re-opens "the step that produced the overlapping
names" — definition prompt for a sub-term, class-list prompt for a top-level
name — and does not say what a pair of one of each re-opens.
**Assumed:** only the sub-term's definition prompt, keeping group-or-separate.
Two top-level names re-open the class list.
**Why:** the sub-term is the later answer; re-opening both would ask the user
to redo a class list that was not the problem. **Reversible?** Yes.

### Header-only pre-flight does not see a JPEG cut in half — finding for passes 3 and 4
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/validation.py:inspect_in_place`
**Found:** measured with Pillow 12.3.0: `Image.verify()` passes a JPEG
truncated to half its bytes; only `load()` raises `image file is truncated`. A
truncated PNG *is* caught by `verify()`. The plan specifies header validation
for pre-flight ("headers validated rather than fully decoded, which is cheap").
**Assumed:** the plan's header check for files the user owns, as specified. On
every path where Optica owns the bytes (`process_owned` — fetch writes, copies
into `dataset/`) the image is fully decoded anyway, so truncation is caught
there.
**Consequence:** a truncated JPEG in a `--dataset` read in place, or in a
`--folder` before labeling, passes pre-flight. Pass 3 will see it as a
thumbnail that fails to render; pass 4 as a decode error at training time.
Recorded here so neither is surprised. A test pins the measured behaviour.

### Proposed plan change — class-name rule 1 misses trailing dots, trailing spaces and control characters
**Pass:** 2   **Date:** 2026-09-13   **Where:** plan § *Class-name rules*, l.242; `src/optica/input/classes.py`
**Found:** Windows silently strips a trailing `.` or space from a folder name,
so `cat.` and `cat` are one folder there — the collision rule 2 exists to
prevent, reached by a route rule 1 does not close. Windows also rejects
characters 0–31 in names. The plan's rule lists neither. Trailing spaces cannot
arrive from `-c` (values are trimmed) but can from a manifest.
**Not implemented:** the plan enumerates the rule, and adding clauses to it is an
edit to the specification by other means. Nothing is built on the gap.
**Proposed wording:** add "must not end with `.` or a space, and must contain no
control characters (U+0000–U+001F)" to rule 1.
**Reversible?** Trivially — two predicates in `class_name_problem`.

### Auto-fetch staging carries a hidden `.fetch.json` per class
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/fetch.py:fetch_class`
**Missing:** plan § *Staging shapes* says auto-fetch staging's "shape is the
directory layout itself". It does not say how a resumed fetch, or a
Fetch-More, avoids downloading the candidates it already tried.
**Assumed:** a hidden `.fetch.json` in the class directory records, per source
and per query, the candidate keys tried and the images delivered (the second is
what grouped classes need, since their files do not say which sub-term they
came from). Hidden, so curation's image listing never sees it; inside the class
directory, so `--clear-staging` and "Start fresh" delete it with the images.
**Why:** without it, "fetch 10 more" re-downloads the first 50 candidates to get
past them — and since Open Images thumbnails are regenerated per request, MD5
would not even recognise them, putting the plan's accepted duplicate gap on the
normal path instead of the rare one.
*Rejected: keeping tried keys in the per-class Open Images cache, which would
survive "Start fresh" and make a fresh start never offer the first images again.*
**Reversible?** Yes — delete the sidecar and the loop retries from the top.

### Fetched images are deduplicated at the write into staging
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/fetch.py:fetch_class`
**Missing:** MD5 deduplication "runs once classes are assigned"; on the fetch
path the class is known at download time.
**Assumed:** a byte-identical download is not written, and does not count
toward the target.
**Why:** the placement rule allows it (the class is assigned), and "fills to
target" means valid images — counting a duplicate toward the target and
removing it later would deliver a shortfall the fetch could have filled.
**Reversible?** Yes.

### Fetch loop parameters
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/fetch.py`
**Missing:** the plan fixes none of these.
**Assumed:**
- Candidates requested per image wanted: **1.5×**, from the measured 18% dead
  rate plus validation rejects.
- A dead `Thumbnail300KURL` is **not** retried as `OriginalURL`. The plan's
  fallback is conditioned on the value being empty, and originals average
  multiple MB.
- Downloads: 403/404/410 dead at once; 429/5xx/transport errors retried 3× with
  backoff, then dead; bodies over 30 MB abandoned.
- Flickr: `sort=relevance`, `safe_search=1`, `content_types=0`, `media=photos`,
  `extras=url_z,url_c,url_m` (640px preferred), no licence filter, 1 s between
  API calls (3,600/h evenly spent), 429 honours `Retry-After`, codes 10/105
  retried.
**Why:** each is the conservative reading of a verified fact; none changes a
user-visible contract. **The Flickr adapter is written but never exercised end
to end** — no key exists (`.env` is empty; Flickr keys need Pro) — and belongs
beside pass 1's MPS branch on the list of code not to mistake for tested.
**Reversible?** Yes — constants at the top of `fetch.py`.

### A reserved device name is refused with any extension
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/classes.py:class_name_problem`
**Missing:** the plan lists `con`, `aux`, `nul`, `prn`, `com1`–`com9`,
`lpt1`–`lpt9`, and does not say whether `con.jpg` counts.
**Assumed:** it does — the stem before the first dot is compared, case-folded.
**Why:** Windows reserves the names with any extension, so `con.x` is exactly as
unusable as `con`; it is the same rule applied as Windows applies it.
**Reversible?** Yes.

### Pass-1 tests changed by pass 2 — the regressions, named
**Pass:** 2   **Date:** 2026-09-13   **Where:** `tests/integration/test_exit_codes.py`, `tests/unit/cli/test_classify.py`
Pass 1 used `optica fetch` as a convenient command that always failed with
"not available in this build". Pass 2 makes `fetch` real, so every pass-1 test
that leaned on that stand-in either broke or went quietly vacuous. Each is
listed; none is a silent edit.

1. **`test_exit_codes.py::test_optica_error_is_one` — assertion broke.** It ran
   `fetch -c cat,dog` in a subprocess and expected exit 1. Under pass 2 that
   command resolves two valid classes and proceeds: in this session it
   **downloaded the Open Images class list from GCS** (a real network call from
   a test), reached the class confirmation, read EOF from the subprocess's
   inherited stdin and exited **130**. The old assertion no longer holds because
   the command it named is no longer an error. **Changed to** `fetch -c cat`,
   which raises `OpticaValidationError` (fewer than 2 classes) before any
   network access — still an `OpticaError`, still exit 1, still from a real
   process. What the test proves is unchanged: an `OpticaError` exits 1 without
   a traceback.
2. **`test_classify.py::TestLock::test_the_lock_is_released_when_the_stage_raises`
   — passed, but vacuously.** Its `fetch -c cat` now fails class-count
   validation *before* `acquire_lock`, so "the lock file is absent afterwards"
   held without the lock ever being taken. **Changed to** `train`, whose body
   still raises inside the lock. Release after a failure inside the real fetch
   body is covered by a new fetch test.
3. **`test_classify.py::TestGlobalFlagsEitherPosition::test_dry_run_is_accepted_on_the_commands_that_take_it`
   — passed for a different reason.** It asserted exit 1 for `fetch --dry-run`,
   meaning "the flag parsed and the unbuilt stage raised". `fetch --dry-run` now
   fails for a missing `--classes` instead. **Changed** the `fetch` case to
   `fetch --dry-run -c cat,dog`, which now exits 0 without touching the network
   or disk; `train`, `export` and `run` keep the old expectation.
4. **`test_quiet_is_accepted_before_or_after_the_command`** uses `fetch -c cat`
   and still asserts exactly what it did — the verbosity level is set before
   class validation raises. **Not changed.**

**Also added, affecting every test:** an autouse `_no_network` fixture in
`tests/conftest.py` that makes any real `httpx` transport raise. Item 1 is the
reason: a pass-1 test reached GCS without anyone intending it, and nothing
noticed except a wrong exit code. `httpx.MockTransport` is unaffected. It does
not reach subprocess-based tests, which is why item 1 had to be fixed at the
command line rather than by the guard.

### `GlobalState.argv` ignored the argv actually invoked — a pass-1 defect, fixed
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/cli/main.py:OpticaTyper.invoke_guarded`, `_root`
**Found:** while converting the stub `test_correctable_abort_prints_the_corrected_command`.
The root callback set `state.argv = sys.argv[1:]` unconditionally, so an
invocation through `invoke_guarded(argv)` — every in-process test, and pass 5's
API if it drives the app — recorded the *host process's* argv. A reconstructed
corrected command would have echoed pytest's command line.
**Fixed:** `invoke_guarded` passes `obj=GlobalState(argv=argv)` to Click, and
the root callback only falls back to `sys.argv` when no argv was recorded. The
prompt-redirect retry drops that `obj` so the retried invocation gets fresh
state for its new argv. The console-script path is unchanged (`__call__` already
passes `sys.argv[1:]` as `argv`). The `UsageError`-at-the-base catch and the
`BadOptionUsage`/`MissingParameter` routing are untouched.

### `FORCE_COLOR` in the environment fails 13 pass-1 logging tests — finding
**Pass:** 2   **Date:** 2026-09-13   **Where:** `tests/unit/utils/test_logging.py`; affects any runner
**Found:** this session's shell exports `FORCE_COLOR=3`. With it set, 13 of 29
tests in `test_logging.py` fail — Rich emits ANSI styling into captured output
and exact-string assertions miss. **Reproduced with pass 2's changes stashed**
(`git stash`, 13 failed / 16 passed), so it predates this pass. `NO_COLOR=1`
produces the same class of failure, since Rich still emits bold under it.
**Not fixed:** the consoles are module-level objects built at import, before any
fixture can scrub the environment, and the fix belongs with `utils/logging.py`
rather than with the input layer. Every test run in this pass unsets
`FORCE_COLOR` and `COLORTERM` (`env -u FORCE_COLOR -u COLORTERM pytest`). The
GitHub runners do not set it; a developer shell or another CI that does will see
13 failures that are not regressions.
**Reversible?** n/a — a finding, recorded for the pass that next touches logging.

### `--clip-threshold` hard-error bands are checked before config load
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/cli/classify.py:fetch`, `run`
**Found:** plan § *CLIP Adapter* specifies the exact error for
`--clip-threshold 0.0` on `fetch` (`✕ --clip-threshold 0.0 disables CLIP
filtering entirely.` / `clip mode requires a threshold greater than 0.0.` /
`To skip filtering, use --mode curate instead.`), and a variant on `run` that
also offers `--mode label`. Pass 1's config load already rejects 0.0, 1.0 and
out-of-range values as a numeric-domain violation, and the standing rule runs
config load first — so the plan's wording was unreachable from the CLI; the user
got the generic range error instead.
**Assumed:** when the flag is given, `fetch` and `run` apply the band check to
the flag value *before* config load, so the plan's per-command message is what
prints. A bad value set in a config file still gets config load's error, which
is the enforcement point the plan names for file-borne values. Exit code and
class (`OpticaConfigError`, 1) are the same on both routes.
**Why:** the plan states the message verbatim, and the config-load check was
never meant to replace it — the plan describes the seven bands as an elaboration
of the general range rule, not a second copy of it.
**Reversible?** Yes — one call per command.

### `is_interactive` treated `NUL` as a terminal on Windows — a pass-1 defect, fixed
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/utils/prompts.py:is_interactive`
**Found:** by the live milestone checks from `.smoke/pass2-fetch/`, not by any
test. `optica fetch -c cat,dog -i 12 </dev/null` printed the class confirmation,
read end-of-file and exited **130**; `optica config --clear-staging --yes
</dev/null` did the same at the destructive prompt. Pass 1's settled rule ("A
piped answer is not an answer", above) requires the non-prompting hard error,
exit **1**. Cause, measured (`notes/verified.md` § "On Windows, `isatty()` is
True for the `NUL` device"): `NUL` is a character device, so `isatty()` is True.
A pipe and a file were already handled correctly, which is why pass 1's own
check of the rule passed.
**Consequence while it stood:** an unattended Windows run with stdin detached —
a scheduled task, `subprocess.DEVNULL`, a CI step that closes stdin — got 130
("interrupted") where the exit-code table says 1, so a script could not tell a
refused prompt from Ctrl+C. It failed *safe*: the destructive prompt still
deleted nothing.
**Fixed:** on Windows `is_interactive` also requires `GetConsoleMode` to succeed
on stdin's handle, which it does only for a real console. The platform branch is
at module level, as `lockfile.py`'s is, so mypy checks the live branch on each
runner. Two tests run a real child process with `stdin=DEVNULL` and with a pipe;
the `DEVNULL` one **was verified to fail against the unfixed function** (stashed)
and pass after. The live checks were re-run: both commands now exit 1 with the
hard error, and staging was untouched (12 files).
**Reversible?** Yes, but reversing reinstates exit 130 for detached stdin.

### Em-dash renders as `�` on a cp1255 console — finding
**Pass:** 2   **Date:** 2026-09-13   **Where:** every message containing `—`; `utils/logging.py`
**Found:** live, on the build machine's cp1255 console: `✓ Fetch complete —
20 images…` printed as `+ Fetch complete � 20 images…`. The `✓` → `+` is pass
1's designed fallback; the em-dash is not in its fallback set, and Rich replaced
it rather than raising, so there was **no traceback** — only mojibake. The plan's
own messages use `—` throughout (`--classes is required for fetch — nothing to
search for.`), and pass 2 transcribed them verbatim.
**Not fixed:** extending the glyph fallback is `utils/logging.py`'s concern and
touches every message, not the input layer. Recorded for the pass that next
touches output; the candidate fix is adding `—` → `-` to `Markers`' fallback
mapping, applied to whole lines rather than to the four status glyphs only.

### `pass-2.md`'s milestone says fetch "produces a manifest"; the plan gives fetch no manifest
**Pass:** 2   **Date:** 2026-09-13   **Where:** `notes/passes/pass-2.md` § "Done when"
**Found:** "`optica fetch` runs end to end and produces a manifest." In the plan,
`--manifest` is a local *input* format (CSV/JSON of `path` + `class`) that
`label`, `run` and `train` read; nothing specifies `optica fetch` writing one.
Fetch's specified output is auto-fetch staging — `~/.optica/staging/<class>/`,
a directory whose shape is the layout itself.
**Assumed:** the milestone is judged against the plan's fetch output. No fetch
manifest was built: inventing an output format the plan does not specify would
be building outside scope and would create a contract later passes would have
to honour. `pass-2.md` is a derived artifact and is not edited (the rule applied
to `pass-0.md` and `pass-4.md`).
**If a manifest was meant:** the nearest existing artifacts are the per-class
`.fetch.json` sidecars (candidate keys tried and images delivered, per source and
query — logged above), which are internal bookkeeping, not a user-facing
manifest. Say which is wanted and it is a small, separate change.

### Pass 2 — closed
**Date:** 2026-09-13
**Built:** `src/optica/input/` except `clip.py` — 9 modules:

| Module | Holds |
|---|---|
| `__init__.py` | package docstring (exempt in `_NO_LOGIC`) |
| `classes.py` | both class-name rules (incl. amended leading `-`), class count, blocklist, auto-mode class sequence |
| `validation.py` | per-file stages, conversion, 128px resize, `_x` suffixes, MD5 dedupe, floors, imbalance |
| `sessions.py` | labeling session file and `curation.json`, atomic writes, version checks |
| `local.py` | flat folders, organized datasets, manifests, copy/materialize |
| `openimages.py` | class list (MD5-verified cache) and the per-class candidate index |
| `fetch.py` | source registry, Open Images and Flickr adapters, downloader, fill-to-target into `.partial` staging |
| `curation.py` | staging view, selection thresholds, mass rejection, materializing a selection |
| `manager.py` | single input source, mode resolution, detection order, `dataset/` conflict state, asymmetric `--classes`, `clip_threshold` bands, soft cap, staging list/clear |

Plus the CLI wiring the milestone needs: `optica fetch` end to end,
`optica config --clear-staging`, the shared class-name prompt, and the
preconditions `label`, `curate` and `run` check before the stages later passes
build. Two pass-1 defects fixed where pass 2 exposed them (entries above).

**Milestone:** *"`optica fetch` runs end to end and produces a manifest."*
- **`optica fetch` runs end to end — met, live.** From `.smoke/pass2-fetch/`
  with `HOME`/`USERPROFILE` inside it: `optica fetch -c cat,dog -i 10 --yes`
  exited **0** in 81.3 s — class list downloaded and MD5-verified, 64.0 MiB of
  labels and 38.1 MiB of metadata read, 20 images staged. Per item:

  | Class | Files | Distinct MD5 | Bytes | Candidates tried | Delivered | Not delivered |
  |---|---|---|---|---|---|---|
  | cat | 10 | 10 | 794,749 | 12 | 10 | 2 |
  | dog | 10 | 10 | 1,155,119 | 13 | 10 | 3 |
  | **Total** | **20** | **20** | **1,949,868** | **25** | **20** | **5** |

  All 20 decode as JPEG, named `0001.jpg`–`0010.jpg` per class; no `.partial`
  left; lock released. Follow-up live checks: re-running took 1.0 s and
  downloaded nothing (cache and staging reused); `-i 12` topped each class up to
  `0011`/`0012`; `--classes --yes` exit 1 naming `'--yes'`; `--dry-run` exit 0,
  nothing written; unattended fetch without `--yes` and unattended
  `--clear-staging --yes` both exit 1 with staging intact — **after** the
  `is_interactive` fix, having first exited 130.
- **"and produces a manifest" — not met as written, deliberately.** The plan
  specifies no manifest output for fetch; see the entry above. Awaiting a human
  decision on whether one was meant.
- **CI — not run.** `git push` is denied to the agent. Pass 1's close records
  what claiming green without a run cost; nothing here claims it. A human pushes
  `build/v0.2.0` and confirms the three runners before pass 3.
- Ruff clean; mypy `strict` clean on 59 files.

**State now:** **868 tests collected — 855 passed, 13 skipped.** The 13 are 5
pass-4 stubs + 6 pass-5 stubs + 2 `_NO_LOGIC` exemptions (5 + 6 + 2 = 13); all
14 pass-2 stubs were turned into real tests, leaving pass 1's 25 − 14 = 11.
Runs with `FORCE_COLOR`/`COLORTERM` unset (entry above). Source is 25 files
(pass 1's 16 + 9); test modules 26 (pass 1's 17 + 8 in `tests/unit/input/` +
`tests/unit/cli/test_fetch_command.py`). **Commits this pass: 16**, this entry's
included. `# TODO(test)` markers in `src/`: 2.

**Left open:**
- **Written but never exercised end to end:** the Flickr adapter (no key; Pro
  required) — beside pass 1's MPS branch. Marked `TODO(test)`.
- `optica fetch --mode clip` and a **grouped** blocklist class stop with "CLIP
  filtering is not available in this build" after all entry checks → **pass 4**
  (`input/clip.py`).
- The `dataset/` conflict prompt: state, description, replace and refusal are
  built and unit-tested in `manager.py`, but no pass-2 command writes
  `dataset/`, so no CLI path prompts yet → **passes 3 and 4** (`label`/`curate`
  materialization, `fetch --mode clip`).
- Browser stages of `label`/`curate`, and `curation.py`'s server side → **pass 3**.
  Truncated JPEGs pass header-only pre-flight → **passes 3 and 4** to expect.
- `run` sequencing → **pass 5**.
- Rare-class Open Images cost model computed, not measured → `TODO(test)`.
- `FORCE_COLOR` test fragility and em-dash mojibake → the pass that next touches
  `utils/logging.py`.
- Proposed plan change (class-name rule 1: trailing dot/space, control
  characters) and the `pass-2.md` manifest clause → **human decision**.
- `.smoke/pass2-index/` and `.smoke/pass2-fetch/` are this pass's throwaway
  smoke directories (each with a scratch home); `.smoke/final` and `.smoke/try`
  are pass 1's and were not touched.

**Entries logged this pass:** 19.

| # | Entry | Kind |
|---|---|---|
| 1 | Open Images image-URL acquisition strategy | assumption (the logged decision) |
| 2 | Two modules added to `input/` | assumption |
| 3 | `input/__init__.py` in `_NO_LOGIC` | assumption |
| 4 | Blocklist matching | assumption |
| 5 | Sub-term counts, grouped or separated | assumption |
| 6 | Mixed overlap re-opens the definition | assumption |
| 7 | Header-only pre-flight misses a half JPEG | **finding → passes 3, 4** |
| 8 | Class-name rule 1 gaps | **proposed plan change** |
| 9 | `.fetch.json` sidecar | assumption |
| 10 | Dedupe at the write into staging | assumption |
| 11 | Fetch loop parameters | assumption |
| 12 | Reserved device name with any extension | assumption |
| 13 | Pass-1 tests changed by pass 2 | record (regressions named) |
| 14 | `GlobalState.argv` | **pass-1 defect, fixed** |
| 15 | `FORCE_COLOR` fails logging tests | finding |
| 16 | `--clip-threshold` checked before config load | assumption |
| 17 | `is_interactive` and `NUL` | **pass-1 defect, fixed** |
| 18 | Em-dash mojibake | finding |
| 19 | Milestone "produces a manifest" | assumption (awaiting a decision) |

12 assumptions + 3 findings + 1 proposed plan change + 2 fixes + 1 record = 19.

**Next:** pass 3 — `server/`. Read this file first: entry 7 (truncated JPEGs),
the `dataset/` conflict item above, and `input/curation.py`, which the server
should call rather than reimplement.

---

## Pass 2 — after close, while CI runs

Four questions from review. The entries below correct three of this pass's own
entries (this file is append-only, so each correction supersedes rather than
edits) and fix one item inside pass 2's scope.

### Stale pass prompt — `pass-2.md` "produces a manifest"
**Pass:** 2   **Date:** 2026-09-13   **Where:** `notes/passes/pass-2.md` § "Done when"
**Supersedes the classification of** *"`pass-2.md`'s milestone says fetch
'produces a manifest'; the plan gives fetch no manifest"*, above, which logged
this as an assumption awaiting a decision. There is nothing to decide:
`CLAUDE.md` says the plan wins over anything under `notes/`, and the plan gives
`optica fetch` no manifest output. The clause is simply wrong — a **stale pass
prompt**, the same disposition pass 0 gave `pass-4.md` ("the first pass that
needs torch") and `pass-0.md` step 4 (`.gitignore`). **`pass-2.md` is not
corrected.** Pass 2's milestone therefore reads, against the plan: *`optica
fetch` runs end to end* — **met**, live (the pass 2 close entry has the run).

### Closing the loop on "manifest" — built, and what pass 3 will find
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/local.py`, `src/optica/input/sessions.py`
**The plan's one manifest** is the `--manifest` input format, plan
§ "Input & Acquisition" → *`--manifest`* (l.670–700), with the session-ID rule
repeated in § "Labeling & Curation" → *Staging shapes* (l.972, l.1002) and
Implementation Note 14. It is a CSV (`path` + optional `class`, header required)
or a JSON array of objects, read by `optica label`, `optica run`, and `optica
train` when fully labeled.
**What creates one: the user.** Nothing in the plan has Optica write a manifest.
l.672: *"A manifest is **disposable input** — used only to build the file list,
**never rewritten**; labeled output is copied into `dataset/<class>/` exactly as
`--folder` does."* l.678 repeats "the manifest never rewritten" for
materialization.
**Built for it** (committed `628f245`, `e2c3b63`):

| Plan requirement | Where |
|---|---|
| format by extension; CSV header; `path`/`class` case-insensitive, trimmed; extra columns ignored | `local.py:parse_manifest`, `_read_csv`, `_read_json` |
| missing-column error naming what the header held | `parse_manifest` (`path`), `Manifest.require_fully_labeled` (`class`) |
| relative paths against the manifest's directory; URLs unsupported, not invalid | `parse_manifest`, `_is_url` |
| exact duplicates collapse with count; contradictions a hard error naming rows | `parse_manifest` |
| un-organized / mixed / fully-labeled states; fully labeled to `label` is a hard error | `Manifest.label_state`, `require_consistent`, `require_unlabeled_for_label`, `require_fully_labeled` |
| class column through both class-name rules | `parse_manifest` → `classes.normalize_class_names` |
| missing and unreadable rows via pre-flight | `local.py:preflight` |
| materialization, same copy as `--folder`, post-conversion `_x` collisions | `local.py:copy_into_dataset` |
| session ID = path + content hash | `Manifest.content_hash`, `sessions.py:session_id`, `LabelingSession.new(content_hash=…)` |

**Does pass 3 find what it needs — checked by driving the path, not asserted.**
`C:\Users\DEN\.claude\jobs\955142b7\tmp\manifest_path.py`, data in
`.smoke/pass2-manifest/`, pass-2 code only: an 8-row unlabeled CSV → parse →
`require_unlabeled_for_label` → pre-flight (**6 readable, 2 unreadable**: `zero
bytes`, `could not be opened`; 6 + 2 = 8) → a manifest-sourced `LabelingSession`
saved after every decision → reloaded (**cat 2, dog 3, 1 skipped, 0 not
reached**; 5 + 1 + 0 = 6) → `copy_into_dataset` copied **cat 2, dog 3** → the
manifest's SHA-256 **unchanged**. Appending one row gave a **different session
file** (and the exact-duplicate row collapsed, count 1). A fully labeled JSON
manifest was refused by the label check and materialized **cat 1, dog 1**.
**Yes — the pieces compose**; no pass-2 command runs the path yet only because
`optica label` stops at its browser stage.

### Stale pass prompt — `pass-3.md` "write back through the manifest" contradicts the plan
**Pass:** 2 (logged for pass 3)   **Date:** 2026-09-13   **Where:** `notes/passes/pass-3.md` § "Done when"
**Found:** *"`optica label` and `optica curate` both start, serve their page, and
write back through the manifest."* The plan says the manifest is **never
rewritten** (l.672, l.678), and `optica curate` has no manifest at all — it reads
auto-fetch staging (l.736, l.983). What the plan has both pages write back
through is the **session files**: *"Both files are written on every decision"*
(l.1018) — `~/.optica/staging/labeling/<session_id>.json` for labeling and
`~/.optica/staging/curation.json` for curation — and, on completion, the copy
into `dataset/<class>/`.
**For pass 3:** read "write back" as the plan does. Labeling writes through
`sessions.py:LabelingSession.save` (then `local.py:copy_into_dataset` at
Finish); curation writes through `CurationSession.save` (then
`curation.py:materialize_selection` at Confirm). **Do not write to a manifest
file** — that would violate l.672 and change the manifest's content hash, which
would silently start a fresh labeling session on the next run (Implementation
Note 14). `pass-3.md` is not corrected: derived artifact, log-only.

### Manifest assumptions that were made and not logged — silent until now
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/input/local.py`
Found while answering the question above. Each was a decision the plan does not
make; none was written here when it was made, which is the outcome the gap rule
exists to prevent.
- **Row numbers** in errors are **1-based data rows** (header not counted), for
  CSV and JSON alike. The plan's examples name "rows" without numbering them.
- **An empty `path` value is a hard error** naming the row. The plan specifies
  missing columns and URLs, not blank cells.
- **An empty `class` cell counts as unlabeled** — so a CSV with a `class` column
  but some blank cells is the *mixed* case, a hard error, not a partially
  labeled one to be tolerated.
- **A UTF-8 BOM is accepted** (`utf-8-sig`); any other non-UTF-8 file is a hard
  error. The plan names no encoding.
- **JSON keys are normalized per record**, so objects spelling a column
  differently (`path`, `Path`) agree; the reported "header" for JSON is the
  union of keys in first-seen order. The plan's normalization rule is written
  for a CSV header row.
- **`list_files` skips hidden files and `Thumbs.db`/`desktop.ini`** in a flat
  folder, so OS litter is not listed as an unreadable image the user never put
  there. The plan says every file is pre-flighted.
**Reversible?** Each is one condition in `local.py`.

### Correction — `FORCE_COLOR` is fixed inside pass 2, and the earlier entry was wrong on three counts
**Pass:** 2   **Date:** 2026-09-13   **Where:** `tests/conftest.py`
**Corrects** *"`FORCE_COLOR` in the environment fails 13 pass-1 logging tests —
finding"*, above. That entry said: 13 failures; that `NO_COLOR=1` fails the same
way; and "not fixed", handed to a later pass. All three were wrong, and the
first two were never measured cleanly — the `NO_COLOR` runs still inherited
`FORCE_COLOR=3` from the shell.
**Measured** (`notes/verified.md` § "Which environment variables change Rich's
output under the test suite"): **31** failures, not 13 — **17 pass-1 tests and 14
pass-2 tests**. `TTY_COMPATIBLE=1` fails the same 31. `NO_COLOR=1` alone fails
**none**.
**The pattern, named:** these tests assert an ambient environment fact — that
the process was not told to force colour. It is the same failure mode as pass 1's
`test_the_test_run_is_inside_a_venv`, which failed all three runners on the
first CI run. This is its second instance in the build.
**Why it is pass 2's to fix, not to hand forward:** 14 of the 31 are pass 2's own
tests (`test_fetch_command.py`, and the pass-2 stubs made real in
`test_classify.py`, `test_main.py`, `test_config_command.py`) — pass 2 did not
merely inherit the dependence, it extended it. The fix is test-harness only,
in a file pass 2 already owns changes to, and changes no product behaviour:
honouring `FORCE_COLOR` is correct for a user who sets it.
**Fixed:** `tests/conftest.py` removes `FORCE_COLOR` and `TTY_COMPATIBLE` before
`optica.utils.logging` is imported. Before import, not in a fixture, because Rich
fixes the colour system when a console is constructed and the consoles are
module-level. Child processes spawned by integration tests inherit the scrubbed
environment. **Verified to bite:** the per-variable matrix gave 31 failures for
each variable before the change and 0 after, re-run with no scrubbing in the
parent; the whole suite now passes in this shell as-is.
*Rejected: mutating the consoles' private attributes, which would break on a Rich
upgrade; and rebuilding the consoles per test, which would orphan every
`from optica.utils.logging import out_console` already bound.*
**Supersedes** the pass 2 close entry's instruction to run tests with
`env -u FORCE_COLOR -u COLORTERM`. That is no longer needed.

### Correction — the em-dash finding had the wrong mechanism; the real defect is wider
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/utils/logging.py`; `notes/verified.md` § "What cp1255 can and cannot encode"
**Corrects** *"Em-dash renders as `�` on a cp1255 console — finding"*, above.
That entry said the em dash "is not in [pass 1's] fallback set, and Rich replaced
it". **Both halves were unmeasured and wrong.** The em dash **is encodable** in
cp1255 (`0x97`); Python wrote that byte correctly, and the Git Bash terminal
behind the pipe decoded it as UTF-8 and showed `�`. It is an encoding
*mismatch* between the stream and the terminal, not an encoding *failure*.
**Was pass 1's approach deliberately limited to four glyphs? Yes.** Its entry
("ASCII fallback for the four status glyphs") scopes it to "the plan's
user-facing marker set", tests each glyph against the stream's encoding, and
explicitly rejects two stream-level alternatives: forcing UTF-8 ("mojibake on a
legacy console rather than a crash") and `errors="backslashreplace"` on stdout
("strictly harder to read than `X`" — for a marker, which has a good ASCII
stand-in).
**Does it generalise to the em dash? No, for a reason that matters.** The
mechanism asks "can this stream encode this character?" For the em dash the
answer is yes, so the fallback would never fire. Adding `—` to the table would
change nothing on this machine. What the em dash needs is a correct
stream-to-terminal encoding, which is the option pass 1 rejected.
**The real defect the question surfaced — not fixed, a decision for you:** a
character the stream *cannot* encode raises on **stdout**. Measured:
`out_console.print` of `→` raises `UnicodeEncodeError`, while `err_console`
degrades to `\u2192` (stderr's `backslashreplace`). Pass 1 protected the four
glyphs, but stdout also carries **user data**: class names, paths, Open Images
display names. Reached through the real CLI with valid input:
`optica fetch -c café,dog --dry-run` → exit 1, *"Optica hit an unexpected error:
UnicodeEncodeError … This is a bug in Optica"*. `café` passes both class-name
rules, and a test asserts it does. The global handler does its job (no raw
traceback), but a valid command fails. It does not occur on a UTF-8 stream (Linux,
macOS, a UTF-8 Windows console).
**Why not fixed here:** every fix is a stream-level policy for stdout in
`utils/logging.py`, and each option is one pass 1 considered and rejected for
its glyphs — `errors="backslashreplace"` (or `"replace"`) on stdout at CLI
start, or UTF-8 output where the stream is a pipe. Re-deciding a settled pass-1
choice is not something to do unannounced from pass 2, even though a pass-2
command is what reaches it. **Recommendation:** `backslashreplace` on stdout,
set in `OpticaTyper.__call__` (CLI only, so the Python API never reconfigures a
caller's stream) — pass 1's objection was about markers, which keep their `X`/`+`
fallback; for arbitrary text there is no stand-in, and an escape beats a failed
command.
**Consequence while open:** on a non-UTF-8 Windows stdout, any command that
prints a non-encodable class name or path to stdout fails with exit 1. Error
messages (stderr) are unaffected apart from escapes.

### Correction to the pass 2 close entry
**Pass:** 2   **Date:** 2026-09-13   **Corrects:** *"Pass 2 — closed"*, above.
- **Milestone:** the "produces a manifest" clause is a stale pass prompt, not
  "not met, deliberately" — see above. Against the plan, the milestone is met.
- **Left open:** "`FORCE_COLOR` test fragility" is **fixed**; "em-dash mojibake"
  is replaced by the stdout-encoding defect above, awaiting a decision.
- **State:** still 868 collected, 855 passed, 13 skipped — now in this shell as-is,
  with no environment scrubbing by the caller.
- **Entries logged this pass:** 19 at close, plus 7 here = **26**. The 7: 2 stale
  pass prompts, 1 record (the manifest loop), 1 set of late-logged assumptions,
  3 corrections — one of which (`FORCE_COLOR`) is also a fix.

### Unencodable user text on stdout — fixed, alongside the status-glyph fallback
**Pass:** 2   **Date:** 2026-09-13   **Where:** `src/optica/utils/logging.py:protect_streams`, `src/optica/cli/main.py:OpticaTyper.__call__`
**Decided:** by the user, after the correction entry above left it open.
**The defect:** text Optica prints but does not choose the characters of — a
class name, a path, an Open Images display name — raised `UnicodeEncodeError` on
a stdout that could not encode it. Reached with valid input:
`optica fetch -c café,dog --dry-run` on this machine's cp1255 stdout exited 1
with *"Optica hit an unexpected error … This is a bug in Optica"*; `café` passes
both class-name rules. The same text on a replaced stderr produced a **raw
Python traceback**, because the failure happened inside the handler's own
`render_error`.

**Two mechanisms, two problems — why both exist.** This is not pass 1's decision
revisited; it is a problem pass 1's mechanism was never for.
- **Status glyphs → `Markers`, unchanged.** The four glyphs each have a good
  ASCII equivalent: `✓` is `+`, `✕` is `X`. Where the stream cannot encode one,
  showing its equivalent is strictly better than any stream-level rendering, and
  that is why pass 1 chose per-glyph fallback over `backslashreplace` for them.
  That reasoning still holds and nothing about the glyphs changed; a test pins
  the four fallbacks.
- **User text → `protect_streams`, new.** A class name has no ASCII equivalent —
  there is nothing to transliterate `黑猫` to — so a per-character table cannot
  exist. The only honest rendering is an escape (`\u9ed1\u732b`), and an escape
  in the output beats a command that fails. The stream's error handler is set to
  `backslashreplace`; its encoding is not touched.
- **They compose rather than overlap:** `Markers` resolves the glyphs before text
  reaches the stream, so a glyph never needs the escape; the escape only ever
  applies to text that has no other rendering.

**Why stderr already escaped and stdout raised — incidental, not by
construction.** Measured and sourced in `notes/verified.md` § "Why stderr
escapes and stdout raises":
- CPython forces the interpreter-created `sys.stderr` to `backslashreplace` — the
  Python 3.11 docs: *"For stderr, the `:errorhandler` part is ignored; the handler
  will always be `'backslashreplace'`."* Even `PYTHONIOENCODING=ascii:strict`
  leaves it there. stdout gets no such guarantee: `surrogateescape` on this
  machine by default, `strict` under `PYTHONIOENCODING`.
- So stderr was safe **by CPython's construction, not Optica's**. Nothing in
  Optica set that handler or relied on it knowingly. And it was one ordinary act
  away from the same crash: replacing `sys.stderr` with a `TextIOWrapper` — what
  an embedding application, a logging harness, or a test runner does — gives the
  default handler `strict`, and `err_console.print` then raised (measured). It
  also rested on Rich writing text through the stream rather than encoding
  itself, which is Rich's implementation, not its contract — the "one dependency
  bump away" risk.
- **Now by construction:** `protect_streams` is applied to **both** streams, so
  the escape no longer depends on who created stderr or on Rich's write path.

**Where it applies — the CLI only.** Called from `OpticaTyper.__call__`, the
console-script path. Not from `invoke_guarded`, and never on import: the Python
API (pass 5) must not reconfigure a host process's streams, which it does not
own. A stream already on a non-raising handler, or one without `reconfigure`,
is left alone.

**Tests — the condition is constructed, never the runner's.** This is the third
time this build has met a test that depends on an ambient environment fact
(`running_in_venv` in pass 1, `FORCE_COLOR` above). Neither test here reads the
runner's code page:
- `tests/unit/utils/test_logging.py::TestUnencodableUserText` builds the stream
  itself — `io.TextIOWrapper(BytesIO(), encoding="ascii", errors="strict")` —
  with a control test proving that stream raises before protection.
- `tests/integration/test_output_encoding.py` runs the real entry point in a
  child: stdout made strict ASCII with `PYTHONIOENCODING=ascii:strict` (documented
  to apply to pipes on every platform), stderr replaced in the child by a strict
  ASCII `TextIOWrapper`. Three controls: the child's stdout really reports
  `ascii strict`; the class name is not blocklisted; and the child's source is
  ASCII-only (`assert source.isascii()`, names passed with `!a`), so how a
  non-ASCII command-line argument is encoded — which differs between Windows and
  POSIX — is not what varies.
- **A control that mattered:** the first draft used `猫`. The plan blocklists
  "single characters", so the fetch stopped at the CLIP entry check before
  printing any class name — the stdout test was failing for the wrong reason and
  would have passed without ever reaching the encoding path. Caught by reading
  *why* it failed, not just that it did; now `黑猫`, with a test asserting it is
  not blocklisted.
**Fails without the fix, passes with it — shown on the final code:** with
`logging.py` and `main.py` stashed, `test_output_encoding.py` gave **2 failed, 3
passed** — the stdout test with *"unexpected error: UnicodeEncodeError: 'ascii'
codec"*, the stderr test with a raw `Traceback` — and **5 passed** restored. The
6 unit tests likewise. **Verified here on Windows only;** the construction is
platform-independent by design, and Linux and macOS confirmation is the CI run.
**Live, on this machine's real cp1255 console:** `optica fetch -c café,dog
--dry-run` → exit 0, `Classes: caf\xe9, dog`; `optica fetch -c 黑猫,dog --dry-run`
→ exit 0, `Classes: \u9ed1\u732b, dog`; a real fetch still ends `+ Fetch
complete…`, glyph fallback intact.
**Still open, and a different problem:** the em dash renders `�` in Git Bash. It
*is* encodable in cp1255; the terminal misreads the bytes. No error handler can
fix a mismatch between what the stream writes and what the terminal decodes.

### Correction — the framing of the stdout-encoding entry
**Pass:** 2   **Date:** 2026-09-13   **Corrects:** *"Correction — the em-dash finding had the wrong mechanism; the real defect is wider"*, above.
That entry framed the fix as re-deciding "a settled pass-1 choice" and each fix
option as "one pass 1 considered and rejected". That was wrong. Pass 1 rejected
stream-level handling **for the four status glyphs**, where a per-glyph ASCII
equivalent exists and is better. Arbitrary user text has no such equivalent.
Different problem, different tool — see the entry above, under which both
mechanisms now coexist.

### Pass 2 — closed (final)
**Date:** 2026-09-13
**Supersedes** *"Pass 2 — closed"* and *"Correction to the pass 2 close
entry"*, above, for everything this entry states. Their per-item milestone
breakdown and the build table stand.

**Commits this pass: 19** (`01812e9..HEAD`, this entry's commit included):
10 `feat`, 3 `fix`, 1 `test`, 1 `chore`, 4 `docs`
(10 + 3 + 1 + 1 + 4 = 19).

| # | Commit | Kind |
|---|---|---|
| 1 | `docs(verified)`: Flickr API and Open Images acquisition checks | docs |
| 2 | `feat(input)`: class-name rules, blocklist, class sequence | feat |
| 3 | `feat(input)`: image validation pipeline | feat |
| 4 | `feat(input)`: labeling and curation session stores | feat |
| 5 | `feat(input)`: Local Adapter — folders, datasets, manifests | feat |
| 6 | `feat(input)`: Open Images class list and candidate index | feat |
| 7 | `feat(input)`: Fetch Adapter, source registry, staging writes | feat |
| 8 | `docs(build-log)`: assumptions for the input modules | docs |
| 9 | `feat(input)`: Curation Adapter staging, selection, thresholds | feat |
| 10 | `feat(input)`: Input Manager detection, conflict, staging | feat |
| 11 | `feat(cli)`: `optica fetch` end to end | feat |
| 12 | `feat(cli)`: `optica config --clear-staging` | feat |
| 13 | `test(config)`: `clip_threshold` band stubs made real | test |
| 14 | `fix(prompts)`: Windows `NUL` is not a terminal | fix |
| 15 | `chore(input)`: the two `TODO(test)` markers | chore |
| 16 | `docs(build-log)`: close pass 2 | docs |
| 17 | `fix(tests)`: stop asserting colour was not forced | fix |
| 18 | `fix(logging)`: unencodable user text escapes instead of raising | fix |
| 19 | `docs(build-log)`: close pass 2 (final) | docs |

**Milestone — met.** Read against the plan (`pass-2.md`'s "produces a manifest"
is a stale pass prompt): *`optica fetch` runs end to end.* Live, from
`.smoke/pass2-fetch/`: `optica fetch -c cat,dog -i 10 --yes`, exit 0, 20 valid
images staged (cat 10 / 794,749 B, dog 10 / 1,155,119 B; 1,949,868 B total),
lock released. Rerun, top-up, `--dry-run`, `--classes --yes`, unattended
refusal and non-ASCII class names all re-checked live since.
**CI:** pushed by the human; **result pending**. Nothing here claims green.

**State:** **879 tests collected — 866 passed, 13 skipped** (13 = 5 pass-4 stubs +
6 pass-5 stubs + 2 `_NO_LOGIC`; 866 + 13 = 879 = 868 at the previous close + 6
unit + 5 integration). Passes in this shell as-is, `FORCE_COLOR=3` inherited.
Ruff clean; mypy `strict` clean on 60 files.

**Handed forward:**

| To | Item | Where it is recorded |
|---|---|---|
| **Pass 3** | `pass-3.md`'s "write back through the manifest" is stale. Both pages write back through the session files (`LabelingSession.save`, `CurationSession.save`), then `copy_into_dataset` / `materialize_selection`. **Never write to a manifest:** it violates l.672, and it changes the manifest's content hash — and the session ID is path + content hash (Note 14). Verified in pass 2: appending one row gave a **different session file**. The user's labeling progress would sit orphaned in `~/.optica/staging/labeling/` while a blank session started, with no error and nothing to tell them why. | § "Stale pass prompt — `pass-3.md`…"; § "Closing the loop on 'manifest'" |
| **Pass 3** | The server calls `input/curation.py` (view, thresholds, mass rejection, materialize) and `sessions.py` rather than reimplementing them. | `input/curation.py` docstring |
| **Pass 3** | Header-only pre-flight passes a JPEG cut in half; expect thumbnails that fail to render. | § "Header-only pre-flight…" |
| **Passes 3 and 4** | The `dataset/` conflict prompt is built in `manager.py` but no pass-2 command writes `dataset/`, so no CLI path prompts yet: `label`/`curate` materialization (3), `fetch --mode clip` (4). | close entry, Left open |
| **Pass 4** | `input/clip.py`: `fetch --mode clip` and grouped blocklist classes pass every entry check and stop at "CLIP filtering is not available in this build". Truncated JPEGs surface as decode errors at training. | close entry; § "Header-only pre-flight…" |
| **Pass 5** | `optica run` sequencing (pre-checks and mode line only so far). The Python API must **not** call `protect_streams` — CLI only. | close entry; § "Unencodable user text on stdout" |
| **Any pass with a key / live budget** | Flickr adapter never exercised with a real key; rare-class Open Images cost model computed, not measured. Both marked `TODO(test)`. | § "Fetch loop parameters"; § "Open Images … strategy" |
| **The next pass touching `utils/logging.py`** | Em-dash `�` in Git Bash — an encode/decode mismatch, not an error; not fixable by error handler. | § "Unencodable user text on stdout", last paragraph |
| **Human** | Proposed plan change: class-name rule 1 misses trailing dot/space and control characters. | § "Proposed plan change — class-name rule 1…" |

**Entries logged this pass: 29** = 19 at the first close + 7 after it + 3 here
(the stdout-encoding fix, the framing correction, this close).
### Two unused pass prompts corrected rather than logged
**Pass:** between 2 and 3   **Date:** 2026-09-13   **Where:** `notes/passes/pass-3.md`, `notes/passes/pass-4.md`
**Found:** four of the seven pass prompts carry a claim the plan does not
support. `pass-0.md` (twice) and `pass-2.md` were found while their passes were
open or closed and were logged, not corrected. `pass-3.md` and `pass-4.md` are
still unused.
**Action taken — corrected, departing from the log-only precedent.** Two
reasons. These prompts have not been used, so correcting them is not rewriting
a consumed artifact. And a file the agent can re-read survives compaction where
an opening-message instruction does not — the same argument `CLAUDE.md` makes
for `notes/verified.md` over conversation. `pass-3.md`'s claim is also the
dangerous one: writing back through the manifest changes its content hash,
which is part of the session ID, silently orphaning the user's labeling
progress.
**Edits:** `pass-3.md` "Done when" now reads *write back through their session
files* (plan l.1018, not l.672's disposable input). `pass-3.md` "Read" now
names `notes/verified.md` and `notes/build-log.md` — it was the only pass
prompt naming no `notes/` file. `pass-4.md`'s opening now says the torch stack
is installed by the human before launch, and that pass 0 task 4 needed torch
first.
**Not corrected:** `pass-0.md` and `pass-2.md`. Their passes are closed and the
claims are historical. See the addendum §1.11 for the full pattern.

### Pass 2 — CI green on all three runners
**Pass:** 2   **Date:** 2026-09-13
**Reported by the human**, after pushing: CI is green on all three runners
(ubuntu, macos, windows). The agent cannot see CI runs (`git push` and the
Actions UI are outside its reach), so this is a relayed result, not one the agent
observed. At the time of the report the local branch matched
`origin/build/v0.2.0` at `d85f353` (0 commits ahead, 0 behind), which includes
every pass-2 commit through `c3fcdeb`.
**What this confirms that local runs could not:** the two platform-independent
constructions this pass relied on hold off Windows — the `FORCE_COLOR` /
`TTY_COMPATIBLE` scrub in `tests/conftest.py`, and
`tests/integration/test_output_encoding.py`, which was verified locally on
Windows only. It also confirms the Windows-only `is_interactive` console check
and its module-level platform branch are clean under mypy on the POSIX runners.
**Closes** the "CI: pushed by the human; result pending" line of *"Pass 2 —
closed (final)"*, above.

**Supersedes one handoff in that entry:** its first pass-3 row says
`pass-3.md` "is stale" and was "not corrected". Since then the human corrected it
(`e6f7e09`, entry immediately above): "Done when" now reads *write back through
their session files*. **Pass 3 should work from `pass-3.md` as it now stands.**
The warning in that row stands unchanged — never write to a manifest; its
content hash is part of the session ID.

**Pass 2 is complete.** Next: pass 3 — `server/`.

---

## Pass 3

**Read at start:** `CLAUDE.md`; `notes/passes/pass-3.md` as corrected on
2026-09-13 (pages write back through their **session files**, never a manifest);
the plan's § "Labeling & Curation" in full, plus § "Input & Acquisition"
(`--manifest`, class-count validation, pre-flight, the `dataset/` conflict),
"Global flags", "Error handling and prompt conventions", "Class-name rules",
"Tech Stack", "Version-bound strategy", "Code Structure", "Exceptions",
"Implementation Notes" and the flag reference; `notes/verified.md` in full; this
file from "## Pass 2" onward; and the code pass 3 calls — `input/sessions.py`,
`input/curation.py`, `input/local.py`, `input/manager.py`,
`input/validation.py`, `cli/classify.py`, `cli/main.py`, `cli/__init__.py`,
`utils/prompts.py`, `utils/logging.py`, `exceptions.py`, `tests/conftest.py`,
`tests/unit/test_tree.py`.

Runs in four checkpoints set by the human: (1) the app, its routes, shared JS
and CSS; (2) the label page; (3) the curate page; (4) integration tests and the
live milestone. Each ends committed.

### FastAPI 1.0 — gate item closed, bound unchanged
**Pass:** 3   **Date:** 2026-09-14   **Where:** `pyproject.toml`
Verified before any `server/` code: FastAPI's latest is 0.141.1 on PyPI and on
GitHub, and no 1.x release or 1.0 pre-release exists (`notes/verified.md`
§ "FastAPI has not reached 1.0"). `fastapi>=0.141,<1.0` stands; nothing changed.

### `optica[web]` installs real Click — finding
**Pass:** 3   **Date:** 2026-09-14   **Where:** every `label`/`curate` environment
uvicorn 0.53.0 declares `click>=7.0`, so `import click` succeeds once the web
extra is installed (`notes/verified.md`). `CLAUDE.md`'s "`import click` fails in
a Core install" remains true for Core only. Harmless while Optica never imports
`click` — Typer raises only its vendored classes — and the existing suite passed
with Click present (866 passed, 13 skipped) before any pass-3 code was written.
No `server/` module imports `click`.
**The sharper consequence (added 2026-09-14 at the human's request):**
`CLAUDE.md` implies that reaching for `click` is a *loud* mistake, because
`import click` fails. With the web extra installed it is **silent**: `import
click` succeeds, `except click.UsageError:` compiles and runs — and never fires,
because Typer raises `typer._click.exceptions.UsageError`, an unrelated class. A
handler written that way would pass review, pass in a Core-only environment only
by failing to import, and in a `label`/`curate` environment let every parser
error through as an unexpected exception. Rule unchanged and now load-bearing in
both environments: **use Typer's equivalents** — `typer._click.exceptions`,
`typer.testing` — never `click.*`.

### Route tests cannot run in CI as the plan stands — proposed plan change
**Pass:** 3   **Date:** 2026-09-14   **Where:** plan § "Version-bound strategy"; `.github/workflows/ci.yml`; `tests/unit/server/`
**Found:** the plan says no CI leg installs FastAPI or uvicorn, calling it "a
cost choice rather than a constraint, deliberately not made here: installing a
package the suite does not exercise verifies that its range resolves, not that
its API works." From pass 3 the suite **does** exercise them, so every test
needing FastAPI skips on all three runners.
**Not changed:** `ci.yml` still installs `.[test]`. Changing what CI installs
would reverse a decision the plan records as deliberate.
**Built to narrow the gap:** everything in `server/` that is logic rather than
wiring lives in modules that do not import FastAPI — `app.py` now (port rule,
warning schedule, idle timer, session state, lazy import), and the page
controllers at checkpoints 2 and 3 — so it runs in CI. What skips there: the
whole of `test_routes.py`, and the 8 `TestServe` tests in `test_app.py` that
start a real uvicorn.
**Measured**, in `.smoke/ci-venv` (Core + `[test]`; FastAPI, uvicorn and Click
all absent): ruff clean, mypy clean on 66 files, **1027 passed, 23 skipped** —
13 as at pass 2's close + 1 `_NO_LOGIC` (`server/__init__.py`) + 1
`test_routes.py` module + 8 `TestServe` = 23. In `.venv` (web installed):
**1054 passed, 14 skipped** — 13 + 1 `_NO_LOGIC`. The collections differ by 18
because a module-level skip counts once for its 19 tests (1068 − 1050 = 19 − 1).
**Proposed wording:** in § "Version-bound strategy", replace the sentence that
begins "Adding `FastAPI` and `uvicorn` is a cost choice" with: "`FastAPI` and
`uvicorn` are installed on CI legs, because the browser server's routes are
exercised by the suite; `open-clip-torch` remains excluded for the torch reason
above."
**Reversible?** Yes — one `pip install` argument in `ci.yml`, once decided.

### mypy overrides for modules that may not be installed
**Pass:** 3   **Date:** 2026-09-14   **Where:** `pyproject.toml` `[tool.mypy]`
**Missing:** CI's bare `mypy` checks `src` and `tests` where FastAPI does not
exist (entry above), so `import fastapi` would fail the step.
**Assumed:** `ignore_missing_imports` for `fastapi`, `starlette` and `uvicorn`
only; and for `optica.server.routes` and the two test modules that use FastAPI,
`disallow_untyped_decorators = false` and `warn_return_any = false` — the two
strict checks that fire when those imports resolve to `Any`. With the extra
installed all three ship `py.typed` and are checked for real. Verified both
ways: clean in `.venv` and in `.smoke/ci-venv`.
**Reversible?** Yes — delete both blocks once CI installs the extra.

### `server/__init__.py` added to `_NO_LOGIC`
**Pass:** 3   **Date:** 2026-09-14   **Where:** `tests/unit/test_tree.py`
A docstring and `from __future__ import annotations`. It must stay so: importing
FastAPI there would make `optica.server.app` unimportable in Core. Third entry,
same shape as the other two.

### Two modules added to the plan's `server/` tree
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/`
**Missing:** plan § "Code Structure" lists `app.py`, `routes.py` and `static/`.
**Assumed:** `app.py` holds the lifecycle and every part of it that is logic,
and imports without FastAPI; `routes.py` is the only FastAPI importer. What each
page *decides* — navigation, Finish gating, the widget and tab thresholds,
selection state — goes in `server/labeling.py` and `server/curation.py`, built
with their pages.
**Why:** the CI entry above: inside `routes.py` that logic would be untested on
every runner; inside `input/` it would put browser concerns into the adapter
layer the plan keeps free of UI. The same "placed when built" move as
`utils/prompts.py` (pass 1) and `input/classes.py` (pass 2).
**Reversible?** Yes — moves.

### Browser session key: a `Host` check and a session cookie
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/routes.py:create_app`, `app.py:BrowserSession`
**Missing:** the plan says localhost only — bound to 127.0.0.1 — and nothing
about requests from the user's **own browser**. Any page open there can send
requests to 127.0.0.1:8765, and a DNS-rebinding page can read the answers. The
label page's Finish writes `dataset/`.
**Assumed:** (1) a request whose `Host` is not `127.0.0.1:<port>` or
`localhost:<port>` is refused, which stops rebinding; (2) the terminal prints
`http://127.0.0.1:<port>/?token=<random>`, and opening it sets an `HttpOnly`,
`SameSite=Strict` cookie named per port, then redirects to `/`; the page and
every `/api/` request need the cookie. Static JS and CSS need nothing — they
hold no session data. Images are served **by ID from the page controller's own
list, never by path**.
**Why:** cheap; without it "localhost only" does not describe who can drive the
session. **Mutation-checked:** with both checks replaced by `if False:`, 3 of
the 19 route tests failed; restored, 19 passed.
**Reversible?** Yes — one middleware and one redirect.
**Status (human, 2026-09-14):** kept, and **an item for the next
plan-amendment session to ratify**. Pass 3 builds on these two guards and does
not extend them; any further unspecified security behaviour is a stop, not an
assumption.

### Port binding: Optica binds, uvicorn serves the bound socket
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/app.py:bind_first_free`, `_bind`
**Missing:** how "next free port" is determined.
**Assumed:** bind each candidate on 127.0.0.1 and hand the bound socket to
`uvicorn.Server.run(sockets=[…])`, so nothing can take the port between check
and serve. `SO_EXCLUSIVEADDRUSE` on Windows, `SO_REUSEADDR` on POSIX, per
`notes/verified.md` § "Binding a taken port on Windows". The error names the
range (`8765-8784`) and stops at 65535.
**Known limit, measured:** on Windows, a program listening on `0.0.0.0:<p>`
does not stop Optica binding `127.0.0.1:<p>`; "free" cannot see that case.
**Reversible?** Yes.

### Where the port report and a browser launch failure go
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/app.py:serve`
**Missing:** the plan says the resolved port "is reported in the terminal
whenever it differs", and that browser launch failure is
`OpticaBrowserServerError`; not at what output level, nor the error's fix.
**Assumed:**
- The port report is a **warning** (stderr, shown under `--quiet`): the user set
  a port and did not get it.
- The URL line and "progress is saved as you go" are **status**, hidden by
  `--quiet`.
- `webbrowser.open` returning False raises `OpticaBrowserServerError` and stops
  the server; the fix names the `BROWSER` environment variable, which Python's
  `webbrowser` honours. *Rejected: keeping the server up for the user to open
  the URL by hand* — the plan names launch failure as an error.
**Reversible?** Yes.

### Idle-timer details the plan leaves open
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/app.py:IdleTimer`; the heartbeat in `routes.py`
**Assumed:**
- **The page's heartbeat is not activity.** The page polls every 5 s to show the
  warning; if polling counted, an open tab would never time out.
- **After a stall** (a sleeping laptop) the terminal prints only the newest due
  warning, not each one missed.
- The browser banner shows whenever a warning is due in the current idle period
  and counts down; "Keep Session Active" posts `/api/keepalive`.
- The terminal-keypress trigger reads keys without Enter — `msvcrt` on Windows,
  cbreak `termios` on POSIX — and only when stdin is a real terminal.
  `TODO(test)`: no runner has a console.
**Reversible?** Yes.

### A request that fails ends the session
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/routes.py` middleware; `app.py:serve`
**Missing:** what happens when a handler raises — a session file that cannot be
written, say.
**Assumed:** the page gets a 500 and the "session ended" card; the terminal
re-raises the first error once the server has stopped — as itself if it is an
`OpticaError`, otherwise wrapped in `OpticaBrowserServerError` naming it.
**Why:** plan § "Coding Style": never continue silently past an error. A page
that carried on after a failed save would show decisions never recorded. The
error is caught before uvicorn's own logging, so no raw traceback prints.
**Reversible?** Yes.

### The shared JavaScript has no automated tests
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/static/shared.js`
No build step and no Node in CI, so no JS test runner. `pageItems()` (smart
ellipsis), the heartbeat banner and the theme toggle carry `TODO(test)`, and are
checked by driving a real browser at checkpoint 4.

### Checkpoint 2 — `optica label`, in the order it runs
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/cli/classify.py:label`, `_label_body`
**Missing:** the plan fixes several "before" constraints and no total order.
**Assumed:** (1) a folder or manifest is given, else a precondition error; (2)
**the web extra** is imported; (3) the input's shape — flat folder, or a manifest
that is not fully labeled; (4) `-c`, prompting where a prompt can fire; (5) the
lock; (6) the session file — resume prompt; (7) the `dataset/` overwrite prompt;
(8) pre-flight, unreadable files listed individually; (9) the browser; (10) after
Finish, copy into `dataset/`.
**Why this order:** everything that can refuse the run does so before anything
asks for attention, and every prompt fires before the browser (plan: conflict
prompts fire before any action). (6) precedes pre-flight because the plan says
the `-c` mismatch "is detected before any image is read".
**The web-extra check at (2)** is not the entry-point guard the plan reserves for
`run` and declines for single-step commands. `optica label`'s only stage *is* the
browser, so its body is the point of use; importing there means a user without
the extra is told so before answering a class prompt, a resume prompt and an
overwrite prompt that could never lead anywhere.
**Reversible?** Yes.

### The `dataset/` overwrite prompt deletes nothing until the new dataset is complete
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/cli/classify.py:_confirm_replace`, `_materialize_labels`; `src/optica/input/manager.py:partial_destination`, `commit_dataset`
**Missing:** the plan says the prompt fires at command start and that
"overwrite" means the existing contents are removed before writing. It does not
say when, relative to an hour of labeling that may never finish.
**Assumed:** the answer is taken at command start (the plan's rule); the
**removal happens at commit**. Labeled images are copied into a hidden sibling,
`<parent>/.<name>.partial/`; the floor checks run on it; only then is the old
dataset removed and the sibling renamed into place. Interrupted, timed out, or
failing the floor re-check, the old dataset is untouched and the partial is
removed.
**Why:** consent to *replace* a dataset is not consent to be left with *no*
dataset when labeling does not finish. Still replace, never merge: nothing old
survives a commit. Tests: `TestOverwritePrompt::test_nothing_is_deleted_when_labeling_does_not_finish`,
`TestFloorAfterCopy`.
**Also:** `--yes` and `--force` never answer it, `--overwrite` does, default N
(mutation-checked: switching the prompt's category to CHOICE with `assume_yes`
fails `test_yes_does_not_answer_it`). The abort message adapts the plan's
`run` example to `label`: "To train on your existing dataset: optica train
--dataset <path>", and the corrected command with `--dataset ./new-dataset`
substituted and every other flag kept.
**Two functions added to `input/manager.py`**, beside `replace_destination`,
which cannot serve: it recreates the directory, and on Windows `os.replace`
cannot rename onto an existing directory. Genuinely required by the page, per
`pass-3.md`'s out-of-scope rule.
**Reversible?** Yes.

### Unreadable at copy is counted before duplicates, so the floor error says why
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/cli/classify.py:_materialize_labels`
**Found while building:** `copy_into_dataset` drops two kinds of file —
duplicates and files that fail the full decode (a truncated JPEG that passed the
header-only pre-flight). `check_floor_after_dedupe` calls every drop a
duplicate, so a class emptied by truncated files would read "N duplicates
removed" when there were none.
**Assumed:** files unreadable at copy are listed individually, subtracted from
their class first and checked with `check_floor` ("cat has fewer than 5
images"); only then does the post-dedupe re-check run on what remains. Both
errors keep the session file, and the dedupe one says the session can be resumed.
**Reversible?** Yes.

### Truncated JPEGs: whether pre-flight sees one depends on the image — refines a pass-2 finding
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/input/validation.py:inspect_in_place`
**Measured** (Pillow 12.3.0, each JPEG cut to half its bytes):

| Image | Full | Half | Pre-flight (`verify`) | Full decode |
|---|---|---|---|---|
| flat colour, 160×140 | 989 B | 494 B | **truncated file** | truncated file |
| noise, 300×300 | 48,840 B | 24,420 B | readable | truncated file |
| flat colour, 1024×768 | 12,917 B | 6,458 B | readable | truncated file |

**Consequence:** pass 2's "a JPEG cut in half passes pre-flight" holds for the
photo-like and larger cases, not for every JPEG. A first draft of this pass's
copy-time test used the flat 160×140 image, which pre-flight caught, so the test
failed for a reason unrelated to what it named. The test now uses the noisy
image and asserts, as a control, that pre-flight passes it.

### Labeling session file: removed on completion; Resume keeps the stored classes
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/cli/classify.py:_open_labeling_session`, `_materialize_labels`
**Missing:** what happens to the session file after a successful Finish; what
"Resume" means when `-c` disagrees.
**Assumed:**
- **Deleted once `dataset/` is committed.** The file exists to resume an
  interrupted session; kept, the next `optica label` on that folder would offer
  to resume a finished one. `config --clear-staging` still lists any left by
  interruption.
- **The prompt fires whenever a session file exists** for the source: `[R]
  Resume   [S] Start fresh`, plus `[A] Adopt <new list>` on a mismatch. `--yes`
  picks R (the `--yes` table); a non-interactive run without `--yes` is a hard
  error; adopting is never automatic.
- **Resume on a mismatch continues with the session's stored classes** and says
  so. Adopt deletes entries for departing classes (they return to the queue)
  and saves at once. Start fresh deletes the file.
- A new session is not written until its first decision.
**Reversible?** Yes.

### Exit codes and completion lines for a browser session that does not finish
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/cli/classify.py:_label_body`; `src/optica/utils/logging.py:incomplete`
**Missing:** the plan says timeout is "treated as a Ctrl+C interruption" for
staging, gives the exit-code table (3 for an `✗ X incomplete` completion, 130
for SIGINT), and does not say which applies to a timeout.
**Assumed:** timeout → `✗ Labeling incomplete — the session closed after 60
minutes without activity; progress is saved…`, **exit 3**. Ctrl+C → `✗ Labeling
incomplete — interrupted; progress is saved…`, **exit 130**. Staging is kept in
both. A timeout is an incomplete step, not a signal, so it takes the
incomplete-completion code; Ctrl+C keeps the shell convention.
**`olog.incomplete()` added:** the `✗` line on stderr, never silenced by
`--quiet` — unlike `success`, it is the only record an unattended run has of why
it exited 3.
**Reversible?** Yes.

### `utils/prompts.py` gains `choose()` for multi-letter prompts
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/utils/prompts.py:choose`
**Missing:** only Y/N prompts existed; the labeling resume prompt has two or
three letters. Passes 4 and 5 need the same shape (imbalance F/C/A, run R/C/S).
**Assumed:** one function: the menu on one line (`[R] Resume   [S] Start
fresh`), letters case-insensitive, re-asks on an invalid answer, `assume_yes`
carries the letter the `--yes` table lists, and no terminal without `--yes` is
a hard error of the caller's class.
**Reversible?** Yes.

### Labeling interaction details the plan leaves open
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/labeling.py`
**Assumed:**
- **"Re-assigning returns to the position the user came from"** is read as
  plain auto-advance to the next image — which, after one Back, *is* where the
  user came from. The plan calls it "the same rule applied consistently rather
  than a special case", which rules out remembering a furthest position.
- **Next on an image that already has a label keeps the label.** Skip is what
  Next records for an image with no decision.
- **Next and assignment at the last image stay there** (`at_end` in the state).
- **Counts and Finish gating count only images in this run.** An entry for a
  file that has since gone, or that pre-flight now rejects, cannot be delivered,
  so it does not help clear the floor.
- **A session with nothing left to label** opens on the image it was left at.
- **No keyboard shortcuts.** None are specified; not added.
**Reversible?** Yes.

### Page scripts: syntax-checked and `pageItems` probed with a local Node — not a test
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/static/*.js`
Node v24.12.0 exists on the build machine (not in CI, not a dependency).
`node --check` passes `shared.js` and `labeling.js`. `pageItems(current, total)`
returned `[1]` (1,1); `[1,2,"…",5]` (1,5); `[1,2,3,4,"…",7]` (3,7);
`[1,"…",4,5,6,"…",10]` (5,10); `[1,2,"…",10]` (1,10); `[1,"…",9,10]` (10,10);
`[1,2,3,4,5,"…",9]` (4,9) — no ellipsis ever hides a single page. `formatDuration`
matched the Python one on 150, 1800, 45 and 60 seconds. A manual check, recorded
so it is not mistaken for coverage; the `TODO(test)` markers stay.

### Checkpoint 2 — state
**Pass:** 3   **Date:** 2026-09-14
**Built:** `server/labeling.py` (controller), `static/labeling.html`,
`static/labeling.js`, the labeling routes in `routes.py`, and `optica label`
end to end in `cli/classify.py`; `choose()`, `incomplete()`,
`partial_destination()`, `commit_dataset()`.
**Tests:** `.venv` (web installed) **1156 passed, 14 skipped** (1170 collected);
`.smoke/ci-venv` (Core + `[test]`) **1113 passed, 23 skipped** (1136). Skips
unchanged from checkpoint 1: 14 = 13 + 1 `_NO_LOGIC`; 23 = 13 + 1 `_NO_LOGIC` +
1 `test_routes.py` module + 8 `TestServe`. Collections differ by 34 =
`test_routes.py`'s 35 tests (19 shared + 16 labeling) − 1 for the module-level
skip. Added this checkpoint: 44 `test_labeling.py`, 30
`test_label_command.py`, 16 labeling routes, 5 `choose`, 2 `incomplete`,
4 dataset commit = 101; 1170 − 1068 = 102, the extra 1 being
`test_tree.py`'s parametrized mirror check for `server/labeling.py`.
Ruff and mypy clean in both environments.
**Not yet run:** the real page in a real browser — checkpoint 4.

### Incident — a test run launched the real server and opened a browser tab on this machine
**Pass:** 3   **Date:** 2026-09-14   **Where:** `tests/unit/cli/test_classify.py` (two pass-2 curate tests); `tests/conftest.py`; `src/optica/server/app.py:serve`
**What happened:** after `optica curate` was wired, the full suite was run
(`pytest -m "not slow"`). It did not finish; the Bash tool moved it to the
background at its 600 s limit and it was stopped by hand. Afterwards `netstat`
showed `127.0.0.1:8765 ↔ 127.0.0.1:54350 TIME_WAIT` — a client had connected to
the browser server. Cause: `test_classes_is_warned_and_ignored_by_curate` and
`test_curate_reports_an_incomplete_fetch_and_proceeds` stage an image and run
`optica curate`, which until this checkpoint ended at "not available in this
build". With the web extra installed they reached the real `serve`, which
called the real `webbrowser.open` — so, almost certainly, **a tab opened in the
developer's browser** — and then waited on the 60-minute idle timer. No process
was left running (`tasklist`: no `python.exe`); the test's staging was in a
temporary fake home.
**Fixed, in two parts:**
1. `tests/conftest.py` gains an autouse `_no_real_browser` fixture: any
   `webbrowser.open` raises `RuntimeError("test attempted to open a real
   browser: …")`, the same shape as pass 2's `_no_network`. Raising inside
   `serve` stops the server it started.
2. `serve`'s `open_browser` default was `webbrowser.open` **bound at definition
   time**, which a monkeypatch cannot reach. It is now `None`, resolved at call
   time. Verified to bite: with the guard in place and the two tests
   unchanged, the run finished in about 2 s with the first test failing on the
   guard, not hanging.
**The two pass-2 tests, changed:** both now stand in for the browser stage (a
fake `serve` returning `INTERRUPTED`, and `load_web` stubbed). The first
asserted exit 1 and "optica curate is not available"; it now asserts exit 130,
the warning, and that the browser stage was reached. The second asserted only
the incomplete-fetch warning; it now also asserts the stage was reached, which is
what "and proceeds" means. A third, `test_curate_with_nothing_staged_is_a_precondition_error`,
failed **only in `.smoke/ci-venv`**: without the web extra, curate reports the
missing extra before the staging precondition. It now stubs `load_web`. That one
would have reddened all three runners.
**Pattern:** the build's earlier test defects asserted an ambient fact; this one
*caused* an ambient effect — a test with a real side effect outside the
process. The harness now refuses both network and browser.

### Has `optica label` been seen to start and serve? — not yet, stated plainly
**Pass:** 3   **Date:** 2026-09-14
**Asked by the human** after checkpoint 2. What exists, and what it does not show:
- `tests/unit/server/test_app.py::TestServe` starts **real uvicorn in a worker
  thread, on a real socket**, with the browser launch injected. It proves bind,
  start, port reporting, timeout, Ctrl+C and shutdown. It sends **no HTTP
  request** to that server.
- `tests/unit/server/test_routes.py` sends real requests through Starlette's
  **in-process test client** — no socket, no uvicorn — against the real
  controllers and session files.
- `tests/unit/cli/test_label_command.py` runs `optica label` end to end with
  `serve` **replaced** by a stand-in that drives the real controller.
**Not shown by any of them:** the installed `optica` console script, as a
separate process, serving the page over a socket to an HTTP client, and handing
back to the terminal. **That is checkpoint 4's live run**, for both commands:
launched as a **background process** (the Bash tool's `run_in_background`, so
the two-minute foreground limit does not apply), with `BROWSER` set to a
harmless command so no tab opens, the tokened URL read from its output, the
page and API driven with HTTP requests, and the process observed to exit with
its completion line after Finish/Confirm. Its output and exit code will be
recorded here.

### Checkpoint 3 — `optica curate`, in the order it runs
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/cli/classify.py:curate`, `_curate_body`
(1) `--classes` warned and ignored; (2) web extra; (3) lock; (4) staging must
hold images, an incomplete fetch reported and proceeded past; (5)
`curation.json` resume prompt; (6) `dataset/` overwrite prompt ("…will be
replaced with new images selected in curation:"); (7) the browser; (8) after
Confirm, mass rejection; (9) `dataset/`. Same reasoning as `label`'s order.

### Curation "Start fresh" deletes `curation.json`, not the fetched images
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/cli/classify.py:_open_curation_session`
**Missing:** plan § *Staging shapes*: "Start fresh deletes the staging and any
state file that accompanies it." Read literally for a standalone `optica
curate`, that deletes the fetched images, leaving nothing to curate and the
command failing its own precondition.
**Assumed:** Start fresh discards the **decisions** — `curation.json` — and keeps
the images. Every image is selected again. `--yes` picks Resume; no terminal
without `--yes` is an `OpticaCurationError` (the subsystem of the file).
**Why:** the sentence is about undoing a step; for `run` (pass 5) the fetch is
an earlier step of the same run and deleting it may be right. For standalone
curate, the fetch was a different command. Pass 5 should re-read this.
**Reversible?** Yes.

### What Confirm leaves behind
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/cli/classify.py:_materialize_selection`
**Assumed:** the selection is written to `.<dataset>.partial/` and committed
exactly as for labeling; then **deselected images are deleted from staging**
(the plan: auto-fetched images "are silently deleted if rejected" — so after
commit, not on toggle, which must stay reversible), `curation.json` is deleted,
and **selected images stay in staging** — they are the fetch's own state, which
`config --clear-staging` owns. Removed counts go to `--verbose` detail only.
**Floor re-check:** only a class the selection put **at or above** 5 can be a
"fell below after duplicate removal" error. A class the user left below 5 and
continued past at the mass-rejection prompt is not re-reported as a dedupe
failure — nothing was certified, and `train` refuses it later. Mutation-checked:
removing the staging deletion fails
`test_the_selection_is_written_and_rejected_images_leave_staging`.
**Reversible?** Yes.

### Fetch More, in the browser and at the F of F/C/A
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/curation.py:start_fetch_more`; `src/optica/cli/classify.py:_run_fetch_more`, `_mass_rejection`; `src/optica/input/curation.py:fetch_more`, `fetch_more_refusal`, `fetch_more_shortfall`; `src/optica/input/fetch.py:staged_queries`
**Missing:** the plan names the banner, says it requests enough to restore
`images_per_class` selected, lists Fetch More as a timer trigger and F as
"fetch more, reopen curation". Nothing on how it runs.
**Assumed:**
- **Request = `images_per_class − selected`.** When that is 0 (a class that trips
  only the percentage trigger with plenty selected), nothing is offered —
  fetching more would lower its percentage further.
- **Browser:** the fetch runs in a worker thread through the Curation Adapter's
  `fetch_more`, which calls the Fetch Adapter's own `fill-to-target` with the
  target raised. The page polls progress; the rest of the page keeps working;
  **Confirm waits**; that class's images are not served while its directory is
  `.partial`. A failed fetch is shown on the page and the session continues —
  it is not a session failure. Source: the configured `default_source`.
- **Grouped blocklist classes are refused** in this build (`staged_queries`
  shows sub-terms): their images are CLIP-scored after fetching, which arrives
  with `input/clip.py` in pass 4.
- **Terminal F:** fetches the shortfall of each warned class that can fetch,
  with progress bars, then reopens curation. **A fetch that yields nothing
  returns to the prompt without F** — borrowed from the plan's imbalance prompt
  (*If the fetch yields no new images … re-presents without F*), so an exhausted
  source cannot loop. F is not offered when no warned class can request
  anything.
- C's confirmation defaults to N and N returns to F/C/A (plan); mutation-checked
  by flipping the default. `--yes`: C, then Y. A: `✗ Curation incomplete —
  aborted; staging and selections are preserved.`, exit 3.
**Three functions added to `input/`,** genuinely required: the Curation Adapter
"bridges the Fetch Adapter and the Curation Server", and that bridge did not
exist.
**Never run against a real source.** Checkpoint 4's live run may exercise it
against Open Images; stated there either way.
**Reversible?** Yes.

### Deselections are keyed by path, and a completed fetch changes paths — finding
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/input/sessions.py:CurationSession`; `src/optica/input/fetch.py:fetch_class`
**Found:** `curation.json` stores deselected **absolute paths**. A class curated
while its fetch is interrupted lives at `staging/<class>.partial/0001.jpg`; when
`optica fetch` later resumes and completes it, the directory is renamed to
`staging/<class>/`, the stored paths match nothing, and **those images silently
come back selected**. Also briefly true of the class being fetched into during
Fetch More, which is why Confirm waits and toggles re-key from the reloaded view.
**Not fixed:** the file shape is specified in `sessions.py` from pass 2 and the
plan's example shows full paths; changing the key to `<class>/<filename>` is a
change to a stored format. Recorded for the human.
**Reversible?** n/a — a finding.

### Curation page details the plan leaves open
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/server/static/curation.js`, `src/optica/server/curation.py`
- Tabs show `selected/fetched` per class and mark a class with warnings; the
  dropdown shows the same in each option.
- Hover zoom: a preview beside the tile after the pointer rests 280 ms,
  dismissed on leave; none while the pointer moves across the grid.
- Page size: as many 150 px cells as fit the grid's width and the height left
  above the Confirm bar; recomputed on resize.
- A tile shows a check when selected; deselected tiles are veiled, not hidden.
- An image that fails to draw shows "Could not display" and stays toggleable.
- A stored `active_class` no longer staged opens the first class. The first
  draft of `state()` raised here; a test written for it caught that.

### Checkpoint 3 — state
**Pass:** 3   **Date:** 2026-09-14
**Built:** `server/curation.py`, `static/curation.html`, `static/curation.js`,
the curation routes, `optica curate` end to end; `staged_queries`,
`fetch_more`, `fetch_more_refusal`, `fetch_more_shortfall`; the browser guard in
`tests/conftest.py`.
**Tests:** `.venv` **1236 passed, 14 skipped** (1250 collected);
`.smoke/ci-venv` **1179 passed, 23 skipped** (1202). Skips unchanged. New: 31
`test_curation.py` (server) + 22 `test_curate_command.py` + 14 curation routes +
6 `TestFetchMore` + 6 `TestStagedQueries` = 79, plus 1 mirror check for
`server/curation.py` = **80 = 1250 − 1170**. CI-style collects 66 more than at
checkpoint 2 = 80 − 14 (the curation routes sit inside `test_routes.py`'s
module-level skip). Dev − CI = 48 = 49 route tests − 1. Ruff and mypy clean in
both. `node --check` passes `curation.js`.

### Proposed plan change — how a stored deselection survives a class-folder rename
**Pass:** 3   **Date:** 2026-09-14   **Where:** plan § "Labeling & Curation" → *Staging shapes* (l.1006, l.1008–1016); `src/optica/input/sessions.py:CurationSession`; `src/optica/server/curation.py`; `src/optica/input/curation.py:_selected`
**Supersedes the "Not fixed … Recorded for the human" disposition** of *"Deselections are keyed by path, and a completed fetch changes paths — finding"*, above.

**The question asked first: does the plan specify `curation.json`'s schema, or
the form of a stored deselection? — Yes, so this stops here and is not decided in
the pass.** The plan gives:
- the **schema**, as a literal JSON shape (l.1010–1014):
  `{ "version": 1, "created": "…", "updated": "…", "deselected": { "cat": ["…IMG_0007.jpg"], "dog": [] }, "active_class": "cat" }`;
- the **form of an entry**: "Records **deselected paths** rather than selected
  ones" (l.1016). The example elides the prefix (`…IMG_0007.jpg`), so it fixes
  *paths ending in a file name* and leaves open whether absolute or relative;
- a **version rule** (l.1006): "`version` mismatch is a hard error … The field
  exists to be checked." Changing what an entry means is exactly what that field
  would have to record.

**The defect, restated as a data-integrity bug.** Pass 2 built entries as
absolute paths. A class's directory is renamed between `<class>.partial/` and
`<class>/` by `fetch_class` — when an interrupted fetch completes, and for the
duration of every top-up (Fetch More, `optica fetch -i` more). Every stored
entry under the old directory then matches no image, and **the images the user
deselected silently come back selected**; Confirm would copy them into
`dataset/` and delete nothing from staging. Nothing reports it. Moving the home
directory has the same effect.
**Reachable today by:** `optica fetch` interrupted → `optica curate` (deselect,
Ctrl+C) → `optica fetch` resumed to completion → `optica curate` → R.

**Options.**

| | Change | Rename-proof | Stored format | Existing files |
|---|---|---|---|---|
| **A** | Store entries **relative to the class folder** — the file name only, `"0007.jpg"`, under its class key | yes | same JSON shape; the *meaning* of each string changes | a version-1 file holds absolute paths that match nothing under the new reading — the same silent reselect, unless the version is bumped to 2 and old files are converted or refused |
| **B** | Keep writing paths as today; **match on (class, file name)** when reading, so the directory part is ignored | yes | unchanged | read correctly as they are |
| C | Rewrite `curation.json` whenever `fetch_class` renames a directory | only for renames Optica performs | unchanged | unaffected | 

*C rejected:* it couples the Fetch Adapter to the curation session, misses a
home-directory move, and leaves the failure silent the moment any other rename
happens.

**Why the file name alone is a safe key in both A and B:** staged images are
named by zero-padded sequence index, unique within a class, and numbering
continues from the highest index present (plan l.797), so a file name identifies
one image within its class for as long as staging holds it.
**One case neither A nor B changes, stated so it is not mistaken for fixed:**
answering "Start fresh" at an *interrupted-fetch* prompt deletes `<class>.partial/`
but not `curation.json`; the re-fetch reuses `0001.jpg` upward, and old
deselections would apply to new, different images. The current absolute-path
scheme has the same behaviour, since the paths coincide. A plan decision on
whether fetch's Start fresh also clears that class's deselections would close it.

**Proposed wording** for l.1016, if **B** (recommended for V1 — no format
change, no version bump, files written by pass 2's code read correctly):
> Records **deselected** paths rather than selected ones … An entry is matched to
> a staged image by its class and file name, not by its full path: staged file
> names are unique within a class, and a class directory is renamed between
> `<class>.partial/` and `<class>/` during every fetch, so a full-path match would
> silently reselect deselected images.

If **A** instead: change the example to `"cat": ["0007.jpg"]`, state that
entries are file names relative to the class directory, and either make that
`"version": 2` with version-1 files refused under l.1006's rule, or state a
conversion.

**Not done in this pass:** no code change, and checkpoint 4's integration tests
will **not** assert the stored form of a deselection until this is decided —
they assert only that deselections round-trip through `curation.json` within
one directory layout. A test that renames `<class>.partial/` to `<class>/` and
proves the deselection survives is ready to write under whichever option is
chosen; under the current code it would fail, which is the defect.

### The live harness's `BROWSER` value — what the stdlib does with it
**Pass:** 3   **Date:** 2026-09-14   **Where:** checkpoint 4's live runs; `src/optica/server/app.py:serve`
Read in CPython 3.11.9's `Lib/webbrowser.py` (`.venv`): `register_standard_browsers`
splits `BROWSER` on `os.pathsep`, registers each entry as
`GenericBrowser(<entry>)` **at the front** of `_tryorder`, and
`GenericBrowser.open` runs `Popen([<entry>, url])` — the whole entry is the
executable, no arguments — returning `not p.wait()`. `webbrowser.open` walks
`_tryorder` and **falls through to the next browser whenever one returns False**
— a non-zero exit, or `OSError` for a command that does not exist.
**Consequence:** a `BROWSER` value that is not an executable exiting 0 does not
fail safe — **it opens the real default browser.** The live runs therefore use an
executable that ignores its argument and exits 0 (Git's `usr/bin/true.exe` on
this machine), checked with `webbrowser.get()` / a dry `open` in the same
environment before `optica` is launched. **Nothing in that path depends on the
test suite's `_no_real_browser` guard**, which is a pytest monkeypatch that
exists only inside test processes; the live `optica` is a separate process with
the real `webbrowser`.

### Stored deselections are matched by class and file name — option B, provisional
**Pass:** 3   **Date:** 2026-09-14   **Where:** `src/optica/input/sessions.py:CurationSession.toggle`, `is_selected`, `_file_name`
**Decided:** by the human, after *"Proposed plan change — how a stored
deselection survives a class-folder rename"*, above: **B, provisionally** — built,
tested and shipped in pass 3, and to be reviewed at the plan-amendment session
before pass 4, together with the Start-fresh question below and three other
items. Chosen to build on because it is reversible: the file format does not
change, so if that session prefers A, a migration is written then rather than
this unwound.
**What changed — reading only.** `is_selected` and `toggle` compare a stored
entry with an image by **class and file name** (the last path component, with
either separator). **What is written is unchanged**: deselecting still appends
the image's full path, the JSON shape is the plan's, `"version"` stays `1`. A
re-deselect after a rename finds the old entry by name and does not add a second;
a reselect removes every entry with that name. Every consumer — the page, the
adapter's selection counts, `materialize_selection`, the staging deletion after
Confirm — already went through `is_selected`, so nothing else changed.
**Rejected:** A (file names only, needing `version: 2` or a conversion — decided
at the amendment session if at all) and C (rewrite `curation.json` on every
rename Optica performs — misses a home-directory move and couples the Fetch
Adapter to curation).
**Tests — the rename is performed, not simulated:**
`tests/unit/input/test_curation.py::TestDeselectionsSurviveAFolderRename` (7) —
deselect under `cat.partial/`, `rename` to `cat/` as `fetch_class` does, reload
view and session, the image is still deselected; plus reselect-after-rename,
no duplicate entry, a Windows-separator stored path, class scoping, the file
written is unchanged (full path, version 1), and **a `curation.json` in pass 2's
exact form reads with the same result as before**.
`tests/unit/cli/test_curate_command.py::TestResume::test_a_fetch_completing_between_sessions_keeps_the_deselections`
(1) — the whole path: `optica curate` interrupted with `cat.partial/`, the
rename, `optica curate --yes`, and `dataset/cat/` holds 10, not 12.
**Fails before, passes after — shown:** before the change, 4 of the 7 adapter
tests failed — the rename test with `assert True is False` on `is_selected` —
and the 3 that passed are the controls that must hold either way (format
written, pass-2 file, class scoping). The end-to-end test, run with
`sessions.py` stashed, failed with `{'cat': 12, 'dog': 12} == {'cat': 10, 'dog':
12}`: **the two images the user rejected were copied into `dataset/`.** With the
change, all 8 pass.
**State:** `.venv` 1244 passed, 14 skipped; `.smoke/ci-venv` 1187 passed, 23
skipped (each +8 from checkpoint 3). Ruff and mypy clean in both.
**The drafted wording for plan l.1016 stays a proposal.** `spec/` is not touched.

### Open question — fetch's "Start fresh" leaves that class's deselections behind
**Pass:** 3   **Date:** 2026-09-14   **For:** the plan-amendment session before pass 4
**Where:** plan § *Staging shapes* ("Start fresh deletes the staging and any state file that accompanies it", l.1020) and § *Deletion, staging, and interruption*; `src/optica/cli/classify.py:_resume_or_start_fresh`; `src/optica/input/sessions.py:CurationSession`
**Its own question, not part of the rename fix above.** Option B does not
cover it, and neither would A.
**The behaviour:** at `optica fetch`'s interrupted-fetch prompt, answering N
("start fresh for these classes") deletes `<class>.partial/`. It does **not**
touch `~/.optica/staging/curation.json`, which is curation's file, not fetch's.
The re-fetch numbers new images from `0001.jpg` again (plan l.797: numbering
continues from the highest index *present*, and none is). Any deselection
recorded for that class before the start-fresh now names a **different, new
image** with the same file name, and that image opens in curation already
deselected. Nothing reports it.
**Reached by:** `optica fetch -c cat,dog` interrupted → `optica curate`
(deselect some cat images, Ctrl+C) → `optica fetch -c cat,dog` → N at the resume
prompt → `optica curate` → R.
**Not changed in pass 3** — left exactly as it is, by the human's instruction.
It was also true of pass 2's full-path matching, since the re-fetched paths are
identical to the deleted ones.
**What the session would decide:** whether fetch's Start fresh for a class also
removes that class's entries from `curation.json` (and so whether "the state
file that accompanies it" includes another subsystem's file); or whether
re-fetched numbering must not reuse names a session has recorded; or whether a
curation resume should detect that a class's images were replaced.

### The network guard now lets loopback through
**Pass:** 3   **Date:** 2026-09-14   **Where:** `tests/conftest.py:_no_network`
**Changed:** requests whose host is `127.0.0.1` or `localhost` pass to the real
transport; every other host still raises "test attempted real network access".
**Why:** checkpoint 4's integration tests talk to Optica's own browser server on
a real loopback socket. The guard exists to keep tests off public hosts; loopback
is not that. Pass 2's fetch and Open Images tests (63, over `MockTransport`)
still pass.
**Reversible?** Yes.

### Checkpoint 4 — integration tests
**Pass:** 3   **Date:** 2026-09-14   **Where:** `tests/integration/test_server.py`
Five tests, the command run in a worker thread exactly as the console script
runs it, uvicorn on a real port, an `httpx` client playing the page. Only the
browser launch is replaced (it hands the URL to the test). Ports come from
`.optica.toml`, chosen by binding; the idle timer is 0.1 min, so a failing test
ends in seconds.
1. `label`: page and three scripts served; 3 assignments visible **in the
   session file** before Finish; Finish → exit 0, `dataset/` 5+5, session file
   removed, the URL line and completion line printed.
2. `label`: without the tokened link the page and API are 403; a foreign
   `Host` is 403; the real page works.
3. `label`: idle timeout → exit 3, `✗ … closed after 6 seconds …`, the one
   assignment still in the session file, no `dataset/`.
4. `label`: the configured port held by the test → served on another, and
   "Port N is in use; the browser server is on M instead." printed.
5. `curate`: page and script served, an image served by ID, 3 deselections and
   the tab switch **in `curation.json`** before Confirm, Confirm → exit 0,
   `dataset/` 10+12, `curation.json` removed.
The stored form of a deselection is **not** asserted (option B under review).
Skipped in CI (web extra), with the reason printed.

### Checkpoint 4 — the live milestone
**Pass:** 3   **Date:** 2026-09-14   **Where:** `.smoke/pass3-live/`
**Method, as answered to the human:** the installed console script,
`.venv/Scripts/optica.exe`, as a **background process** (the Bash tool's
`run_in_background`, so the two-minute foreground limit does not apply), with
`HOME`/`USERPROFILE` set to a scratch home and `BROWSER='C:\Program
Files\Git\usr\bin\true.exe'` — verified first to be the head of `webbrowser`'s
try-order and to return True, since a failing `BROWSER` falls through to the real
browser (`notes/verified.md`). A driver (`scratchpad/drive.py`, httpx) read the
tokened URL from the process's own output and sent the page's requests. Nothing
in the path depends on the test suite's browser guard.

**`optica label --folder images -c cat,dog`** — `images/` holds 24 real photos
copied from pass 2's live fetch (12 `photo_c*`, 12 `photo_d*`) and one zero-byte
`empty.jpg`: 25 files.

| Observed | Value |
|---|---|
| terminal, before the browser | `! 1 file could not be read before labeling and is left out…` / `…\empty.jpg: zero bytes` |
| headline | `Labeling 24 images at http://127.0.0.1:8765/?token=…` (default port, free) |
| no key: `GET /`, `GET /api/heartbeat` | 403, 403 |
| foreign `Host` | 403 |
| tokened link | 303 → `/`, cookie `HttpOnly` and `SameSite=strict` |
| page, `shared.css`, `shared.js`, `labeling.js` | 200 ×4, title "Optica — Label" |
| state | 24 images, `1 of 24`, radio widget, unreadable notice naming `empty.jpg` |
| image 0 | 200 `image/jpeg`, 91,517 B |
| session file after 3 assignments | `9418ecd74430134e.json`, 3 entries, position `photo_c04.jpg` |
| decisions | 23 assigned (11 cat, 12 dog), 1 skipped (`photo_c12`) |
| Finish unconfirmed | `confirm`: "1 image will not be included: 1 skipped, 0 not yet reached." |
| Finish confirmed | `finished` |
| terminal after | `Copying 23 images (2.2 MB) to dataset/ — originals untouched`, `+ Labeling complete — 23 images labeled across 2 classes (1 unreadable file left out)` |
| **exit** | **0** |
| `dataset/` | cat 11, dog 12 (11 + 12 = 23) |
| session file | removed; `images/` still 25 files; port 8765 released |

**`optica curate --yes`** — scratch home seeded from `.smoke/pass2-fetch/home/.optica/`
(staging cat 12, dog 12 real Open Images photos, plus its label-map cache);
`.optica.toml` sets `images_per_class = 12`.

| Observed | Value |
|---|---|
| headline | `Curating 24 images across 2 classes at http://127.0.0.1:8765/?token=…` |
| no key, foreign `Host`, tokened link, page + 3 assets | 403, 403, 403, 303 (both cookie flags), 200 ×4 |
| state | tabs; cat 12/12, dog 12/12 |
| image `0/0` | 200 `image/jpeg`, 91,517 B |
| after 3 deselections | `curation.json` cat entries 3; cat 9 of 12; warning `cat: only 9 images selected (fewer than 10)`; Fetch More offered for 3; Confirm enabled (advisory) |
| Fetch More (live, Open Images) | requested 3, delivered 3, no error; cat 12 of 15, warning cleared |
| tab switch, Confirm | active 1; `finished` |
| mass rejection | none due (12 ≥ 10, 80%) — `--yes` had nothing to answer |
| terminal after | `+ Curation complete — 24 images selected across 2 classes` |
| **exit** | **0** |
| `dataset/` | cat 12 (`0004`–`0015`), dog 12; 12 distinct MD5 in cat |
| staging | cat `0004`–`0015` (the 3 rejected deleted), dog 12; `curation.json` removed; port released |

`—` printed as `�` in both logs: the known cp1255-file / UTF-8-reader mismatch
(pass 2), not new. **Not exercised live:** Ctrl+C at the terminal (no way to send
a console Ctrl+C to a background process here; the INTERRUPTED path is covered
by `TestServe` and the unit tests), the timeout warnings at 30 and 5 minutes
(covered with a fake clock and by integration test 3's 6-second timeout), the
mass-rejection prompt in a real terminal, and a real browser rendering the pages
— the JavaScript remains `TODO(test)`.

### Pass 3 — closed
**Date:** 2026-09-14
**Milestone — met, live.** *`optica label` and `optica curate` both start, serve
their page, and write back through their session files* (`pass-3.md` as
corrected): both ran as the installed console script in the background, served
their page and assets to an HTTP client, wrote every decision to
`~/.optica/staging/labeling/<id>.json` and `~/.optica/staging/curation.json`
respectively as it happened, copied into `dataset/` through a `.partial` sibling
on Finish/Confirm, and exited 0. No manifest was written; curate has none.
**CI:** not run by the agent. The human pushes and confirms three runners.
Expected on CI: **1187 passed, 28 skipped** (the `.smoke/ci-venv` result).

**Built:** `src/optica/server/` — `__init__.py` (docstring), `app.py`,
`routes.py`, `labeling.py`, `curation.py`, and `static/` (`shared.css`,
`shared.js`, `labeling.html`, `labeling.js`, `curation.html`, `curation.js`);
`optica label` and `optica curate` end to end in `cli/classify.py`; in `input/`,
`partial_destination`, `commit_dataset`, `staged_queries`, `fetch_more`,
`fetch_more_refusal`, `fetch_more_shortfall`, and option B in `sessions.py`;
`utils/prompts.choose`, `utils/logging.incomplete`; the browser guard and the
loopback allowance in `tests/conftest.py`.

**State:** `.venv` (web extra) **1249 passed, 14 skipped** — 1263 collected;
`.smoke/ci-venv` (Core + `[test]`) **1187 passed, 28 skipped** — 1215 collected.
Skips: 14 = 13 from pass 2 + 1 `_NO_LOGIC` (`server/__init__.py`); 28 = those 14
+ 1 `test_routes.py` module + 8 `TestServe` + 5 integration. Collections differ by
48 = `test_routes.py`'s 49 − 1. Pass 3 added 1263 − 879 = **384** tests to the
suite collected at pass 2's close (879). Ruff clean and mypy `strict` clean on 73
files in both environments. `TODO(test)` markers in `src/`: **6** (2 from pass 2:
Flickr, rare-class cost; 4 from pass 3: keypress, the three page scripts).

**Commits this pass: 21** (`4a76394..HEAD`, this entry's included) — 9 `feat`,
2 `fix`, 1 `test`, 9 `docs` (9 + 2 + 1 + 9 = 21):

| # | Commit | Kind |
|---|---|---|
| 1 | `docs(verified)`: FastAPI 1.0, web extra, uvicorn, port binding | docs |
| 2 | `feat(server)`: lifecycle and shared routes | feat |
| 3 | `feat(server)`: shared styles and behaviour | feat |
| 4 | `docs(build-log)`: checkpoint 1 | docs |
| 5 | `docs(build-log)`: real-Click consequence; session key for ratification | docs |
| 6 | `feat(utils)`: choice prompt, incomplete line | feat |
| 7 | `feat(input)`: commit a finished dataset | feat |
| 8 | `feat(server)`: labeling page | feat |
| 9 | `feat(cli)`: `optica label` | feat |
| 10 | `docs(build-log)`: checkpoint 2 | docs |
| 11 | `fix(tests)`: refuse real browser launches | fix |
| 12 | `feat(input)`: Fetch More bridge | feat |
| 13 | `feat(server)`: curation page | feat |
| 14 | `feat(cli)`: `optica curate` | feat |
| 15 | `docs(build-log)`: checkpoint 3, stray browser launch | docs |
| 16 | `docs(build-log)`: stored-deselection proposal | docs |
| 17 | `fix(sessions)`: rename no longer reselects (option B) | fix |
| 18 | `docs(build-log)`: option B shipped; Start-fresh open question | docs |
| 19 | `test(server)`: label and curate over a real socket | test |
| 20 | `docs(verified)`: webbrowser fall-through, wheel, live Fetch More | docs |
| 21 | `docs(build-log)`: checkpoint 4 and pass 3 close | docs |

**Handed forward:**

| To | Item | Recorded in |
|---|---|---|
| **Amendment session before pass 4** | **Option B**, provisional: deselections matched by class and file name; format unchanged | "Stored deselections are matched by class and file name — option B, provisional" |
| **Amendment session** | **Open question:** fetch's Start fresh leaves a class's deselections behind | "Open question — fetch's 'Start fresh' leaves that class's deselections behind" |
| **Amendment session** | **Session key** (`Host` check + cookie) — kept, to ratify; not extended | "Browser session key…" (status line) |
| **Amendment session** | Proposed plan change: CI installs the web extra, so route and integration tests run on the runners | "Route tests cannot run in CI as the plan stands" |
| **Human** | Proposed wording for plan l.1016 (option B) — a proposal; `spec/` untouched | "Proposed plan change — how a stored deselection survives…" |
| **Pass 4** | Truncated JPEGs: whether pre-flight sees one depends on the image (measured table); expect decode errors at training | "Truncated JPEGs: whether pre-flight sees one depends on the image" |
| **Pass 4** | Fetch More refuses grouped blocklist classes until `input/clip.py` exists | "Fetch More, in the browser and at the F of F/C/A" |
| **Pass 5** | `optica run` sequences label/curate: reuse `_label_body`/`_curate_body` shapes; re-read curation Start fresh (standalone keeps the images) and the web-extra entry check; the API must not call `protect_streams` | "Curation 'Start fresh' deletes `curation.json`…"; pass 2 close |
| **Pass 5 / 6** | `choose()` exists for imbalance F/C/A and run R/C/S | "`utils/prompts.py` gains `choose()`" |
| **Any pass with a console** | Keypress resets the timer; Ctrl+C at a live terminal; the pages in a real browser (JS `TODO(test)`) | this entry, "Not exercised live" |
| **Human** | `.smoke/ci-venv/`, `.smoke/pass3-live/`, `.smoke/wheel/` are this pass's throwaway directories | — |

**Entries logged this pass: 39** `###` entries under "## Pass 3", counted with
`grep -c "^### "` — checkpoint 1: 12; checkpoint 2: 10; checkpoint 3: 9; after
checkpoint 3: 4 (the stored-deselection proposal, the `BROWSER` mechanism,
option B, the Start-fresh open question); checkpoint 4: 4 (loopback guard,
integration tests, live milestone, this close). 12 + 10 + 9 + 4 + 4 = 39. Not
counted: 2 edits to existing entries made at the human's request (the
real-Click consequence, the session key's ratification status).

**Pass 3 is complete.** Next: the plan-amendment session, then pass 4.

### Plan amendment session 2 — the six open items decided
**Pass:** between 3 and 4   **Date:** 2026-09-14   **Where:** `spec/optica-plan-v1-core.md`
**What this is:** the outcome of the second out-of-repo plan-amendment session,
recorded here so a later pass reading the six proposals above can tell which
landed. The `spec/` edits were applied by the user, not by an agent.

| # | Item | Disposition | Sites |
|---|---|---|---|
| 12 | Class-name rule 1 misses trailing dots, spaces, control characters | **Amended** | l.242 |
| 13 | Route tests cannot run in CI as the plan stands | **Amended** — with 16, one edit pair | l.132 |
| 14 | Browser session key — `Host` check and session cookie | **Ratified** — behaviourally | l.887, l.1700 |
| 15a | A stored deselection and a class-folder rename | **Ratified — option B** | l.1016, l.1012 |
| 15b | "Start fresh" leaves that class's deselections behind | **Amended** — accepted limitation; fix is fast-follow | l.1020 |
| 16 | Install the web extra in CI | **Amended** — with 13 | l.132 |

**Item 12 — the plan now leads the code, and no pass owns the catch-up.** l.242
excludes names containing U+0000–U+001F and names ending in `.` or a space.
`src/optica/input/classes.py:class_name_problem` implements the pre-amendment
list, so for the first time in this run a shipped module and the plan disagree.
Two predicates and their tests close it, as that entry's *Reversible?* line
already says. Pass 4 does not touch `input/` validation, so this needs an owner
assigned rather than inherited.

**Item 12 — correction to the agenda's framing.** The session prompt and the run
record's §4 both describe the gap as one *"the `_x` collision suffix would not
catch"*. `_x` is the staged-filename suffix at plan l.680 and the
checkpoint/export folder suffix at l.1093 and l.1216; it never applies to a class
folder. The mechanism that should catch `cat.` against `cat` and does not is
**rule 2 at l.243**, which compares case only. Nothing downstream depends on the
wrong framing, but it is in two documents and this is the correction of record.

**Items 13 and 16 — what the workflow change must preserve.** l.132 now sanctions
`optica[web]` on at least one leg **and** requires that at least one leg install
no extras at all. Two things must stay true after the workflow is edited. The
extras-free leg is what keeps the import-time contract (l.1417) under continuous
check, along with pass 3's FastAPI-free modules and `server/__init__.py` staying
logic-free. And a stray `import click` under `src/optica/` must still fail
somewhere: on a leg with the web extra it will not, because uvicorn brings real
Click (`notes/verified.md` § *What `optica[web]` resolves to*). The 27 tests that
skip today — 19 route, 8 `TestServe` — run on whichever leg installs the extra.
Leg count does not change. The arrangement is not specified by the plan and was
not this session's to specify.

**Item 14 — no code change, and a new stop.** The `Host` check and the session
cookie are now what l.887 and l.1700 describe, at the level of the rule rather
than the mechanism: only the session Optica itself opened can drive the server.
The mechanism stays here rather than in the plan, on the same reasoning that
removed an API name from l.220 in the first session. l.887 also now states that
these two guards are the whole of V1's browser-security surface, which makes
anything further a plan-level stop rather than an implementing pass's call —
the disposition that entry asked for.

**Item 15a — B is the plan's reading, and the stored form is settled.** l.1016
states the class-plus-file-name match. What is written is unchanged: full paths,
`"version": 1`, the shape at l.1010–1014. Pass 3's deferral — that checkpoint 4's
integration tests would not assert the stored form until this was decided — is
lifted; the stored form may now be asserted. Option A was rejected because a
version-1 file read under A matches nothing, which is this same defect in a new
form, so it needs `"version": 2`; l.1006 makes that a hard error telling the user
to delete the file, costing them every deselection they had. Writing a migration
instead is V1 functionality.

**Item 15a, incidental.** l.1012's example entry read `…IMG_0007.jpg`, a name
auto-fetch staging cannot produce — l.797 numbers staged images `0001.jpg`
upward and l.1008 scopes curation to auto-fetch staging. Now `…0007.jpg`.

**Item 15b — recorded, not fixed.** l.1020 carries an accepted-limitation
sentence: Start fresh does not clear that class's entries in `curation.json`, so
a deselection recorded before a start-fresh applies to whichever new image takes
the reused name, and that image opens already deselected. All three candidate
fixes are V1 functionality and go to the fast-follow. A later pass should not
close it opportunistically — having fetch clear curation's state is the coupling
option C was rejected for.

### `CLAUDE.md`'s Click note did not cover the web extra
**Pass:** between 3 and 4   **Date:** 2026-09-14   **Where:** `CLAUDE.md` § "Settled points that the plan leaves implicit"
**Found:** the 13 September correction says Typer vendors Click and that
`import click` fails in a Core install. True, but incomplete. Pass 3 checkpoint
1 established that `optica[web]` pulls real Click transitively through uvicorn,
so under the web extra `import click` **succeeds**. The failure stops being
loud: a mistaken `except click.UsageError` compiles, runs, and silently never
fires, because Typer still raises the vendored `typer._click` one.
**Action taken:** appended to the same paragraph rather than rewriting it. The
instruction is unchanged — never `click.*`, use `typer`'s equivalents. Only the
failure mode is now stated accurately for both install shapes.
**Why it matters more after 14 September:** amendment item 16 sanctions
`optica[web]` on at least one CI leg, so real Click will be present in a test
environment. The same amendment requires at least one leg to install no extras
at all, which is what keeps a stray `import click` under `src/` failing
somewhere. Pass 6 owns the arrangement.
**Provenance:** the consequence was raised at pass 3 checkpoint 1 and logged by
that pass. The companion session undertook to make this edit at the pass 3
boundary and did not; it was surfaced again by amendment session 2's addendum
edits and supplied on 14 September. Recorded because a dropped handoff is worth
seeing in the record, not only its repair.

## Pass 4

### Pass 4 opened — checkpoint 0, the amended class-name clauses
**Pass:** 4, checkpoint 0   **Date:** 2026-09-15   **Where:** `src/optica/input/classes.py`
**Assigned deliberately outside pass 4's scope:** the 14 September amendment to
l.242 added two exclusions no pass owned — control characters U+0000–U+001F and
names ending in `.` or a space.
**Done:** both predicates in `class_name_problem()`. Every surface reaches it
through `normalize_class_names()` (`-c` in `cli/classify.py`, the manifest
column and folder names in `input/local.py`, the blocklist definitions), so no
caller changed. Check order: after the comma check for control characters, after
the leading-`-` check for the trailing clause, so an all-dots name like `..`
keeps its path-component reason rather than the trailing-dot one.
**Range decided literally:** the plan says U+0000–U+001F, so DEL (U+007F) is
accepted. Windows permits it in file names. A test pins both boundaries.
**Bite proven:** removing the control-character check fails 7 tests; removing the
trailing check fails 6. Restored, 141 pass.

### Found at checkpoint 0 — logged, not fixed
**Pass:** 4, checkpoint 0   **Date:** 2026-09-15

1. **`tests/integration/test_exit_codes.py::TestMilestone::test_no_torch_is_importable_in_this_environment`
   now fails locally.** It asserts that `import torch` fails in the running
   interpreter — it inherits the torch-less condition rather than constructing
   it, and torch is now installed in `.venv` for this pass. It still passes in
   CI, which never installs torch, so CI is not red. The pass 1 milestone it
   guards (`optica --version` with no torch) would be better tested by
   constructing the condition: run `--version` in a subprocess with a
   `sys.meta_path` finder that refuses `torch`, and assert success. Not changed
   here — checkpoint 0 is scoped to the class-name rule.
2. **`ruff format --check` reports 16 files that would be reformatted**, all
   untouched by this pass (`cli/classify.py`, `cli/config.py`, `cli/main.py`,
   `config/`, and ten test files). CI runs `ruff check` only, which is clean.
   Format drift has been accumulating unenforced since at least pass 3. Pass 6
   owns CI; whether to enforce formatting is its call.

### The torch milestone test now constructs its condition
**Pass:** 4, before checkpoint 1   **Date:** 2026-09-15   **Where:** `tests/integration/test_exit_codes.py::TestMilestone`
**Found:** `test_no_torch_is_importable_in_this_environment` asserted that
`import torch` fails in the running interpreter — an ambient fact about the
machine, and the sixth instance of that defect in this build (after
`running_in_venv` in pass 1 and `FORCE_COLOR` in pass 2). It failed locally once
torch was installed for pass 4. Its sibling `test_version_runs_without_torch`
had the same defect in quieter form: it ran `--version` under whatever torch the
interpreter happened to have, so it only checked the milestone while the venv
was torch-less. Both are replaced; neither is deleted or skipped.
**Now:** both construct the torch condition inside the subprocess and assert
the construction took before driving the app.
- `test_version_runs_with_the_torch_stack_absent` — every finder on
  `sys.meta_path` is wrapped so `torch`, `torchvision`, `timm`, `sklearn` and
  `open_clip` are not found (`find_spec` → None, import → ModuleNotFoundError,
  as on a machine that never installed them). Asserts `--version` exits 0.
- `test_version_never_imports_the_torch_stack` — a recording fake of each of
  those five packages is put first on `sys.path` so the stack is *present*,
  shadowing any real one. After `--version`, asserts no module of the stack is in
  `sys.modules`. This is the one that catches an import guarded by
  `except ImportError`, which absence alone cannot see. The fake prints the
  importing stack, so a failure names the importer. `importlib.util.find_spec`
  alone does not load the fake, so detection without import stays legal.
**Bite proven, on both kinds of machine.** Mutations to `cli/main.py`, each
restored afterwards (`git status` clean in `src/`):

| Mutation | `.venv` (torch 2.14.0 present) | scratch venv, Python 3.11.9, Core + test only, `find_spec` None for all five |
|---|---|---|
| none | 3 pass | 3 pass |
| top-level `import torch` | absent + never-imports fail | absent + never-imports fail (+ console-script test) |
| top-level `try: import timm / except ImportError` | never-imports fails | never-imports fails |
| `try: import torchvision` inside `_version_callback` | never-imports fails | not run |

The torch-less row is what the old tests could not do: in CI a guarded import
would have passed both of them silently. The scratch venv was
`python3.11 -m venv` in the session scratchpad plus
`pip install -e "C:/dev/optica[test]"`; it touched nothing in the repo.

### `open-clip-torch` installed into `.venv`
**Pass:** 4, checkpoint 1   **Date:** 2026-09-15   **Where:** `.venv`
**Found:** the human installed the torch stack (torch, torchvision, timm,
scikit-learn) but not `optica[clip]`'s `open-clip-torch`, which checkpoint 1's
`input/clip.py` needs to run at all.
**Decided:** installed `open_clip_torch-3.3.0` from its PyPI wheel after a
`pip install --dry-run` showed it would add only `ftfy 6.3.1`, `regex
2026.9.10`, `wcwidth 0.8.3` and itself — no change to torch 2.14.0+cu130,
torchvision 0.29.0+cu130 or timm 1.0.29, all re-checked after the install.
**Why not a stop:** it is the extra the plan names for this module, not the
torch stack the pass instruction reserved for the human, and it is reversible
with one `pip uninstall`. **Reversible?** Yes.

### CLIP Adapter — what the plan leaves open, and what was assumed
**Pass:** 4, checkpoint 1   **Date:** 2026-09-15   **Where:** `src/optica/input/clip.py`, `src/optica/cli/classify.py`
1. **Which survivors clip mode keeps.** The plan keeps "up to
   `images_per_class`" of what passes. Kept: the highest-scoring, ties by path.
2. **Pass is `score >= clip_threshold`** — the plan discards "whatever scores
   below". Boundary pinned by a test.
3. **A grouped class's score is its best sub-term.** The plan says each image
   is scored against all sub-terms and keeps its label; `max` is the only
   reading under which one matching sub-term is enough.
4. **Clip mode's staging is consumed.** It fetches into staging (so an
   interrupted clip fetch resumes like any other), scores, writes survivors to a
   hidden sibling of `dataset/`, commits in one move, and only then deletes that
   run's class staging. A failure or interrupt before the commit leaves the old
   dataset untouched and the candidates staged.
5. **An empty class after filtering still gets its folder** in `dataset/`, so
   training's floor check names it rather than the class silently vanishing.
6. **The destination check is the first thing `_fetch_body` does under
   `--mode clip`** — before the client, the label index, any prompt for work.
   `fetch` had a `--dataset` flag and an `--overwrite` flag already.
7. **CLIP loads before the first image is fetched,** not after — the 605 MB
   weights download and the verification happen before any quota is spent.
   The plan's "check before any action" principle, applied to a load.
8. **The grouped path under curate is not over-fetched.** The plan's × 2 is
   stated for clip mode; under curate a person selects afterwards. Rejected
   images are deleted from staging (auto-fetched, per the deletion rule), and
   the count is reported per class.
9. **Weights verification is Optica's, against a pinned size + SHA-256.**
   open-clip resolves `openai` through the Hugging Face Hub (hard dependency),
   and neither it nor `hf_hub_download` hashes a cached file. On Windows without
   Developer Mode the Hub cache keeps no content-addressed blob, so the hash
   cannot be read from the cache layout either (`notes/verified.md`). Repair is
   delete + one forced re-download; still wrong → `OpticaCLIPLoadError` naming
   the path. A slow test fails if an open-clip upgrade changes the file the tag
   resolves to.
10. **Fetch More still refuses grouped classes.** Lifting it needs a per-sub-term
    top-up target (`fetch_class` takes one `per_query`, and the sidecar's
    per-query `delivered` counts include images CLIP later removed) and the model
    loaded inside the curation server's worker thread. The refusal text no longer
    claims CLIP filtering is absent from the build. → **pass 5 or the human.**
11. **Device selection lives in `clip.py` for now** (`select_device`: CUDA, then
    MPS, then CPU). Checkpoint 2's training engine needs the same choice; it
    decides whether to share it.
**Reversible?** Each is local to one function.

### The MPS path is written and never run
**Pass:** 4   **Date:** 2026-09-15   **Where:** `src/optica/input/clip.py:select_device` (and, from checkpoint 2, `training/`)
This machine has an NVIDIA GPU (CUDA 13.0) and no Apple silicon. The MPS branch
is exercised only by a test that monkeypatches `torch.backends.mps.is_available`
to True and asserts the device *type* chosen — no tensor has ever been placed on
an MPS device by this build. Marked `TODO(test)`. **Do not read the passing
`TestDevice::test_mps_when_only_mps_is_available` as MPS coverage.** The CUDA
path is genuinely exercised: the live clip fetch below scored on
`torch.device("cuda")`.

### Two more tests read the shared `sys.modules`, and pass 4 is what broke them
**Pass:** 4, checkpoint 1   **Date:** 2026-09-15   **Where:** `tests/unit/utils/test_system.py::TestNoTorch`
**Found:** `assert "torch" not in sys.modules`, twice, in the pytest process.
Passed while nothing in the suite imported torch; failed as soon as
`tests/unit/input/test_clip.py`'s slow tests did, earlier in the same run.
Seventh and eighth instances of the ambient-fact defect.
**Fixed:** each now runs in a fresh interpreter with a recording fake `torch`
first on `sys.path` (asserted to be the one found), and reports the torch
modules loaded. The detection test is parametrized over both `nvidia-smi`
branches. **Bite:** a guarded top-level `import torch` in `utils/system.py` fails
all three, and a guarded lazy one in `detect_gpu` fails the two detection cases,
in `.venv` and in the torch-less scratch venv alike. Restored: 3 pass.

### My own new CLI tests inherited the clip extra — caught by the torch-less venv
**Pass:** 4, checkpoint 1   **Date:** 2026-09-15   **Where:** `tests/unit/cli/test_fetch_command.py::TestClipMode`, `TestGroupedUnderCurate`
**Found:** all 29 fetch-command tests passed in `.venv` on the first run. In the
torch-less scratch venv — CI's shape — the 8 new ones failed: `fetch --mode clip`
checks `clip_available()` at entry, which is True in `.venv` only because
open-clip is installed there. Exactly the defect the standing rule names; it
would have turned CI red on all three runners.
**Fixed:** a `clip_installed` fixture sets `clip_available` to True, and the
`scorer` fixture depends on it. Now 1246 pass / 0 fail in the torch-less venv
with `-m "not slow"`, and 1316 pass in `.venv` with slow included.
**Rule applied going forward:** every pass-4 test suite is run in both venvs
before commit.

### Proposed plan change — the CLIP load call needs `force_quick_gelu=True`
**Pass:** 4, checkpoint 1   **Date:** 2026-09-15   **Where:** plan § "CLIP Adapter (clip mode)", the code line under "hardcoded in V1" (l.848); `src/optica/input/clip.py:MODEL_KWARGS`
**Found:** the plan's line
`open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai')` builds
ViT-B-32 with standard GELU in open-clip 3.3.0 and loads the QuickGELU-trained
openai weights into it, raising only a `UserWarning`. Measured on 120 verified
Open Images images: 22 of 120 own-class scores cross `clip_threshold = 0.25`
between the two builds (`notes/verified.md`). The plan says the threshold is
calibrated for "this model, these weights" — the bare call is not quite that
model.
**Done in code:** the call is made with `force_quick_gelu=True`. Model name,
weights tag and template are unchanged. My earlier docstring claim that the tag
"carries QuickGELU" was wrong, and the slow test I wrote for it checked the tag's
config rather than the model built; both corrected. A slow test now asserts the
built model contains `QuickGELU` modules; a CI-safe test asserts `load_clip`
passes the kwarg (removing it fails that test); a slow test fails if open-clip
ever starts applying the tag's activation itself.
**Proposed wording** (for the human; `spec/` untouched):
```python
model, _, preprocess = open_clip.create_model_and_transforms(
    'ViT-B-32', pretrained='openai', force_quick_gelu=True)
```
followed by: "*`force_quick_gelu=True` is part of the model: the openai weights
were trained with QuickGELU, and open-clip does not apply that from the tag — it
warns and builds GELU.*"
**Why not a hard stop:** checkpoint 1 ends here, so the report is the stop. The
code follows the plan's stated intent (this model, these weights), and reverting
it is one kwarg.

### Finding for the human — 0.25 sits inside the true-positive score range
**Pass:** 4, checkpoint 1   **Date:** 2026-09-15   **Where:** plan § "CLIP Adapter", Implementation Note 6
Not a code change. On Open Images' human-verified Cat and Dog images, the
correct-class cosine score (QuickGELU build) averaged 0.2587 and 0.2500, ranging
0.1801–0.3059 and 0.1737–0.2915. At 0.25, clip mode discarded 15 of 60 genuine
cats and 29 of 60 genuine dogs, and 4 of 60 cats also scored ≥ 0.25 against "a
photo of a dog". The 2× over-fetch still filled `images_per_class` in both
post-fix live runs. Two classes from one source are not a calibration study;
recorded so that a later recalibration starts from numbers.

### Open — the Hub's unauthenticated-request warning prints twice on every CLIP run
**Pass:** 4, checkpoint 1   **Date:** 2026-09-15   **Where:** `input/clip.py:load_clip` (the HEAD request inside `hf_hub_download`)
Every live run, cached or not, printed "You are sending unauthenticated requests
to the HF Hub..." once through `warnings` and once through stdlib logging. Not
actionable for most users; noise on stderr. **Left for checkpoint 2**, because
timm's pretrained weights come from the same Hub and one decision should cover
both. The QuickGELU warning is gone with the fix.

### Checkpoint 1 — state
**Pass:** 4   **Date:** 2026-09-15
**Built:** `input/clip.py`; `fetch --mode clip` and the grouped path under curate
in `cli/classify.py`; Fetch More's grouped refusal re-worded in `input/curation.py`.
**Tests:** `.venv`, slow included: 1320 passed, 14 skipped. Torch-less scratch venv (CI's
shape), `-m "not slow"`: 1248 passed, 28 skipped, 10 deselected. Ruff and mypy clean in both. Mutation checks:
12 of 12 bite (11 in `scratchpad/mutate_clip.py` plus dropping `MODEL_KWARGS`).
**Live:** three `fetch --mode clip` runs on CUDA, table in `notes/verified.md`.
**Not run live:** the grouped path's scoring (fake scorer only); the weights
repair path (constructed files only — no real corrupt download was staged);
MPS.
**Next:** checkpoint 2, `training/`.

### `.venv` audited against the declared extras
**Pass:** 4, before checkpoint 2   **Date:** 2026-09-15   **Where:** `notes/verified.md` § "What `.venv` holds…"
Requested by the human after checkpoint 1's `open-clip-torch` install. Result:
Core, `[web]`, `[clip]`, `[all]`, `[test]` and the setup-owned torch stack all
fully installed and in range; no partial extras; only `pip` reached by no root.
One finding worth pass 5 and `CLAUDE.md`'s owner: **real Click arrives with the
torch stack**, through `huggingface_hub 1.31.0`'s unconditional
`click<9.0.0,>=8.4.2` (required by timm and open-clip), not only through
`[web]`'s uvicorn. `CLAUDE.md` is not edited here.

### Checkpoint 2 — what the plan leaves open in `training/`, and what was assumed
**Pass:** 4, checkpoint 2   **Date:** 2026-09-15   **Where:** `src/optica/training/`, `src/optica/cli/classify.py:train`

**Decided because the human asked for a decision:**

1. **mobilenet's `conv_head` is unfrozen in Phase 2.** `mobilenetv3_large_100`'s
   `conv_head` (1,230,080 params, 29% of the model) sits after `global_pool`;
   `norm_head` is an `Identity`. Read literally, l.1063's "last 3 blocks" leaves
   it frozen in both phases, so Phase 2 fine-tunes `blocks.4–6` through a fixed
   ImageNet projection. One rule now covers all four rows: *the named blocks, and
   every parameterised module after them up to the classifier* — exactly the
   amended efficientnet rows (`conv_head` + `bn2`), exactly `layer4` for resnet50,
   and `+ conv_head` for mobilenet. The literal reading was rejected because the
   14 September amendment added `bn2` for the same reason: a frozen layer between
   trainable ones. **For the amendment session** — proposed l.1063 cell:
   "Last 3 blocks (`blocks[4]`–`blocks[6]`) + `conv_head`". Test:
   `test_models.py::test_mobilenet_phase2_includes_conv_head_and_not_blocks_3`.

**Assumed under the gap rule (log and continue):**

2. **Frozen BatchNorm stays in eval mode.** Train mode would rewrite running
   statistics of frozen layers from tiny batches. Test asserts `bn1`'s running
   mean does not move.
3. **Float floors take a 1e-9 tolerance** (splits and phase allocation):
   `100 × 0.29 = 28.999999999999996`, `20 × (1 − 0.9) = 1.9999999999999996`.
   The plan states exact arithmetic; a bare `math.floor` would give 28 and 1.
4. **Early stopping in Phase 1 ends Phase 1, not the run**, and fine-tuning
   begins; in the last existing phase it ends the run, and only that sets
   `early_stopped`. The plan says each phase has its own window and that
   `early_stopped` means the run ended on patience. Recorded in the log as
   `phase1_stopped_early`; the completion block's Phases line says so.
5. **A checkpoint folder holds `checkpoint.pt`** = `{state_dict, optimizer_state}`,
   tensors and primitives only, loadable `weights_only=True`. The plan names only
   `checkpoint_info.json`.
6. **`checkpoint_info.json` carries the six preprocessing values too**, so export
   copies what training used instead of re-resolving with a possibly newer timm —
   the plan's own reason for exporting them. **Its `config` block adds**
   `optimizer`, `train_split`, `val_split`, `test_split`, `max_checkpoints`: a
   resume must reproduce the split, and `random_state` alone cannot.
7. **Accuracy in folder names is three decimals** (`checkpoint_val0.852_epoch7`),
   as every plan example shows.
8. **Top N is per run**, same ordering as export ranking; an epoch tying the worst
   retained one replaces it (higher epoch wins ties). Test evaluation runs only
   when a checkpoint is saved.
9. **`interrupted_at_epoch` is the epoch in progress** (completed + 1). The resume
   prompt reads it from the run's log (`log_file`), because
   `checkpoint_info.json` does not carry it; falls back to the checkpoint epoch.
10. **Resume continues from the newest interrupted checkpoint's epoch** — epochs
    after it that were not top-N are trained again. It uses the checkpoint's
    `config` block and model family, warns naming any flags given, keeps the
    `run_id`, refuses when the classes or `training_data_hash` changed (the split
    would silently re-mix), and on completion clears `interrupted` from every
    retained checkpoint of the run.
11. **Class weights: `total / (num_classes × count)` on the training split** —
    what the loss sees.
12. **Validation and test losses use the same (possibly weighted) criterion**
    the run trains with, so early stopping monitors what is optimised.
13. **Augmentation** — `Resize(floor(input/crop_pct))` → `RandomCrop` → flip
    p=0.5 → rotation ±15° → `ColorJitter(0.2, 0.2, 0.2)`. The plan names the four
    operations and ±15° only.
14. **`num_workers = 0`** on every platform: Windows spawn re-imports the entry
    point; one behaviour everywhere.
15. **Standalone `optica train` offers C/A at the imbalance warning, never F** —
    it cannot tell whether a dataset came from a fetch, and "on a dataset the user
    brought" is the conservative reading.
16. **The `--epochs 1` confirmation fires for any ratio strictly between 0 and 1**
    that leaves Phase 2 empty — only reachable at `epochs = 1`. N exits 3.
17. **`--output` is always a container for `optica train`**: absent → "Create
    it? [Y/n]" (`--yes` Y), a file → hard error. The export table's N/C/A
    name-versus-container prompt has nothing to decide when only the log is
    written. Export (checkpoint 3) implements the full table.
18. **Order of the command:** dataset shape and `--classes` typo (no torch) →
    `import_torch_stack` → `--output` → resume → K/A/D/S + soft limit → subset
    confirmation → manifest copy → pre-flight/dedupe/floor → imbalance → ratio
    warnings, `--epochs 1` → CPU batch size → **K/A/D/S action** → train. The
    archive/delete runs last, so a later refusal leaves checkpoints untouched.
19. **`train --manifest`** validates full labeling and runs the `dataset/`
    destination check first; the copy runs after every question.
20. **A decode failure at training** raises `OpticaTrainingError` naming the file
    (pass 3 handoff: header pre-flight passes some truncated JPEGs).

**Modules added to the plan's tree:** `training/data.py` (dataset and loaders),
`training/runlog.py` (the log), `training/trainer.py` (one classification run —
where pass 5's API will call in), `utils/mlstack.py` (lazy torch-stack import,
device selection moved out of `clip.py`, Hub handling). None imports torch at
module level; the pass 1 milestone tests (constructed torch presence) still pass.

**Not added:** timm weights get no first-use notice or verification, unlike
CLIP's — the plan specifies both for CLIP and neither for timm, and timm's own
download shows a progress bar.

**Reversible?** Each is local to one function or constant.

### Four more ambient-state tests, three of them mine
**Pass:** 4, checkpoint 2   **Date:** 2026-09-15
1. **`tests/unit/cli/test_classify.py`** — four pass-1 tests invoke bare
   `optica train` expecting an error. That error used to be the stub; now it is
   "no dataset", which holds only while the **repo root** has no `./dataset/`.
   They now take `project_dir` (an empty project). Found because the first
   version of `_train_body` imported torch before checking the dataset, which
   leaked torch into the pytest process and failed `test_main.py`'s and
   `config/test_init.py`'s `"torch" not in sys.modules` tests — those two are the
   same shared-`sys.modules` defect as `test_system.py`'s, fixed only indirectly
   here (torch now loads after the dataset check). **Logged, not rewritten:** they
   still read ambient `sys.modules` and will fail again the day any fast test
   imports torch in-process. The subprocess form in `test_system.py` is the fix.
2. **`test_mlstack.py::test_a_server_warning_prints_once_not_twice`** (mine)
   passed alone and failed in the suite twice over: an earlier `--quiet` left the
   root logger at ERROR, and earlier CLI tests left root handlers on closed
   capture streams. It now sets the Hub logger's level and replaces the root's
   handlers.

### `ImageListDataset` / `DataLoader` and the stubs
**Pass:** 4, checkpoint 2   **Date:** 2026-09-15
Pass-4 stubs resolved: `test_defaults.py::test_finetune_ratio_extremes_warn` is
real; `test_prompts.py`'s K/A/D/S and CPU batch-size stubs are replaced by a
pointer to `test_train_command.py::TestCheckpointHousekeeping` and
`TestCpuBatchSize`, which exercise them through the command. Still stubs:
`test_classify.py::test_checkpoint_rank_absence_prompts_rather_than_meaning_rank_1`
(export — checkpoint 3) and `test_run_checks_required_extras_up_front` (pass 5).

### Checkpoint 2 — state
**Pass:** 4   **Date:** 2026-09-15
**Built:** `training/` — `splits.py`, `models.py`, `transforms.py`,
`checkpoints.py`, `runlog.py`, `data.py`, `engine.py`, `trainer.py`;
`utils/mlstack.py`; `optica train` in `cli/classify.py`. `select_device` moved
from `input/clip.py` to `utils/mlstack.py`; the MPS entry above now points there.
**Tests:** `.venv`, slow included: 2118 passed, 12 skipped (2130 collected).
`.venv`, `-m "not slow"`: 2045 passed, 12 skipped, 73 deselected (2130). Torch-less
scratch venv, `-m "not slow"`: 1983 passed, 26 skipped, 73 deselected (2082
collected — module-level skips of the web-extra modules count once there). Ruff
clean; mypy clean in both venvs.
**Mutation checks — 27 mutations; 26 bit on the first run, 27 after one test was
rewritten** (`scratchpad/mutate_train.py`, each run against the named test files,
source restored after each):

| Area | Mutations | Bite |
|---|---|---|
| splits and hash | n_val minimum; float tolerance; OS separators | 3 / 3 |
| phase allocation and loop | phase1 minimum; Phase 2 LR; boundary reset; `<=` on improvement; `early_stopped` on a Phase 1 trip | 5 / 5 |
| models | `bn2` dropped; mobilenet `conv_head` dropped; frozen BN in train mode | 3 / 3 |
| checkpoints | epoch tie-break; timestamp tie-break; archive in collision check; run end keeps `interrupted` | 4 / 4 |
| trainer | top-N never evicts; class-weight formula; interrupt unmarked; resume without weights | 4 / 4 |
| transforms, data | round vs floor; decode error unwrapped | 2 / 2 |
| CLI | housekeeping acts at the prompt; CPU prompt not SAFETY; duplicates kept; torch before dataset checks; changed dataset resumes; **K/A/D/S not skipped on resume** | 6 / 6 |

**The K/A/D/S-on-resume mutation survived the first run:** the test asserted
the menu's absence under `--yes`, where `choose()` answers without printing it.
Rewritten to run interactively and record every question; re-running that
mutation alone now fails it (1 failed, 47 passed; restored, 48 passed). Totals:
3 + 5 + 3 + 4 + 4 + 2 + 6 = 27.
**Live:** one smoke run (`notes/verified.md`), not the milestone.
**Not exercised:** MPS; CPU training end to end on this machine (tests run the
trainer on `torch.device("cpu")` with `pretrained=False` — the CLI's CPU path is
tested with a fake trainer); `train --manifest` against the real trainer; a real
Ctrl+C at a terminal (interruption is raised from the reporter in tests).
**Next:** checkpoint 3, `export/`.

### Incident — `export` and `run` were deleted from `cli/classify.py` mid-checkpoint 2
**Pass:** 4, checkpoint 2   **Date:** 2026-09-15   **Where:** `src/optica/cli/classify.py`   **Recorded:** at the start of checkpoint 3, at the human's request — it should have been logged when it happened.
**What happened:** to remove two helpers I had just written (`_log_interrupted_epoch`,
`_patience_of`), a scratch script sliced the file with
`t[: t.index("def _patience_of(")]` — *to end of file*. `_patience_of` was the
last function of the new `train` block, but the pre-existing `export` and `run`
commands followed that block, so they went too. The same session then ran
`ruff check --fix`, which removed the now-unused `MODES` import — the auto-fix
erased evidence of the deletion.
**What caught it: the test suite, before any commit.** The next fast run failed
`tests/unit/cli/test_classify.py::TestCommandSurface::test_the_flat_alias_exists[run]`
and `[export]` (pass 1's command-surface test: `assert name in _commands()`).
After restoring the two commands from `git show HEAD`, `ruff check` reported
`F821 Undefined name MODES` in `run`, which is how the `--fix` removal surfaced.
Scope was then confirmed by hand — an AST comparison of top-level definitions
against HEAD (none missing) and `git diff HEAD` showing only the three stub lines
deleted. **That last step was attention, not a control.**
**What would not have been caught:** the command-surface test covers the
registered commands only. A private helper deleted the same way would fail only
if a test imports or calls it, or ruff F821 sees a reference to it. Deleted code
that is neither referenced nor tested — a docstring, a comment carrying a
decision, a branch inside a surviving function — passes the suite, ruff and mypy.
**What controls it now:**
1. **The command-surface test** (pass 1) — unchanged, and it did its job.
2. **No more unbounded slices in edit scripts.** Every scripted edit from here
   uses exact-match replacement with a count assertion (`s.count(old) == 1`) —
   the form every other edit in this pass already used. A removal is bounded by
   both ends of the text removed.
3. **`ruff check --fix` is not run on a dirty tree.** Plain `ruff check` reports;
   fixes are applied by hand, so a fix cannot remove the trace of a mistake.
4. **Before every commit, `git diff --cached --numstat` is read against intent**
   — a file whose deletions exceed what the change should delete is stopped.
   This is a procedure, not an automated check; recorded as exactly that.
**Not added:** a test asserting every top-level definition in `classify.py`
survives. It would freeze the module's shape and fail on every legitimate
removal, which is noise the next pass learns to ignore.

### Handoff — `CLAUDE.md`'s Click note enumerates exceptions, and there are now two
**Pass:** 4   **Date:** 2026-09-15   **For:** the human, at the pass boundary
`CLAUDE.md` calls `optica[web]` *the* exception that makes `import click`
succeed. The torch stack and `[clip]` are a second route (huggingface_hub 1.31.0,
`notes/verified.md` § "What `.venv` holds…"). The human will replace the
enumeration with a general rule; this pass does not edit `CLAUDE.md`.

### Checkpoint 3 — what the plan leaves open in `export/`, and what was assumed
**Pass:** 4, checkpoint 3   **Date:** 2026-09-15   **Where:** `src/optica/export/manager.py`, `src/optica/export/pytorch.py`, `src/optica/cli/classify.py:export`
1. **Every `--checkpoint-rank` error is one `OpticaValidationError` (exit 1)**,
   listing each invalid value with its reason, plus the available ranks when a
   value names one that does not exist. The plan's "wrapped error" for a
   non-integer is read as *a clean error, not a traceback*: the tokens pass the
   parser as strings (the option is comma-separated), so it is not a parser
   `UsageError`, and one error is what "validate all upfront, report all invalid
   at once" can produce. Repeats collapse.
2. **No checkpoint is `OpticaExportError`** — the command's precondition belongs
   to the export contract.
3. **`--output` is a `str` for `optica export`**, not the shared `Path` option:
   `Path` drops the trailing slash the table depends on. `train` and `run` keep
   the `Path` option (`run` is pass 5's).
4. **Component count excludes the anchor**: `/out` and `C:\out` are
   single-component. **N** (use the last component as the export name) creates
   the parent if absent. With several ranks, **N** names them `<name>_ckptX`.
5. **`--yes`, or no terminal, at the ambiguous multi-component row** is the hard
   error the plan specifies; its fix lines carry the copy-paste command with a
   trailing slash (unambiguous) and say the name branch needs a terminal (`--name`
   is fast-follow, so there is no flag to suggest).
6. **Order:** ranks and checkpoint existence (no torch) → `import_torch_stack` →
   `--output` questions → selection prompt → warnings → stale partials removed →
   writes. One timestamp for every folder of one invocation.
7. **Selection prompt** lists the ranking and takes a rank or several,
   comma-separated; an invalid answer is explained and asked again. No terminal
   and no `--yes` → error naming `--checkpoint-rank 1`.
8. **Stale-path warning** fires, per path, for `checkpoint_paths` in the exported
   checkpoint's run log (read through `log_file`) that no longer exist. The plan
   gives the text and not the trigger.
9. **A checkpoint whose run never finished exports**, with `epochs_trained` and
   `early_stopped` null in `model_info.json` and a warning. The plan says only
   that such a checkpoint lacks the fields.
10. **The six preprocessing values come from `checkpoint_info.json`** (checkpoint
    2 stores them), never re-resolved; a checkpoint without them is refused.
    `config` is copied as stored — its five extra keys (checkpoint 2, item 6) come
    with it.
11. **Stale partials removed are only those named in the export form**
    (`.<family>_<N>cls_<YYYYMMDD>_<HHMMSS>[_ckptX][_x].partial`): `--output .`
    would otherwise delete `.dataset.partial/`. A partial from the **N** branch is
    not recognisable and stays.
12. **Every export re-reads `model.pt` with `weights_only=True` and rebuilds the
    model with the plan's two lines (`pretrained=False`, `strict=True`)** before
    the folder is renamed into place. A head-name drift fails the export instead
    of shipping an artifact whose documented reconstruction does not work.
13. **`usage_examples.md` supports `crop_mode = "center"` only** — all four V1
    backbones — and refuses anything else rather than teaching an unchecked
    transform.
14. **Completion line:** `✓ Export complete — rank R of N to <folder>` per folder,
    then its files; the plan specifies no export completion message.
**Reversible?** Each is local.

### The generated usage example was first tested by a test that could not fail
**Pass:** 4, checkpoint 3   **Date:** 2026-09-15   **Where:** `tests/unit/export/test_pytorch.py`
**Found by the mutation run:** removing `Normalize` from the generated example
failed only the string-level tests; the slow test that *executes* the example
and compared its probabilities with training's evaluation path (`atol=1e-5`)
still passed.
**Why, measured:** a `pretrained=False` efficientnet_b0 is nearly input-blind —
logits for two unrelated random inputs differed by 1.8e-4, softmax 0.5001/0.4999
vs 0.5000/0.5000. A first repair scaled the classifier weights (×1e4 gave
2.0 / 0.41 / 0.85 logit shifts for no-Normalize / bilinear / resize-235 when the
head came from `create_model(num_classes=2)`), but through `reset_classifier`'s
initialisation the same scaling moved the logits only 0.0045 — its own control
assertion caught that, which is what the control was for.
**Now:** two exact comparisons that do not depend on model sensitivity — the
example's preprocessed `batch` must `torch.equal` training's evaluation tensor
(control: a bilinear pipeline gives an unequal tensor), and the reconstructed
model's state dict must equal the checkpoint's tensor for tensor. **Bite:**
`Normalize` dropped, bicubic→bilinear, centre→random crop, `load_state_dict`
removed from the example — each fails it; restored, 10 pass.

### The unbounded-slice rule, broken once the same day
**Pass:** 4, checkpoint 3   **Date:** 2026-09-15
The first repair script above replaced the test with `s[:start] + new` — to end
of file — hours after the incident entry said edit scripts would not. The test
was the file's last and the test count was 8 before and after, so nothing was
lost; but the rule was not followed. The second script asserts the replaced
region holds exactly one test and ends at end of file, and that the count of
tests is unchanged. Recorded because a procedure that is not followed is not a
control either.

### Checkpoint 3 — state
**Pass:** 4   **Date:** 2026-09-15
**Built:** `export/manager.py`, `export/pytorch.py`, `optica export`.
**Tests:** `.venv`, slow included: 2193 passed, 12 skipped (2205). `.venv`,
`-m "not slow"`: 2117 passed, 12 skipped, 76 deselected (2205). Torch-less,
`-m "not slow"`: 2055 passed, 26 skipped, 76 deselected. Ruff clean; mypy clean
in both venvs. `test_classify.py`'s export stub is a pointer to
`test_export_command.py::TestSelection`; `export/__init__.py` joins `_NO_LOGIC`.
**Mutation checks — 18 run, 18 bite** (`scratchpad/mutate_export.py`): ranks 2,
output table 2, naming 2, stale partials 1, atomic write 2, `model_info` 1,
`pytorch.py` 3, CLI 5 — 2 + 2 + 2 + 1 + 2 + 1 + 3 + 5 = 18. Plus the 4 targeted
mutations of the generated example above, after the execution test was
rewritten.
**Smoke:** `optica export --dry-run` and `--checkpoint-rank 1,2 --yes` against
checkpoint 2's smoke checkpoints wrote two complete folders (`_ckpt1`,
`_ckpt2`), before the tests were written.
**Not exercised:** a write-protected `--output` on a real ACL (constructed with a
file in place of the folder); the N branch's partial left by an interrupt.
**Next:** checkpoint 4, the live `optica train` and `optica export` runs.

### Checkpoint 4 — the live milestone, and how it was verified
**Pass:** 4, checkpoint 4   **Date:** 2026-09-15   **Where:** `.smoke/pass4-live/milestone/`; facts in `notes/verified.md` § "Pass 4 milestone"
**Run as one chain,** at the human's direction: a fresh project, a real
clip-mode fetch to make the dataset, `optica train` on it, `optica export` from
that run. Nothing from the checkpoint 2 smoke run was reused except the Open
Images class list.
**How long-running commands were driven.** The Bash tool kills a foreground
command at two minutes. The chain ran as one shell script under
`run_in_background`; the harness notified on exit, and a bounded `until grep`
loop (10-minute tool timeout) waited on the `CHAIN DONE` line. Pass 3 needed an
HTTP client because its server stayed up; train and export are batch commands
that exit, so exit codes plus their artifacts are the whole observable result.
Verification was a separate Python process reading only the artifacts — it
does not trust anything the commands printed.
**What in the path depends on that mechanism — and what the mechanism changed:**
- **Nothing in Optica depends on running in the background.** The commands were
  ordinary child processes of bash.
- **stdin was not a terminal**, so every prompt took its non-interactive branch,
  answered by `--yes`: training's `--output` creation and K/A/D/S (no prior
  checkpoints, so not reached), export's selection (rank 1) and `--output`
  (existed after training). **No interactive prompt was exercised live** —
  those are covered by the command tests only.
- **stdout was a pipe to a cp1252 file**, so Rich rendered no live progress bars
  and `protect_streams` escaped non-ASCII: this found a cosmetic defect below.
- **The private home came from `HOME`/`USERPROFILE`**, and Optica resolves
  `~/.optica` through `Path.home()`, which reads `USERPROFILE` on Windows —
  the same isolation mechanism every live run in this build has used. `HF_HOME`
  pointed at the real Hugging Face cache, so the CLIP weights were not
  re-downloaded; mobilenetv3's were downloaded inside the run.
**Result:** all three exit 0; the verifier prints 24 `[OK]` and no `[FAIL]` (23
failable checks and one summary line over 18 per-key comparisons); it prints 7
`[FAIL]` when the rank-1 checkpoint is changed on disk.

### Found at checkpoint 4 — the epoch line's `│` prints as `│` on a cp1252 stream
**Pass:** 4, checkpoint 4   **Date:** 2026-09-15   **Where:** `src/optica/cli/classify.py:_RichReporter.epoch_finished`
`train.out` reads `train loss 1.0853  acc 0.409  │ val loss 0.9050  acc
0.833`. The separator is a box-drawing character this pass chose; on a non-UTF-8
stdout `protect_streams` escapes it, exactly as pass 2 designed. Nothing is lost,
but a plain ASCII separator would read the same everywhere. **Not changed after
the milestone ran** — the milestone evidence stays tied to the committed code.
→ the next pass that touches `cli/classify.py` (pass 5, `run`).

### Correction — the checkpoint 2 entry "Four more ambient-state tests, three of them mine"
**Pass:** 4   **Date:** 2026-09-15
The title's count is wrong. The entry describes four pass-1 tests in
`test_classify.py` that relied on the repo root having no `./dataset/` (not
mine), and one test of mine (`test_mlstack.py::test_a_server_warning_prints_once_not_twice`)
that failed twice over on inherited logging state — plus two older
`sys.modules` tests it logs without rewriting. Mine: 1, not 3. Corrected here
rather than in place, the log being append-only.

### Pass 4 — closed
**Pass:** 4   **Date:** 2026-09-15
**Milestone met:** `optica train` and `optica export` run to completion, in one
chain, on a small real dataset (`notes/verified.md` § "Pass 4 milestone").
**Built:** the class-name exclusions (checkpoint 0, assigned outside scope);
`input/clip.py` and CLIP filtering in `fetch --mode clip` and the grouped path;
`training/` (`splits`, `models`, `transforms`, `checkpoints`, `runlog`, `data`,
`engine`, `trainer`); `export/` (`manager`, `pytorch`); `utils/mlstack.py`;
`optica train` and `optica export`.
**Tests at close:** `.venv`, slow included: 2193 passed, 12 skipped (2205
collected). `.venv`, `-m "not slow"`: 2117 passed, 12 skipped, 76 deselected.
Torch-less scratch venv (CI's shape), `-m "not slow"`: 2055 passed, 26 skipped,
76 deselected. Ruff clean; mypy clean in both venvs. Mutation checks: checkpoint 1
12 of 12; checkpoint 2 27 of 27 (26 on first run); checkpoint 3 18 of 18, plus 4
targeted on the generated usage example.
**Commits this pass: 22**, this entry's included — checkpoint 0: 1; between 0
and 1: 1; checkpoint 1: 4; between 1 and 2: 2; checkpoint 2: 8; between 2 and 3:
1; checkpoint 3: 4; checkpoint 4: 1 (1 + 1 + 4 + 2 + 8 + 1 + 4 + 1 = 22).
**Entries under "## Pass 4": 27** `###` entries (`grep -c`), this one included —
23 before checkpoint 4, plus the milestone entry, the `│` finding, the
correction and this close (23 + 4 = 27).

**Handed forward:**

| To | Item | Recorded in |
|---|---|---|
| **Amendment session** | **One decision:** the CLIP load call with `force_quick_gelu=True` **and** the observation that 0.25 sits inside the true-positive score range — the call and the number are calibrated together | "Proposed plan change — the CLIP load call…"; "Finding for the human — 0.25…" |
| **Amendment session** | mobilenet's `conv_head` unfrozen in Phase 2 — proposed l.1063 cell | "Checkpoint 2 — what the plan leaves open…", item 1 |
| **Human, at the pass boundary** | `CLAUDE.md`'s Click note enumerates exceptions; there are now two routes (`[web]`, torch stack/`[clip]`). A general rule replaces it. `CLAUDE.md` untouched | "Handoff — `CLAUDE.md`'s Click note…" |
| **Pass 5** | `optica setup` reads the `.venv` audit, including real Click via huggingface_hub | `notes/verified.md` § "What `.venv` holds…" |
| **Pass 5** | `optica run`: call `training.trainer.train` and `export.manager` rather than re-sequencing; `run`'s `--output` is still the shared `Path` option and cannot see a trailing slash — `export`'s `str` option shows the form | checkpoint 2 item 18; checkpoint 3 item 3 |
| **Pass 5** | Fetch More still refuses grouped blocklist classes | "CLIP Adapter — what the plan leaves open…", item 10 |
| **Pass 5** | The epoch line's `│` separator | "Found at checkpoint 4…" |
| **Pass 5 or 6** | `test_main.py::TestVersion::test_no_torch_is_imported` and `config/test_init.py::test_importing_it_does_not_import_torch` still read the shared `sys.modules`; they fail the day a fast test imports torch in-process. The subprocess form in `test_system.py` is the fix | "Four more ambient-state tests…" |
| **Pass 6** | `ruff format --check` reports 16 pre-existing files; CI runs `ruff check` only | "Found at checkpoint 0…", item 2 |
| **Human** | `.smoke/pass4-live/` is this pass's throwaway directory (clip runs, the GELU comparison, the train smoke, the milestone). The scratch torch-less venv lived in the session scratchpad | — |

**Live coverage — not exercised, for pass 6's README** (joins pass 3's list):
- **A genuinely write-protected `--output`** — tested by putting a file where
  the folder should be, never against a real ACL or read-only mount.
- **An interrupted export under a user-chosen name** (the `--output` N branch):
  its `.partial` is not recognisable as an export's and is left in place.
- **The CLIP weights-repair path** — delete and one re-download of a corrupt or
  truncated `open_clip_model.safetensors`; tested with constructed files only.
- **MPS** — written, never run; the device choice is tested by monkeypatching
  `torch.backends.mps.is_available`.
- **The grouped blocklist path's CLIP scoring** — fake scorer only.
- **Interactive prompts of `optica train` and `optica export`** — every live run
  used `--yes` with a non-terminal stdin; the prompts are covered by the command
  tests with patched `typer.prompt`/`typer.confirm`.
- **Ctrl+C during a real training run at a terminal** — interruption is raised
  from the reporter in tests; resume is exercised end to end there, not live.
- **CPU training through the CLI** and **`train --manifest` with the real
  trainer** — the trainer runs on CPU in the slow tests; the CLI paths use a fake
  trainer.

**Pass 4 is complete.** Next: the amendment session, then pass 5.

### The Click sentence is now a rule, after three corrections
**Pass:** between 4 and 5   **Date:** 2026-09-15   **Where:** `CLAUDE.md` § "Settled points that the plan leaves implicit"
**Found:** pass 4 established a second route by which real Click reaches the
environment — `huggingface_hub` brings it with the torch stack, not only
uvicorn with `optica[web]`. The sentence was wrong in shape rather than in
fact: it named one exception where there were two, and any dependency bump can
add a third.
**Action taken:** the enumeration is replaced by the rule — *never rely on
Click's absence* — with both known routes given as examples rather than as the
list. The instruction is unchanged for the fourth time running: use `typer`'s
equivalents, never `click.*`.
**The pattern is the finding.** This is the third correction to one sentence:
- 2026-09-13 — the original premise, *"they arrive transitively through `typer`
  and `pydantic-settings`"*, was half false. Typer vendors Click as
  `typer._click` and declares no dependency on it.
- 2026-09-14 — the correction said `import click` fails in a Core install,
  which is true and incomplete. `optica[web]` admits real Click, so the failure
  stops being loud.
- 2026-09-15 — this entry. A second route appeared, and a list of exceptions
  will keep going stale for as long as the dependency tree moves.

Each correction was true when written and each was falsified by the next pass
touching a wider slice of the dependency tree. The lesson is not about Click: a
statement enumerating the cases where a hazard applies decays, while a statement
of the hazard does not. Prefer the rule to the list when the underlying set can
grow.
**Who found it:** pass 4 checkpoint 2, from a `.venv` audit against
`pyproject.toml`'s declared extras that the companion session asked for on
unrelated grounds. Recorded in `notes/verified.md`. `CLAUDE.md` was left
untouched by the agent and flagged here for the human, which is the correct
handling — an agent editing its own standing instructions is not a change it
should make unattended.

### Plan amendment session 3 — items 17, 17b and 18 decided
**Pass:** between 4 and 5   **Date:** 2026-09-15   **Where:** `spec/optica-plan-v1-core.md`
**What this is:** the outcome of the third out-of-repo plan-amendment session.
It is recorded here so pass 5, reading pass 4's three proposals above, can tell
which landed and in what wording. The `spec/` edits were applied by the user,
not by an agent.

| # | Item | Disposition | Sites |
|---|---|---|---|
| 17 | The CLIP load call builds GELU under QuickGELU-trained weights | **Ratified** — kwarg added inside the call | l.848 |
| 17b | `clip_threshold = 0.25` sits inside the true-positive score range | **Deferred** — fast-follow; no edit | — |
| 18 | mobilenet's `conv_head` frozen in both phases | **Ratified** — cell amended | l.1063 |

**For pass 5 — the `clip_threshold` bands did not change.** l.859–865 and the
`--yes` rows at l.205–206 stand as written. So does the default `0.25` (l.336,
l.851, l.1746). Transcribe them as the plan states them.

**Item 17 — what landed differs from the proposal.** l.848 now reads, on one
line:
`model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai', force_quick_gelu=True)`.
The proposal's two-line layout was not used, because it would move every later
line number. Its explanatory sentence was not added either. The kwarg is correct
whether or not a later open-clip applies the tag's activation itself, while the
sentence describes open-clip 3.3.0's behaviour, which is exactly what
`input/clip.py`'s slow test watches for a change. `MODEL_KWARGS` already
matches, so no code changes.

**Item 17b — why the number stands.** Under the activation change, the mean
own-class score moves +0.003 (dog) and +0.006 (cat), and at most 0.022 on any
one image. That is about the size of the value's own last-digit rounding. The 22
crossings are large because 0.25 sits where true-positive scores are densest,
not because the scale moved.

What was measured does not support a lower default either. Against the *other*
class's prompt, cats average 0.2206 and dogs 0.2030. At 0.25, clip mode keeps 76
of 120 genuine images and admits 4 of 120 as the wrong class; a value near 0.20
sits inside that near-negative distribution. Real negatives from a text search
were never measured, and `notes/verified.md` holds no per-image scores.

The plan is not edited. l.853 already reports a shortfall per class and says it
is not an error, and l.1723 already accepts that one threshold may over-filter
a class, so the user-visible consequence is covered.

**Item 17b — what the fast-follow starts from.**
- **Study the threshold and l.853's hardcoded 2× over-fetch together.** Dog
  survival at 0.25 was 52–54%, against the factor's 50% break-even; live run 3
  kept 25 dogs from 27 that passed.
- **Revisit the band edges too.** The Normal band runs to <0.5, and no measured
  score exceeded 0.3059.
- **Keep the per-image scores.** If `scratchpad/gelu_compare.py`'s per-image
  scores still exist, keep them; they are the only per-image data.

Two verified classes from one source are the whole evidence base so far.

**Item 18 — what landed differs from the proposal.** l.1063's cell now reads
*Last 3 blocks + `conv_head`*. The proposed `(blocks[4]`–`blocks[6])` span was
not added: on 13 September, item 10 deleted this row's type word and declined
adding indices, because indices are the part that decays.

The derived rule is *the named blocks plus every parameterised module after
them, up to the classifier*. It was checked against § task 4's module order and
restates l.1060–1062 exactly. It is not written into the plan, since in V1 four
rows that agree with it are a closed list. `training/models.py` already
matches, so no code changes.

**Item 18 — a number worth keeping.** mobilenet's Phase 2 trainable share,
classifier included, is now 95.4% of parameters, up from 66.2% under the
literal reading. For comparison, the efficientnets sit at 78.8% and 79.3%, and
resnet50 at 63.7%. Still frozen in Phase 2: `conv_stem`, `bn1` and
`blocks[0]`–`[3]`. Nothing measured accuracy under either reading.

**Correction to the agenda's framing.** The pass 4 close and the run record
describe 17 and 17b as one decision because *the call and the number are
calibrated together*. That holds in principle and not at the measured scale.
Changing the call does not move the number, and 17b stands or falls on its own
evidence.

### Fast-follow reconciliation — fourteen pre-implementation findings read against passes 0–4
**Pass:** between 4 and 5   **Date:** 2026-09-16 to 2026-09-18   **Where:** `spec/optica-plan-v1-core.md`; `optica-fast-follow-findings.md`
**What this is:** the outcome of an out-of-repo session. It read the fourteen needs-decision findings in `optica-fast-follow-findings.md` — sorted before implementation began and not consulted in four passes — against the code those passes shipped, and recorded three items the run itself raised. The `spec/` edits are applied by the user, not by an agent. It is recorded here so that pass 5 can tell which decisions landed and in what wording.

| Item | Disposition | Plan sites |
|---|---|---|
| F21 — declined prompt `3` vs `click.Abort` `130` | **Resolved** † | l.220, l.1570 |
| F14 + O8 — `optimizer` in the artifact `config` blocks; `finetune_ratio` in `TrainConfig` | **Resolved** † (O8 → pass 5) | l.1155, l.1284, l.1394 |
| F18 — `TrainResult` lacks `early_stopped` | **Pass-5** | l.1374, l.1378 |
| F23 — `--only` undefined | **Post-V1** † | l.1649 |
| F15 — exporting an interrupted checkpoint | **Resolved** † | l.1165 |
| F16 — "permanent" log vs "regenerable" folder | **Plan-open**, decided | l.289 |
| F5 — `--yes` at the blocklist definition prompt | **Resolved** † — already in the plan | — |
| F1 + O3 — version table; uvicorn declaration | **Resolved** | l.104, l.112 |
| F2 — "`.env` is gitignored" | **Plan-open**, decided | l.261 |
| F8 — soft cap vs clip's 2× draw | **Post-V1**, with 17b | l.853 |
| F11 — "Optica doesn't touch" | **Plan-open**, decided | l.799 |
| F13 — zero-readable abort and ownership | **Plan-open**, decided | l.949 |
| F22 — exception class for a nonexistent checkpoint path | **Pass-5** | l.1419 |
| F24 — Note 19 and verbosity | **Plan-open**, decided | l.1642 |
| 15b, 17b, mobilenet Phase 2 share | **Post-V1** — new section of the fast-follow file | — |

18 edits on 18 lines, applied to a scratch copy and invariant-checked. The file stays at 1781 lines, CRLF throughout, and no line number moves. l.1570 is the first change to the exit-code table in this run, and it was made deliberately.

**† = unverified.** The session asked for one batch of repository observations, and the batch was not run. The dispositions rest on what the plan says; where they also depend on shipped code, the settling command is in `optica-fastfollow-reconciliation-dispositions-2026-09-16.md`. Pass 5 is told to check each one.

**For pass 5 — what changed and what to do.** Read the 18 lines as they stand in `spec/`, not the proposals in the dispositions file. `notes/passes/pass-5.md` carries the full block. In short:
- **`TrainConfig`** has exactly eleven fields, and they are the same eleven the artifact `config` block carries. Confirm the shipped blocks hold all eleven.
- **`TrainResult.early_stopped`** is copied from the loop's own flag, never derived from `epochs_run`, and is `None` under `dry_run`.
- **`Classifier(checkpoint_path=…)`** raises `OpticaValidationError` whether the path is missing or is not a checkpoint.
- **The interrupted-export warning** gets a stable `WarningEntry` code.
- **Every new prompt** answers N itself and exits `3`. `confirm(..., abort=True)` has no call site in `src/`.
- **The API** raises `OpticaValidationError` at the blocklist definition step.
- **The zero-readable abort** on `curate` and `clip` reports a count only.
- **`--only`** is not built.

**For pass 6 — the README.**
- Advise users to add `.env` to their own `.gitignore`. Optica never touches it (l.261, l.289).
- Name `~/.optica/logs/` as the durable run history. The copy under `--output` duplicates it (l.289, l.1175).

**Correction to the fast-follow file's record.** F5 quotes l.183 as saying `--yes` "resumes automatically". That sentence was rewritten by the Findings Resolution session's own F7/F9 edits before implementation, and l.183 now states F5's resolution (c). The fast-follow file carries a note to this effect; its line citations all still resolve.

**For the human.**
- **`CLAUDE.md`.** § "Settled points that the plan leaves implicit" opened with the declined-prompt rule, which the plan now states at § "Error handling and prompt conventions (standing rules)" and § "Exceptions". The paragraph now cites both. The heading is unchanged, and the `confirm(..., abort=True)` ban remains the genuinely implicit part.
- **Run the observation batch before pass 5 opens.** It is in the session transcript and in the dispositions file.

### Fast-follow reconciliation — the seven unverified dispositions, observed
**Pass:** between 4 and 5   **Date:** 2026-09-18   **Where:** observation only; no file in `src/` or `tests/` was touched
**What this is:** the entry above recorded seven dispositions as unverified, because the session's repository observations had not been run. They were run on 18 September, before pass 5 opened. **Nothing is contradicted and no disposition changed.**

| Row | What was observed |
|---|---|
| F21 | `findstr /s /n /c:"abort=True" src\*.py` returns one line: `utils/prompts.py`'s module docstring, stating that `typer.confirm(..., abort=True)` is never used and that `confirm_or_abort` is the only place the decline-to-exit mapping is written. No call site. |
| F23 | `--only` appears nowhere in `src/` or `tests/`. |
| F14 | Three `checkpoint_info.json` files and the exported `model_info.json` from the pass 4 milestone each carry exactly eleven `config` keys — the plan's six plus `optimizer`, `max_checkpoints`, `train_split`, `val_split`, `test_split`. The amended examples at l.1155 and l.1284 describe shipped behaviour. |
| F15 | `export_manager.missing_run_end()` detects a checkpoint whose run never finished; `info.get(...)` writes `epochs_trained` and `early_stopped` as `null`; `cli/classify.py` warns through `olog.warn` with a `why=` naming both fields. l.1165's "with a warning" describes shipped behaviour. The API's `WarningEntry` remains pass 5's. |
| F18, F22 | `TrainConfig`, `TrainResult` and `Classifier` do not exist in `src/`, as expected — both items are pass 5's to write. `training/trainer.py` already carries `early_stopped` on the loop's outcome object, which the CLI's completion block reads, so pass 5 copies a value rather than computing one. |
| F5 | Two live tests on `TerminalClassPrompter.define` pin both branches of l.183: `OpticaValidationError` in a non-prompting context, and the prompt firing in a terminal under `--yes`. |
| CRLF | `git ls-files --eol spec/optica-plan-v1-core.md` reports `i/crlf w/crlf attr/-text` after the amendment commit. |

**Two corrections to `notes/passes/pass-5.md`**, made in the same commit as this entry:
- **Item 5 was wrong as committed.** It said the `abort=True` grep must return nothing; it always returns the docstring line. It now says exactly one line, that line, and that any call site is a defect.
- **Items 1, 2, 4 and 6 now record what was observed**, so pass 5 does not re-run checks that are already answered: the eleven `config` keys, `outcome.early_stopped`, the CLI's existing warning, and `TerminalClassPrompter.define` as the shipped example. Item 7, the zero-readable abort on `curate` and `clip`, is still a check pass 5 must make.

**One observation with no owner.** `tests/unit/utils/test_prompts.py`'s `TestPlanValuesStillToImplement` holds live tests for behaviour pass 2 shipped, including both F5 branches; its own comment says so. The class name is stale for its contents. Not fixed here — it is test organisation, not scope.

**Record correction.** The entry above, and the two commits before it, were rebuilt locally on 19 September: they carried 16 September where the work ran from the 16th to the 18th, and the `spec/` commit message carried the same date. Nothing had been pushed. The rebuilt commits carry author date 2026-09-18 and committer date 2026-09-19; `backup/pre-date-fix` holds the originals until this is settled.

### Pass 5, item 7 — the zero-readable abort on `curate` and `clip`: checked, no defect
**Pass:** 5   **Date:** 2026-09-20   **Where:** `tests/unit/cli/test_fetch_command.py::TestUnreadableAutoFetchedImages`
**What was asked:** plan l.945 and l.949 — auto-fetched images (`curate`, `clip`) are
reported as an **aggregate count**; per-file reasons belong to user-provided files
alone. Pass 5 item 7 was to check the shipped code and fix it if it listed reasons on
an auto-fetched path.

**What the shipped code prints.** No auto-fetched path carries a reason to print.
`RejectReason` reaches the terminal through exactly one function, `reasons_summary`
(`input/validation.py`), and it has two call sites: `local.preflight`'s zero-readable
raise and `cli/classify.py::_report_unreadable`. Both are user-provided input only —
`preflight` is called once, from `_label_body` on `--folder`/`--manifest`;
`_report_unreadable` is called from the labeling copy, the `--manifest`
materialization and `_ingest_dataset` (`--dataset`, read in place). The auto-fetched
reports carry an `int`, not a reason: `ClassFetchReport.unreadable` (printed as
`Skipped N dead links, M unreadable downloads and K duplicates`) and
`ClipFilterReport.unreadable` (printed as `(M could not be read)`).
**No change to `src/` was needed, and none was made.**

**Two observations that go with it, neither a defect.**
- `curate`'s zero-images abort is `curation.load_view`'s
  *"No fetched images are staged for curation."* — the count is zero and the message
  says so. Unreadable downloads are deleted at fetch-write, so by the time curation
  looks there is nothing left to count and no file to name. Confirmed live in
  `.smoke/item7/` against an empty home: three lines, no per-file reason.
- **`clip` does not abort on zero readable images at all.** It writes an empty class
  folder by name, warns *"Fewer images than requested passed CLIP filtering"*, and
  leaves the five-image floor to training. That matches the plan's reasoning for the
  abort — l.949 exists so a browser does not open onto an empty session, and clip mode
  has no browser stage — so the absence is deliberate, not a gap. Item 7's rule still
  binds what clip *reports*, and it reports a count.

**Pinned so it cannot regress.** Three tests, each constructing its own condition
rather than inheriting one: every CDN body undecodable (the fetch report), the staging
those downloads leave behind (the curate abort), and a scorer returning `None` for
every image (the CLIP report). Each asserts no member of `RejectReason` appears in the
output. `FakeScorer.score_fn` was widened to `float | None`, which is what the real
`ImageScorer.score` returns — the narrow annotation was why the unreadable case could
not be constructed against the fake.
**Proved they bite:** three separate mutations, each reverted — a reason appended to
the fetch `Skipped` line, a reason appended to `_report_clip`'s parenthetical, and a
reason plus the staging path added to `load_view`'s `why=`. Each failed exactly its
own test and no other.

### Pass 5 scope widened — `optica run`'s CLI body
**Pass:** 5   **Date:** 2026-09-20   **Where:** decided between checkpoint 0 and
checkpoint 1, not in the pass prompt
**Missing:** **no pass's Build list owns `optica run`.** `CLAUDE.md` § "Build
order" gives pass 2 `input/`, pass 3 `server/`, pass 4 `training/`/`export/` and
pass 5 `api/`, `cli/setup.py` and the registries. The composite command appears
in none of them, and `cli/classify.py` accordingly ships it as
`raise _not_yet("optica run")` — live, `optica run -c cat,dog --yes` prints
*"optica run is not available in this build."* It is the plan's **Tier 1 entry
point** (§ "Python API", five-tiers table) with a section of its own
(§ "`optica run` resumption and preconditions"), and pass 6 forbids `src/`.

**Assumed → decided:** pass 5 builds it. Not an assumption logged and carried:
the gap was reported at checkpoint 0 as a closing window and the human widened
the pass in reply. Recorded here because the decision was taken **between
checkpoints**, so nothing in `notes/passes/pass-5.md` shows it.

**Why this is a missing scope line rather than a decision taken against it** —
three artifacts already assume pass 5 owns it, while no Build list says so:
- `notes/passes/pass-5.md` item 5: *"Every prompt this pass adds — `optica
  setup`, **`optica run`'s R/C/S**, any other"*.
- Pass 2's forward hand-off: *"Pass 5: `optica run` sequencing"*.
- Pass 4's forward hand-off: *"`run`'s `--output` can't see a trailing slash"*.

**Order fixed by the human:** registries → `api/` → `optica run`'s CLI body →
`cli/setup.py` → the live runs. The body delegates to `optica.run()`, so it
cannot precede the API.

**Gate:** before any of it is written, § "`optica run` resumption and
preconditions" is read in full and checkpoint 2 reports what the work actually
is — what is genuine delegation and what is CLI-only (the R/C/S prompt,
`--output`, exit codes, the `--yes` interaction) — with a measurement rather
than the estimate "thin delegation". If it is a module rather than a wrapper,
pass 5 stops there and the human decides again.

**Reversible?** Yes, and cheaply, up to the moment the body is written: reverting
to `_not_yet` is a one-line change. After V1 ships it is not — a stubbed Tier 1
entry point is what shipping would make permanent.

### The registries: placement and four decisions
**Pass:** 5   **Date:** 2026-09-20   **Where:** `src/optica/registries.py`
**Missing:** plan § "Code Structure" ends with *"the `TASK_REGISTRY`/
`EXTRAS_REGISTRY` have no stated home … both should be placed when the API
namespace and setup registry are built"*. That is the only instruction; the file
is not in the tree.

**Assumed:** a new top-level `src/optica/registries.py`, holding both registries,
the group helpers, `resolve_setup`, the `--include-extras`/`--exclude-extras`
name validation, the Review's size arithmetic and the CUDA index table.
**Why:** two layers read this data — `cli/setup.py` resolves a selection from it,
and `TASK_REGISTRY`'s `api_namespace`/`tier5_class` describe the API's task
namespace. A home under `cli/` would have `api/` importing the CLI.
**Reversible?** Yes — one module, no dependants outside pass 5's own work yet.

Four decisions inside it, none of them stated by the plan:

1. **Which exception class the extras-flag errors raise.** `OpticaValidationError`,
   not `OpticaSetupError`. § "Exceptions" scopes `OpticaSetupError` to
   environment resolution, hardware detection and install failure, and lists
   *"mutually exclusive input flags"* under `OpticaValidationError`; an unknown
   registry key or a both-sides conflict is the input contract, not the
   subsystem's. The errors carry `options=` (every valid key) per the
   fixed-value-flag rule.
2. **How the Review's download total renders below 1GB.** The plan shows one
   total, `~0.9–3.1GB`, and no sub-gigabyte case. Rule taken: **one unit for the
   whole figure, chosen by the top of the range** — GB at or above 1000MB, MB
   below — with half-up rounding to one decimal in GB. That reproduces the
   plan's figure exactly (250+5+600 = 855MB → 0.9GB; 2500+5+600 = 3105MB →
   3.1GB) and renders `torch-cpu`+`web`+`clip` as `~855MB` rather than `~0.9GB`.
   A per-endpoint unit was rejected: it would print `~855MB–3.1GB`, whose two
   ends cannot be compared at a glance. `size_breakdown()` exists so the Review
   cannot print the total without the rows it is a sum of.
3. **The CUDA index is a table, not a format string.** `notes/verified.md`
   § "Which CUDA indexes exist on `download.pytorch.org`" (2026-09-12) records
   `cu126`, `cu128`, `cu129`, `cu130`, `cu132` published and **`cu131` 403 —
   never published**. `cuda_index_url()` therefore returns the newest published
   index at or below the driver's CUDA version, so a 13.1 driver (this machine)
   takes `cu130`. `torch-gpu`'s own `index_url` stays **pinned** to `cu130`, which
   is what the plan's `cu<XXX>` gate item asks for; only `torch-auto` resolves.
4. **Ruff's `allowed-confusables`.** The en dash in `~250MB–2.5GB` and
   `~0.9–3.1GB` is the plan's own character, transcribed exactly; RUF001/2/3
   flag it as confusable with a hyphen. `pyproject.toml` now allows that one
   character repo-wide rather than carrying seven `# noqa`s. Every other
   confusable stays flagged.

**Not built here, deliberately:** the prompts (`resolve_setup` takes the
selection as injected callables), the pip commands, and the Review's rendering.
`PYPI_PACKAGES`/`INDEXED_PACKAGES` carry the partition those commands need —
`timm` and `scikit-learn` are absent from the torch index and `--index-url`
replaces PyPI rather than adding to it — but building the command is
`cli/setup.py`'s, at checkpoint 3.

### The interrupted-export warning code — `checkpoint_run_incomplete`
**Pass:** 5   **Date:** 2026-09-20   **Where:** `api/simple.py::WarningCode`
**Missing:** pass-5.md item 4 and plan l.1165 require the interrupted-checkpoint
export warning to be a `WarningEntry` with **its own `code`**, and say codes are
stable API surface — but name no code. Choosing one is permanent: renaming it
after V1 breaks every caller branching on it.

**Chosen:** `checkpoint_run_incomplete`.
**Why:** the plan's own two example codes — `class_imbalance`, `low_resolution` —
name *what is true*, as subject plus condition, and carry no command prefix.
This one's subject is the checkpoint and its condition is that the run which
produced it never finished, which is exactly what `export_manager.missing_run_end()`
establishes: `epochs_trained` and `early_stopped` are absent, so
`model_info.json` records them as `null`.

**Rejected, and why each was rejected:**
- **`interrupted_checkpoint`** — the plan's *heading* word, and the checkpoint
  may carry `"interrupted": true`. Rejected because it asserts a **cause the
  check does not establish**: `missing_run_end()` tests for two absent keys, and
  a crash, a kill, or a machine losing power leaves the same state without any
  interrupt handler running. A code that names a cause a caller cannot rely on
  is worse than one that names the state.
- **`incomplete_run`** — the closest to the CLI's own sentence ("from a run that
  did not finish") and the shape of `low_resolution`. Rejected for **collision
  inside its own namespace**: `optica.run()` and `RunResult` are in the same
  API, so a caller reading `code == "incomplete_run"` would reasonably take it
  for the pipeline call rather than the training run behind a checkpoint.
- **`missing_run_end`** — exactly what the detector checks. Rejected because it
  is the **detector's own function name**: it names the mechanism (two absent
  JSON keys) rather than the condition, and promoting an implementation detail
  to permanent public surface is what makes later refactoring breaking.
- **`export_interrupted_checkpoint`, or any `export_` prefix** — rejected
  because the plan's example codes carry no command prefix, and the same
  checkpoint state is readable outside export: `Classifier(checkpoint_path=…)`
  meets it, and post-V1 incremental learning reads the same two fields. A prefix
  would date the code to the first command that happened to surface it.

**Reversible?** Until V1 ships, yes — one constant and its tests. After, no.
The full code set lives in one class, `WarningCode`, so the whole stable surface
is visible in one place rather than as literals at each raise site.

### `optica.export` — the flat alias collides with the `export/` subpackage
**Pass:** 5   **Date:** 2026-09-20   **Where:** `src/optica/__init__.py`
**Missing:** the plan fixes **both** names and does not notice they collide.
§ "Python API" gives `optica.export()` as a Tier 3/4 flat alias (its own example
calls it), and § "Code Structure" gives `src/optica/export/` to the Export
Manager. On the `optica` package object only one `export` attribute can exist.

**Assumed:** the **function wins**. `optica/__init__.py` binds the alias after
the subpackage has been imported, so `optica.export(...)` is the Tier 3 call and
`sys.modules["optica.export"]` is still the module.
**Why:** the alias is the surface users are told to call; the package is
internal. Everything inside Optica already reaches it as
`from optica.export import manager` / `import pytorch`, which is unaffected.
Renaming the package would contradict § "Code Structure", and a plan
contradiction is a stop-and-report, not a silent edit.

**What it costs, stated rather than hidden:** any attribute walk from the
package object — `import optica.export.pytorch` then `optica.export.pytorch.x`,
and `monkeypatch.setattr("optica.export.pytorch.export", …)` — now resolves
`optica.export` to the function and fails. That broke **25 existing tests** in
`tests/unit/cli/test_export_command.py` and `tests/unit/export/test_manager.py`,
all of them patching the writer by dotted string; both now patch through the
module object instead, with a comment saying why. No product code was affected.
A test pins the resolution both ways, so a silent flip fails loudly.
**Reversible?** Yes, by dropping the flat `export` alias — which the plan's own
example forbids.

### The Python API — six smaller decisions
**Pass:** 5   **Date:** 2026-09-20   **Where:** `api/simple.py`, `api/classifier.py`
1. **The blocklist raise moves to entry.** The CLI reaches the definition prompt
   inside the class sequence, after `source.prepare()`. The API raises before
   the lock is taken, because `define` has no safe answer here so the outcome is
   already determined — and l.769 says an unattended run "refuses **before any
   fetch begins**". `dry_run=True` still reports `needs_definition` rather than
   raising, matching the CLI's dry run.
2. **The overwrite refusal is API-shaped.** `input_manager.overwrite_refused()`
   names `--overwrite`; the API raises its own `OpticaValidationError` naming
   `overwrite=True`, per the mapping rule that sends `--overwrite` to a
   per-operation `overwrite=True`. Tested for both the presence of the one and
   the absence of the other.
3. **`verbose=` is restored after each call.** The CLI sets verbosity globally
   and keeps it; a library call that left the process quieter than it found it
   would be a side effect nobody asked for, so the level is set for the call and
   put back. The plan's stated loss stands: `--verbose`'s extra detail has no
   API spelling.
4. **`run(dataset=…)` takes `None` as its default**, not `"dataset"`. The
   short-circuit resolution needs to know whether the caller named the dataset —
   `dataset_explicit` in `short_circuits_acquisition` — and only a sentinel can
   carry that. Every other function keeps the plain default.
5. **`checkpoints.read(folder)` was added** — the single-folder counterpart of
   `list_active`, which had no public way to read one checkpoint by path.
   `Classifier(checkpoint_path=…)` validates through it and `list_active` now
   uses it, so there is one parse rather than two. JSON only; never torch.
6. **Browser steps that do not finish raise.** `label()` and `curate()` have no
   exit code to return, so a timeout raises `OpticaError` and an interrupt
   re-raises `KeyboardInterrupt` — the API counterparts of exit 3 and 130.

### The `optica run` gate — what § "resumption and preconditions" actually asks for
**Pass:** 5   **Date:** 2026-09-20   **Where:** measurement taken before any of
checkpoint 3 was written, at the human's instruction

**Every behaviour the section specifies, with which side owns it.**

*Delegation to `optica.run()` — already built at checkpoint 2:*
1. Mode resolution and the acquisition short-circuit — `simple._run` resolves
   both; `short_circuits_acquisition` needs `dataset_explicit`, which the CLI
   already knows from its own flags.
2. The entry extras check — `simple._require_extras`: web for label/curate,
   clip for `--mode clip` and for a blocklisted name under curate, torch for the
   train and export steps, all before fetching begins.
3. The stage sequence itself: acquire → train → export, with `RunResult`
   carrying the three stage results and `None` for stages that did not run.
4. `--dry-run`'s four resolutions (`mode`, `detection_order`, `short_circuit`,
   `destination`). The CLI renders them; it computes none of them.
5. Every stage's warnings, as `WarningEntry` — the CLI prints from the entries.

*Shared — the component is built, both surfaces call it:*
6. Precondition validation per stage: `curate` checks staged images
   (`load_view`), `train` checks the dataset shape (`load_organized_dataset`),
   `export` checks a trained checkpoint (`ranked_checkpoints`), `label` checks
   its folder or manifest. All four already raise `Optica*Error` with fix lines
   from `input/`, `training/` and `export/`, reached identically from either
   surface.
7. `label`'s `-c` resolution "the way `fetch` does" — `resolve_auto_classes`
   with a prompter; the CLI passes `TerminalClassPrompter`, the API passes the
   raising one. The seam exists; `run` picks the prompter.

*CLI-only — no API counterpart exists, by the plan's own rules:*
8. The `Previous session found:` block, with one `✓`/`✗` line per completed or
   incomplete step.
9. The top-level `[R] Resume [C] Choose step [S] Start fresh` prompt.
10. **C** — the step selector: four steps with status
    complete / incomplete / not started, where a step whose inputs are absent is
    **listed but not selectable and says why**.
11. Selecting a step earlier than the last completed one **discards the later
    steps' staging, behind a confirmation** — a destructive branch.
12. `--yes` auto-picks **R** at top level, which is why 11 never arises
    unattended.
13. **S** clears staging and starts clean (`input_manager.clear_staging` exists;
    the choice is the CLI's).
14. Suppressing the step-level resume prompts inside `run`, and the checkpoint
    K/A/D/S prompt with them (Note 19) — the API has no step-level prompts at
    all, so this is CLI-only by construction.
15. Warnings and safety prompts still firing inside `run` (Note 19) — the CPU
    batch-size prompt is the live example.
16. `--output` handling: `run` currently declares the shared `Path` option,
    which **cannot see a trailing slash** (pass 4's hand-off), so it needs
    `export`'s `str` option and the N/C/A multi-component prompt with it.
17. Exit-code mapping: 3 for a declined prompt or an aborted stage, 130 for an
    interrupt, through the global handler.
18. The per-stage `✓ X complete` / `✗ X incomplete` terminal lines for the
    stages `run` drives — today each lives inside the standalone command body,
    which `run` will not call.

**Three things I cannot place from the section, stated rather than picked:**
- **Where the resumption state model lives.** Deciding what is complete,
  incomplete or not started across the four steps is a computation over
  staging, `dataset/`, `checkpoints/` and the output folder — a *decision*, and
  the CLI layer is specified to hold none. But in V1 only the CLI consumes it,
  because the API behaves as though `--yes` were passed and `--yes` picks R,
  which never needs the per-step status. `input/manager.py` and `cli/classify.py`
  are both defensible; the section does not say.
- **Whether `optica.run()` itself honours R.** The `--yes` table row
  *"`optica run` top-level R/C/S resume → R — resume"* is in the table the API
  is told to follow, so the API arguably must resume from the last incomplete
  step. As built, `simple.run()` runs every stage and lets each one
  short-circuit on what it finds, which is weaker than an explicit resume. If
  the stronger reading is right, the state model is shared and the API needs
  work too.
- **Where the per-stage completion lines are printed.** The CLI's `✓`/`✗`
  vocabulary is terminal output, so the API should not print it — but `run`
  reaches its stages through `optica.run()`, which returns results rather than
  printing them. Re-rendering from the results in the CLI is the obvious answer;
  the plan does not confirm it.

**Size, measured rather than estimated.** Comparable blocks already in
`cli/classify.py`: `_resolve_export_output` 54 lines, `_selection_prompt` 32,
`_mass_rejection` 61, `_checkpoint_housekeeping` 73, `_open_curation_session` 27,
`_resume_prompt` 19. `optica run`'s command is 96 lines today, of which ~30 are
validation and one `_not_yet`. Items 8–13 are one prompt block plus one selector
of that same shape; 16 is `export`'s existing `str`/`_resolve_export_output`
pattern reused; 17 and 18 are per-stage mapping. `simple.run()` is 57 + 95 lines
and holds the sequencing. On that basis the CLI body is a **wrapper with one
substantial prompt block**, not a module — the same shape as `_curate_body`
(59 lines) plus `_mass_rejection` (61) — **unless** the second ambiguity above
resolves toward a shared state model, which would add a component to `input/`.

**What checkpoint 3 will NOT verify, stated before it is built.**
A live end-to-end `optica run` is out of scope: it drives both browser steps and
a real training run. So the following will be exercised by tests and by
inspection only, and a green checkpoint 3 must not be read as proof the chain
ran:
- No real browser session opened by `run`'s curate or label stage, and so no
  live check that the step-level resume prompt is actually suppressed **while a
  browser step is resuming** — only that `run` does not call the prompting path.
- No live interrupt (Ctrl+C) inside a `run`-driven training stage, so exit 130
  from within a stage is asserted from a raised `KeyboardInterrupt`, not from a
  real signal.
- No live resume of a genuinely interrupted pipeline: the staged states will be
  **constructed** on disk (staging directories, a `dataset/`, checkpoints with
  and without the run-end fields), not left behind by an interrupted run.
- No live export of a model trained inside the same `run` invocation; the export
  stage is exercised over constructed checkpoints with the `.pt` writer replaced.
- The four-step status model is verified against constructed states only, so a
  state real usage can produce but the fixtures do not construct is unverified.
Same discipline as pass 4's MPS path and pass 3's prompt surface.

### `optica.export` — the alias is stable, on one undocumented invariant
**Pass:** 5   **Date:** 2026-09-20   **Where:** `tests/unit/api/test_init.py::TestExportNameCollision`
**Tested, not reasoned.** Five import orders in **fresh interpreters**, plus the
in-process state:

| Probe | `optica.export` is |
|---|---|
| `import optica.export` alone | function |
| `import optica` then `import optica.export` | function |
| `import optica` then `import optica.export.pytorch` | function |
| `import optica.export.pytorch` then `import optica` | function |
| `from optica import export` | function |
| `sys.modules["optica.export"].manager` | the real module's `manager` |

**Why it holds, and what it rests on.** The import machinery sets the attribute
on the parent package **only on a submodule's first load**
(`_find_and_load_unlocked`); every later import short-circuits on `sys.modules`
and never re-binds. Optica's first load of `optica.export` happens *inside*
`optica/__init__.py` — through `optica.api.simple`'s module-level
`from optica.export import manager` — **before** the alias is bound. So the
alias is bound last and nothing overwrites it.

**Demonstrated both ways** on a two-shape synthetic package: where the
subpackage is **not** pre-imported by `__init__`, a later `import pkg.sub` in
user code rebinds the attribute from the function to the module; where it **is**
pre-imported, the function survives. Optica is the second shape.

**The invariant is fragile and was undocumented.** Making
`api/simple.py`'s export import lazy — an ordinary refactor — flips Optica to
the first shape: the mutation was applied and **four of the five import orders
broke**, `import optica.export` alone included. The invariant now has a test of
its own (`test_the_subpackage_is_loaded_before_the_alias_is_bound`) and the five
orders are parametrized, so the next person to make that import lazy is told
why they cannot.

**For the amendment list.** The collision is a **plan contradiction**, not an
implementation choice: § "Python API" fixes `optica.export()` as a Tier 3 alias
and § "Code Structure" fixes `src/optica/export/`, and only one attribute can
exist on the package object. The code currently arbitrates it. The plan should
say which wins — and, if the function, that the subpackage must be imported
during package init for the alias to survive.

### The per-stage completion lines in `optica run` — the API prints them
**Pass:** 5   **Date:** 2026-09-20   **Where:** decided at the checkpoint 2 gate
**Missing:** the plan says the `✓ X complete` / `✗ X incomplete` lines are
printed for the browser steps "the moment a browser step hands control back"
(l.955) and for training "for standalone `optica train` and inside `optica run`
alike" (l.1089). It does not say **which layer prints them** once `optica run`
reaches its stages through `optica.run()`.

**Chosen:** the **API's stage functions print them**, through `olog`'s existing
`success`/`incomplete` vocabulary, and the CLI's `run` prints none of its own.
The training block's renderer moves into `api/simple.py`, and
`cli/classify.py`'s standalone `train` calls it — **one implementation, both
surfaces**.
**Why:** the block reports `patience`, `phase1_stopped_early` and
`classes_without_test`, which live on `TrainOutcome` and **not** on
`TrainResult`. Only the API layer holds both the outcome and `olog`, so it is
the only layer that *can* render the full block on the `run` path.

**Rejected:**
- **The CLI re-rendering from `RunResult`** — impossible without adding
  `patience`, `phase1_stopped_early` and `classes_without_test` to
  `TrainResult`, and pass-5.md item 2 forbids adding the
  "(N classes absent from test set)" field outright.
- **Leaving both renderers in place** (CLI's `_report_training` and a new one in
  the API) — two implementations of the same sentences, which is exactly the
  drift the warning contract's *one source, two surfaces* rule exists to
  prevent.
- **A new shared renderer module, or moving the renderer into `training/`** —
  `training/` deliberately imports no `olog` (outside `cli/` and `api/`, only
  `server/app.py` does), and a module § "Code Structure" does not have is more
  structure than the problem needs. `cli/` importing `api/` is the direction
  that already exists and creates no cycle.
**Reversible?** Yes — one function's home, plus its call site.

### Where the pipeline state model lives — `src/optica/pipeline.py`
**Pass:** 5   **Date:** 2026-09-20   **Where:** new top-level module
**Missing:** ambiguity 1 from the checkpoint 2 gate. The human resolved
ambiguity 2 to the strong reading — `optica.run()` honours **R**, because l.1339
makes the `--yes` table binding row by row "with no exceptions" and excepts only
the `config --init` row, l.1335 puts the API under that table, and l.195's row
is *R — resume*. That makes the state model **shared**, and the plan says
nothing about where it lives.

**Chosen:** a new top-level `src/optica/pipeline.py`, alongside `registries.py`.
**Why:** it reads all four steps' state — auto-fetch staging and the session
files, `dataset/`, `checkpoints/`, and the export container — so every existing
package would own a quarter of it. It holds decisions and no prompts, which is
what lets both surfaces consume it.

**Rejected:**
- **`input/manager.py`**, whose `short_circuits_acquisition` is the two-state
  version of the same question. Rejected because the model needs
  `training.checkpoints` and `export.manager`, and having the input layer import
  the training and export layers inverts the direction § "Code Structure"
  implies.
- **`api/simple.py`**, which the CLI may already import (the completion-line
  decision). Rejected because that module is a **surface**; a component both
  surfaces consume does not belong inside one of them, and `simple.py` is
  already the largest module in the package.
- **`cli/classify.py`** — the placement the state model would have taken if
  ambiguity 2 had gone the other way. Rejected by that resolution: the CLI layer
  holds no decisions, and the API now consumes this one.

**Two readings of "R resumes from the last incomplete step".** Implemented as
*the first step that is not complete*. The two name the same step for any state
the pipeline itself can produce, since a step cannot complete before the one in
front of it; they part only where a user brings a later stage's output by hand,
and there the earliest unfinished step is the one that must run for the rest to
have inputs. Recorded in the property's own docstring.

### `optica.run(start_at=…)` — public API surface added, deliberately
**Pass:** 5   **Date:** 2026-09-20   **Where:** `api/simple.py::run`
**Missing:** the terminal's **C** answer — *choose step* — has no way to reach
the API. `optica.run()` resolves **R** itself from the state model, but C names
a step, and a step that may be *complete* (the user asking to re-run training).

**Assumed:** one keyword-only parameter, `start_at: str | None = None`, taking a
`Step` value. None means R.
**Why:** without it the CLI needs its own stage sequencer beside
`optica.run()`'s — two implementations of the same order, which is the drift the
*one source* discipline forbids.

**Rejected:**
- **Expressing C by discarding**, so the state model's own `resume_from` lands
  on the chosen step. Works for every step except a **complete** one: after
  discarding what follows it, it is still complete, so the resume point is the
  step *after* it — the opposite of what the user asked for.
- **Discarding the chosen step's own output too**, which would make it
  not-started. Rejected as destruction the plan does not sanction: it says the
  *later* steps' staging is discarded, and deleting a user's checkpoints because
  they asked to train again is exactly what the K/A/D/S prompt exists to avoid.
- **The CLI sequencing the Tier 4 functions itself for C** and calling
  `optica.run()` for R — two code paths for one pipeline, free to diverge.

**Flagged, not hidden:** this is public API surface added in the last pass that
writes `src/`, and a parameter cannot be removed afterwards without breaking
callers. It is one keyword-only parameter with a `None` default, so a caller who
never passes it sees no change; the values are the four `Step` names, which the
error lists on a wrong one.

### An inconsistency inside the plan's own example block
**Pass:** 5   **Date:** 2026-09-20   **Where:** plan l.744-752, observation only
The prompt line in the example reads
*"Resume from last completed step (training)?"* while the prose immediately
below says *"R resumes from the **last incomplete** step"* — and in that same
example training is the ✗ incomplete one. The parenthetical names the right
step; the label in front of it does not. **The prose is normative and the code
follows it**; the literal string is reproduced as the plan shows it, because
output text is the plan's to fix. For the amendment list.

### `optica run`'s CLI body — four local decisions
**Pass:** 5   **Date:** 2026-09-20   **Where:** `cli/classify.py`

1. **`--output` stays the shared `Path` option and is always a container.**
   Pass 4 handed forward that `run`'s `--output` "cannot see a trailing slash"
   because `Path` drops it, and that `export`'s `str` option shows the form.
   Taken the other way: `run`'s `--output` **governs all run outputs — the
   export folders *and* the project-local training log** (§ "`--output` path
   handling"), so the export table's name-versus-container question cannot
   arise. Letting the last component name a single export folder would put the
   run's log inside a folder named after one export. `run` therefore takes
   `train`'s `_ensure_output` — create where absent (`--yes` answers Y), hard
   error on a file — and the trailing slash has nothing left to disambiguate.
   *Rejected: the `str` + N/C/A treatment, which would make an incoherent
   destination expressible in order to ask about it.*

2. **`run --checkpoint-rank` takes one rank.** `RunResult` carries a single
   `ExportResult` (§ "Result types"), so a run exports one checkpoint. Several
   ranks is a hard error naming `optica export --checkpoint-rank 1,2`, which is
   where multi-rank export lives. *Rejected: exporting each rank in a loop,
   which the result type cannot represent; and silently taking the first, which
   discards input the user wrote.*

3. **The entry extras check moved after the dry-run return, and is scoped to the
   stages that actually run.** The standing rule is that a composite entry point
   raises "before fetching begins" — a dry run never fetches, spends no quota
   and holds no attention, so demanding the torch stack to *print a plan* would
   make `--dry-run` unusable on a machine that has not run `optica setup`, which
   is exactly the machine a plan is most useful on. For the same reason a stage
   the resume point skips no longer requires its extra: resuming at export does
   not need the web extra. *Rejected: checking every extra unconditionally,
   which is what pass 2's `fetch` does — `fetch` reaches its dependency within
   seconds either way, and `run` does not.*

4. **`_not_yet` is gone.** It existed so an unbuilt stage body raised a plain
   error rather than a traceback; `optica run` was its last call site. The
   module docstring's "stage bodies that belong to later passes" paragraph is
   replaced by what is now true: every command's body is here, and `run` is the
   one that hands its sequence to `optica.run()`.

**A near-miss worth recording.** A mutation meant to remove `--yes`'s **R**
answer from the resumption prompt was applied by a first-occurrence string
replace and landed on the *labeling* resume prompt instead — three call sites
share that line. The run tests passed, which is what exposed it: a mutation that
changes nothing is not evidence that a test bites. Re-applied by line number,
two tests failed as they should.

### For the plan amendment list — three items pass 5 found and did not act on
**Pass:** 5   **Date:** 2026-09-20   **Where:** observations; `spec/` untouched
Gathered here so the next reader does not re-derive them.

1. **`optica.export` — the plan fixes two things that cannot both exist.**
   § "Python API" makes `optica.export()` a Tier 3/4 flat alias (its own example
   calls it) and § "Code Structure" makes `src/optica/export/` the Export
   Manager's package. Only one `export` attribute can exist on the `optica`
   package object, so the code currently arbitrates. **An amendment should say
   the function wins, and that the subpackage must be imported during package
   init for the alias to survive** — the alias is stable only because
   `api/simple.py` imports `optica.export` at module level, which makes the
   submodule's first load happen before the alias is bound. Proven by making
   that import lazy: four of five import orders then break. See the entry above.

2. **The R row's reading took six passages to establish.** That
   `optica.run()` honours **R** follows from l.195's table row, l.1335 putting
   the API under that table, and l.1339 making it binding row by row "with no
   exceptions" while excepting only `config --init`; l.752 supplies what R
   means, and l.1347/l.1380 are about `dry_run`'s `plan` rather than about
   `run()`, so they are not counter-evidence. The plan is clear enough to decide
   and the decision was made, but **§ "Python API" says nothing about
   resumption**, and the next reader should not have to assemble six passages.
   An amendment should state it where the API is specified.

3. **The example block contradicts its own prose.** At l.744-752 the prompt
   reads *"Resume from last completed step (training)?"* while the sentence
   below says *"R resumes from the **last incomplete** step"*, and training is
   the ✗ incomplete one in that very example. The parenthetical names the right
   step; the label does not. The prose is normative and the code follows it; the
   literal string is reproduced as written, because output text is the plan's to
   fix.

### Pass 5, checkpoint 3 — what was NOT exercised live
**Pass:** 5   **Date:** 2026-09-20   **Where:** stated before building, restated after
A live end-to-end `optica run` was out of scope: it drives both browser steps
and a real training run. **A green checkpoint 3 is not evidence that the chain
ran.** The list below is the prediction made at the checkpoint 2 gate, unchanged,
plus what building it added.

**Predicted, and still true:**
- No real browser session opened by `run`'s curate or label stage, so no live
  check that the step-level resume prompt is suppressed **while a browser step
  resumes** — only that `run` does not call the prompting path.
- No live interrupt (Ctrl+C) inside a `run`-driven training stage; exit 130 from
  within a stage is asserted from a raised `KeyboardInterrupt`, not a signal.
- No live resume of a genuinely interrupted pipeline: every staged state is
  **constructed** on disk, never left behind by an interrupted run.
- No live export of a model trained inside the same `run` invocation.
- The four-step status model is verified against constructed states only, so a
  state real usage can produce but the fixtures do not construct is unverified.

**Added while building:**
- **The only live `optica run` was `--dry-run`**, in `.smoke/run3/`. It printed
  the mode, the classes, the destination and `Starts at: train` against a
  constructed dataset, and exited 0. No stage ran.
- **No prompt was answered at a real terminal.** The R/C/S prompt, the step
  selector, the discard confirmation and **S** are driven through scripted
  `typer.prompt`/`typer.confirm`, so what a person actually sees — Rich's
  rendering of the menu, the default marker, the ✓/✗ glyphs on a non-UTF-8
  console — is unverified.
- **The per-stage completion lines the API now prints have not been seen from a
  real `optica run`.** `report_training` is covered through `optica train`'s
  existing tests, and `Labeling complete` / `Curation complete` are not
  exercised by any browser session at all.
- **`discard_after` was exercised on constructed trees only**, so the case where
  a checkpoint folder or an export folder is locked by another process — the
  Windows failure mode for a delete — has never run.
- **The `--output` create prompt and S's staging clear** likewise ran against
  constructed trees, never against a directory a real run had populated.

### Amendment item 4 — `optica.run(start_at=…)`
**Pass:** 5   **Date:** 2026-09-20   **Where:** observation; `spec/` untouched
Public API surface the plan does not specify, added in the last pass that can
add any. § "Python API" enumerates the API's parameters and this is not among
them; the plan's own mapping rule says a prompt *answer* has no API equivalent
(`--yes`, `--ci` and `--force` have none), while the terminal's **C** answer
names a *step*, which nothing else can carry into `optica.run()`. The reasoning
and the three rejected alternatives are logged above and the human has not
reopened them. **The plan should say whether the parameter exists**, rather than
leaving the code to have decided: a parameter cannot be removed after V1 without
breaking callers, and the next reader has no way to tell a specified parameter
from one the implementation invented.

### Pass 5, checkpoint 4 — what a green `optica setup` will NOT mean
**Pass:** 5   **Date:** 2026-09-20   **Where:** stated **before** the run, as at
checkpoint 3
This machine's `.venv` already holds **all extras plus the whole torch stack**,
audited in pass 4 (`notes/verified.md` § "What `.venv` holds, against
`pyproject.toml`'s declared dependencies and extras"). That decides what a live
`optica setup` can and cannot show:

- **The idempotent second run is the easy case and is the one that will run.**
  Every package is present, so the Skip path is what executes: setup finds a
  compatible installed set and installs nothing. **A green idempotency run is
  evidence that setup does not redo work. It is not evidence that installation
  works.**
- **The first-install path will not run live at all.** No `pip install` will be
  executed against a missing package, so the install command construction, the
  per-extra progress bars, the failure path and the incomplete message are
  covered by tests alone. Running the real thing would mean uninstalling the
  torch stack from the environment the rest of this pass depends on.
- **The two-command install split is therefore unverified end to end.** Pass 0
  measured that `timm` and `scikit-learn` are absent from the torch index and
  that `--index-url` replaces PyPI; the commands built from that partition are
  asserted in tests, never run.
- **Which setup branch is testable on this machine** (pass-5.md's *Record*):
  - **GPU-detected: yes.** `nvidia-smi` reports an RTX 4070 Ti with driver CUDA
    13.1, so the hardware scan's CUDA branch, the `torch-cpu`-on-a-CUDA-machine
    safety prompt, and `torch-auto` resolving to the `cu130` index are all
    exercisable live.
  - **No-GPU: no.** Nothing on this machine can make `detect_gpu()` report CPU
    without replacing it, so the `torch-gpu`-with-no-GPU safety prompt and the
    CPU index resolution are written-but-never-run live, the same standing as
    pass 4's MPS path. Tests construct the condition by replacing the probe.
- **`--ci` is testable in full**, because it installs nothing and detects no
  environment. What it cannot show here is the CI environment itself: all three
  runners execute **outside a venv**, and this machine is inside one.

### `optica setup` — six decisions the plan leaves to the implementation
**Pass:** 5   **Date:** 2026-09-20   **Where:** `cli/setup.py`, `utils/system.py`,
`utils/mlstack.py`, `utils/prompts.py`

1. **Where setup's detection lives.** `utils/system.py` gains the environment
   half — `conda_prefix`, `running_in_conda`, `is_venv`, `discover_venvs`,
   `venv_python`, `activation_command` — and the metadata half,
   `installed_version` and `pairing_problem`. Its docstring already said pass
   5's setup flow was its main consumer, and none of it imports torch, which is
   the property that module exists to hold. The one piece that **must** import
   is `stack_import_problem`, the *"imports successfully"* half of *compatible*;
   it went to `utils/mlstack.py`, which owns every lazy torch import. *Rejected:
   putting the package checks in `registries.py`, which is data and resolution
   and says it detects no hardware.*

2. **`--ci` returns before the pre-phase exists.** Not a flag consulted inside
   environment detection — the `if ci:` branch runs `_ci_init()` and returns, so
   there is no code path from `--ci` to a prompt or a probe. A test replaces
   every detection entry point with a function that fails the test, and another
   replaces `typer.prompt`/`typer.confirm` the same way **with a terminal
   present**, because a prompt reached in CI is a hard exit 1 by pass 1's
   design. Mutating `--ci` to resolve the environment fails five tests.

3. **Two pip commands for the torch stack, not `--extra-index-url`.** The
   partition is `registries.py`'s; the choice is here. `--index-url` replaces
   PyPI and `timm`/`scikit-learn` are not on the torch index (measured
   2026-09-12), so one command cannot install all four. *Rejected:
   `--extra-index-url`, which lets pip choose per package and can silently pull
   a PyPI torch over the variant's build — a test asserts the flag appears in no
   command Optica builds.*

4. **Case 1 is checked before the mismatch.** The plan lists the mismatch as
   case 2 and says case 1 "wins outright". Checking the mismatch first would
   raise on a machine where `CONDA_PREFIX` names an environment Optica **is**
   running from, since the two paths differ textually. Found by a test that
   constructs an active conda environment.

5. **The Review renders the per-package states under the torch line.** The plan
   gives the Extras section as one row per extra with a size, and the
   idempotence states as "per package". Both are printed: the extra's row, then
   its four packages indented beneath. *Rejected: aggregating the four into one
   state, which cannot express "three present, one absent" — the state a
   partially installed stack is actually in.*

6. **`prompts.ask` was added** for the two free-text prompts setup needs — the
   new environment's name and the API key. It shows a default only where there
   is one, so an Enter that means *skip* is not dressed up as a choice. Nothing
   in it consults `--yes`, which has no role in setup at all.

**`--ci` ran live** in `.smoke/ci4/` against a throwaway home: it created
`~/.optica/config.toml`, printed one completion line, ran no pip command and
exited 0. The idempotent second run belongs to checkpoint 5.

### Pass 5 — closed
**Date:** 2026-09-20
**Built:** `registries.py`, `pipeline.py`, `api/simple.py`, `api/classifier.py`,
`api/__init__.py`, `classify.py` (the task namespace), `cli/setup.py`, the
resumption path in `optica.run()`, `optica run`'s CLI body, and additions to
`utils/system.py`, `utils/mlstack.py`, `utils/prompts.py`,
`training/checkpoints.py` and `export/manager.py`.
**Milestone:** met, as **two separate claims**, both verified by a checker that
reads disk and never opens the commands' output (`notes/verified.md` § "Pass 5
milestone"). Claim 1 — `optica.run()` works from Python: 27.6 s, exit 0, 24 of
24 artifact checks, three mutations proved the checker bites. Claim 2 —
`optica setup` redoes no work on a second run: both runs exit 0, 11 of 11
snapshot checks, four mutations proved it bites. **Claim 2 does not carry claim
1, and neither carries installation:** every package was present before either
setup run.
**Scope change:** pass 5 was widened between checkpoints 0 and 1 to include
`optica run`'s CLI body, which no pass's Build list owned.
**Assumptions logged this pass:** 14 entries above, plus four amendment items.

## The standing list — written but never exercised live

Everything below is implemented and tested, and has **never run against the real
thing**. It is the pass's most load-bearing hand-off: pass 6 writes the README
from it, and anything a README claims that appears here is a claim no live run
supports.

**The whole browser surface.** `optica label`, `optica curate`,
`optica.label()`, `optica.curate()` and both browser stages of `optica run` /
`optica.run()`. The milestone run used `mode="clip"` precisely because it has no
browser stage. *(Pass 3 drove the server and both pages live; what has never run
is a browser stage **inside the composite pipeline**.)* With it: the suppression
of step-level resume prompts inside `run` — asserted only as *the prompting path
is not called* — and the API's `Labeling complete` / `Curation complete` lines.

**The whole terminal prompt surface added this pass.** No prompt was ever
answered at a real terminal: the R/C/S resumption prompt, the **C** step
selector with its *listed but not selectable* lines, the discard confirmation,
**S**, setup's environment prompts, the extras prompt, the variant prompt, the
API-key prompt, the Review's `Proceed with installation?`, and both hardware
safety prompts. Every live run this pass was non-interactive. Rich's rendering
of those menus, and the default marker, are unverified.

**`optica run`'s resumption, executed.** The state model was read live (the
`.smoke/run3` dry run correctly reported `Starts at: train` against a
constructed dataset), but no live run ever **started from** a resume point: the
milestone ran a clean project from the top. Every REVIEW/TRAIN/EXPORT start is
test-only, and every staged state in those tests is constructed rather than left
behind by a real interruption.

**Interruption and its exit codes.** No live Ctrl+C inside a `run`-driven stage.
Exit 130 from within a stage is asserted from a raised `KeyboardInterrupt`, and
exit 3 from a declined prompt from a scripted answer.

**`optica setup`'s first-install path — all of it.** No `pip install` ran, on any
path. That leaves unexercised: the install command construction, the **two-command
torch split** (asserted, never executed), the per-extra progress, the failure
path, the incomplete message and its retry command, and `--upgrade` and the
repair path in their entirety.

**Setup's environment cases, except the one this machine is in.** Live, only
*case 1 — an active venv Optica runs from*. Never run: the mismatch hard error,
the single-found confirmation, the more-than-one picker, creating a venv
(`python -m venv`), the create-name collision, skip-into-system-Python, and
**every conda path** — there is no conda on this machine, so `running_in_conda`,
the `Conda:` label and the conda interpreter path are written and never run.

**The no-GPU branch.** This machine has an RTX 4070 Ti, so `detect_gpu()` cannot
report CPU without being replaced. Unexercised live: the
`torch-gpu`-with-no-GPU safety prompt, the CPU index resolution, and every
CUDA index except `cu130` (`cu126`, `cu128`, `cu129`, `cu132` are table lookups
against a driver version no run has had).

**The MPS path**, carried forward from pass 4: `select_device`'s Apple-silicon
branch is written and has never been run.

**The warning contract.** The milestone run produced **zero** warnings, so
`RunResult.warnings` was empty and no `OpticaWarning` was ever emitted by a live
run. Every one of the sixteen `WarningCode` values, and the `warnings.warn`
emission itself, is exercised by tests alone — including
`checkpoint_run_incomplete`, whose condition the live run could not produce
because its checkpoints finished.

**Tier 5.** `Classifier` has never been constructed outside a test: no live
`clf.fetch().train().export()` chain, and no live
`Classifier(checkpoint_path=…)`.

**The Tier 3/4 functions individually.** `optica.fetch()`, `optica.train()` and
`optica.export()` ran live only *inside* `optica.run()`; none was called on its
own, and `optica.label()`/`optica.curate()` not at all.

**`discard_after` against a locked file** — the Windows delete failure mode —
and `--output`'s create prompt against a directory a real run had populated.

**Every platform but Windows.** Every live run this pass was on Windows 11. CI
on Ubuntu is the only Linux check there is and it installs no torch stack;
macOS has no check at all. `optica setup --ci` has never run **on a runner**,
outside a venv — pass 6 adds it to the matrix, and that is the first time it
will.

### Amendment item 5 — which entry-time check wins: extras, or the blocklist definition
**Pass:** 5   **Date:** 2026-09-20   **Where:** found by CI, on all three runners
**The failure:** `optica.fetch(["defective","cat"])` raised `OpticaCLIPError`
where the test expected `OpticaValidationError` at the definition step. It
passes on this machine because `.venv` has `optica[clip]` and fails on every
runner because none does.

**The plan places both checks at entry and orders neither.**
- **l.769** — *"**The user-definition prompt is the sequence's one
  non-defaultable step**, so it fires wherever a prompt can fire and raises
  `OpticaValidationError` where one cannot, naming the blocklisted class and
  that a concrete definition is required — the same disposition the Python API
  takes, and the reason an unattended run with a blocklisted `-c` name refuses
  **before any fetch begins** rather than blocking on stdin."*
- **l.1543** — *"**`optica fetch --mode curate` with a blocklisted `-c` name is
  the one exception, and it takes the entry check.** … blocklist membership is
  a test on the class names, which are invocation arguments, so this is knowable
  at entry … and **the check fires at entry accordingly**."*
- **l.226** — the standing rule both inherit: *"any check whose answer is
  knowable before work begins … run before anything is written or any browser
  opens."*

Both are specified to fire at entry and nothing says which precedes the other.
Two coherent readings follow:

- **(A) the extras check first**, on l.1543's plain words — *the check fires at
  entry accordingly*. This is what ships.
- **(B) the definition raise first**, on l.1543's stated *reason*: the entry
  check exists because *"the blocklist flow runs the user-definition prompt,
  group-or-separate, the per-sub-term counts, the overlap check and the
  confirmation, the fetch then completes in full, and only then does the grouped
  path score images and raise."* In a **non-prompting** caller that sequence
  cannot occur — the definition raises immediately, no fetch runs and no quota
  is spent — so the work the entry check protects does not exist. Under (A) a
  caller with no clip extra is told to install it for a call that would fail on
  the definition regardless.

**Not picked.** This is a plan question and the amendment session has four items
already; this is the fifth. Note that **pass-5.md item 6 does not settle it
either**: it says the API raises `OpticaValidationError` at the definition step,
which is true under both readings whenever the extra is present, and says
nothing about a caller who lacks it. The test had over-specified.

**Is checkpoint 3's move related?** Not the same code — that moved
`_require_extras` in `api/simple.py::_run`, after the dry-run return and scoped
to the stages that actually run, and it left `_fetch`'s check untouched. But it
is the same *kind* of question — *does the entry extras check fire for work that
will not happen?* — and it was answered there in the direction of **(B)**: a dry
run does no work, so it requires no stack, and a stage the resume point skips
requires no extra. That precedent is recorded here because it bears on the
amendment; it was not used to decide this one.

**What ships meanwhile:** (A), unchanged. Two tests now pin both branches, each
constructing the extra's presence in its own body, so whichever way the
amendment goes the change is visible as a failing test rather than a silent
drift.

### The clip fixture recurred because it was module-local
**Pass:** 5   **Date:** 2026-09-20   **Where:** `tests/conftest.py`
Pass 4 met this exact pattern and fixed it with `clip_installed` — *"the clip
extra is present — constructed, so CI (which never has it) agrees"* — defined at
module level in `tests/unit/cli/test_fetch_command.py`. A module-level fixture
is visible only to its own module, so `tests/unit/api/test_simple.py` could not
see it; that file imports `World` and `_jpeg_for` from the same module **by
name**, which is why the fixture looked available and was not.
`clip_installed` and `clip_absent` now live in `tests/conftest.py` as the one
definition, and the CLI module's local copy is gone.

**Process, not code:** `.smoke/ci-venv` — Core plus `optica[test]`, no torch, no
`fastapi`, no `open_clip`, editable-installed against the working tree — was
built in pass 3 for exactly this and **pass 5 never ran it**. Run now, before
the fix, it reproduced CI exactly: `1 failed, 2324 passed`. After: `2326 passed,
26 skipped, 76 deselected`, with `ruff` and `mypy` clean under that interpreter
too. Running the suite CI-style at each checkpoint is what caught this in passes
2, 3 and 4; skipping it is what let a green checkpoint 5 hide a red CI.

### `CLAUDE.md`'s pass 5 row omitted three modules
**Pass:** between 5 and 6   **Date:** 2026-09-20   **Where:** `CLAUDE.md` § "Build order", pass 5 row
**Found:** the row read *"`api/simple.py`, `api/classifier.py`, `cli/setup.py`,
the registries"*. Three modules pass 5 built are absent from it:
- `src/optica/registries.py` — placed at top level under the gap rule, so that
  `api/` never imports `cli/`. Logged in checkpoint 1.
- `src/optica/pipeline.py` — the four-step resumption state model, placed at top
  level because both surfaces consume it and it reads staging, `dataset/`,
  `checkpoints/` and the export container. Logged in checkpoint 3.
- `optica run`'s CLI body in `cli/classify.py` — the mid-pass scope widening.
**Action taken:** the row now names all three. `CLAUDE.md` is standing
instruction read automatically by pass 6, so a scope table that understates what
exists is live rather than historical.
**Not corrected:** `notes/passes/pass-5.md`'s Build list. Its pass is closed and
the omission is historical, per the precedent applied to `pass-0.md` and
`pass-2.md` and against the one applied to `pass-3.md` and `pass-4.md`, which
were corrected because they were still unused.
**Why `optica run` was missing in the first place:** no pass's scope named it,
though three artifacts assumed pass 5 owned it — `pass-5.md`'s own amended item
5 refers to *"`optica run`'s R/C/S"* as a prompt this pass adds, pass 2 handed
forward *"Pass 5: `optica run` sequencing"*, and pass 4 handed forward *"`run`'s
`--output` cannot see a trailing slash"*. It is the fifth instance of pass
prompts written from the plan and never read back against it, and the only one
that was a missing scope line rather than a wrong claim. Caught by pass 5's
opening message, which replaced the gap rule's *log and keep building* with
*say so loudly*, on the grounds that pass 6 writes no `src/` and there is no
later pass to inherit a log entry.

### Plan amendment session 4 — items 19–23 decided
**Pass:** between 5 and 6   **Date:** 2026-09-21   **Where:** `spec/optica-plan-v1-core.md`
**What this is:** the outcome of the fourth out-of-repo plan-amendment session,
on pass 5's five items. It is recorded here because pass 6 reads this log in
full and writes the README from the plan. The `spec/` edits were applied by the
user, not by an agent. Full reasoning is in
`optica-plan-amendment-change-record-2026-09-21.md`.

| # | Item | Disposition | Sites |
|---|---|---|---|
| 19 | `optica.export` — the flat alias collides with the `export/` subpackage | **Ratified** — the function wins; the init-order invariant is stated. Renaming the subpackage goes to the fast-follow | l.1417 |
| 20 | `optica.run()` honours R, established only across four passages | **Amended** — one clause | l.1339 |
| 21 | `optica.run(start_at=…)` — public surface the plan does not specify | **Declined** — the plan does not specify it; the fast-follow makes it private | — |
| 22 | The resume prompt says *last completed step* | **Deferred** — the string and l.748 change together in the fast-follow | — |
| 23 | The entry extras check runs before the blocklist definition's raise | **Amended** — accepted limitation; the reorder goes to the fast-follow | l.1543 |

**For pass 6 — what the README must not say.**
- **Do not document `optica.run(start_at=…)`.** The plan declined it. Its
  docstring already shows it in `help()`; that stays, because it is `src/`.
- **Do not say that an unattended run with a blocklisted `-c` name always
  reports the definition error.** Without the clip extra it reports the missing
  extra first — on `fetch` and `run`, CLI and API alike. l.1543 now records this
  as an accepted limitation.
- **If the README quotes `optica run`'s resume prompt, quote it as V1 prints
  it.** l.748 is unchanged, and so is `cli/classify.py`'s string.
- **Spell out every extras install command in full** — `optica[clip]`,
  `optica[web]` — and do not copy the CLI's missing-extra messages as they print.
  See the finding below.

**Item 19 — the invariant, as the plan now states it.** `optica.export` is the
flat alias, not the subpackage, whatever the caller imports afterwards, and the
subpackage is imported during package initialization, before the alias is bound.
Today that happens through `api/simple.py:48`'s module-level
`from optica.export import manager as export_manager`, before `__init__.py:54`
binds `export = _task.export`. The plan states the requirement, not which module
meets it. `test_the_subpackage_is_loaded_before_the_alias_is_bound`
(`tests/unit/api/test_init.py:73`) is what enforces it. The rebinding was
reproduced this session on a synthetic package under Python 3.12.3: four of five
import orders leave the module when the subpackage is not loaded during init,
and all five leave the function when it is.

**Item 21 — what V1 ships anyway.** `start_at: str | None = None`,
keyword-only. Its values are `fetch`, `review`, `train` and `export`, and any
other value raises `OpticaValidationError`. `discard_after` is called only from
`cli/classify.py:2557`, so the API itself never discards anything. The decline
is about the surface, not safety. The dry-run `plan` also carries a `start_at`
key (`api/simple.py:1882`), a fifth key beyond the four resolutions l.1380
lists. It goes to the fast-follow with the parameter.

**Item 23 — observed, not inferred.** Probes were run in `.smoke/ci-venv` with no
clip, torch or fastapi, stdin `NUL`, and a private home.
`optica.fetch(["defective","cat"])` and `optica fetch -c defective,cat --yes`
raise `OpticaCLIPError`. `optica.run(...)` and `optica run ... --yes` raise
`OpticaWebError`, which is the first missing extra. That clip belongs to the
same check on `run` is `_require_extras` as logged in pass 5; it has not been
observed on its own.

### The CLI's missing-extra messages drop the extra's name — finding
**Pass:** between 5 and 6   **Date:** 2026-09-21   **Where:** CLI error output;
found by amendment session 4's item 23 probes
**Observed:** `optica fetch` prints
`✕ CLIP filtering requires the clip extra. Run: optica setup --include-extras clip or pip install optica`,
and `optica run` prints `…Run: optica setup or pip install optica`. Plan
l.1536–1537 specify `optica[clip]` and `optica[web]`. `str(e)` on the same
exceptions keeps the brackets, so the text is lost when it is rendered.
**Why:** Rich markup reads a bracketed token that starts with a lowercase letter
as a style tag and drops it without an error. This was reproduced with Rich
15.0.0: `[clip]`, `[web]` and `[y/N — n to exit]` vanish; `[R]`, `[C]` and `[F]`
survive, since uppercase tags are not markup; an escaped `\[clip]` survives.
**Consequence:** the `optica setup …` half of each message is correct. The `pip`
half tells the user to install a package they already have.
**Not fixed.** Pass 6 writes no `src/`. Whether V1 ships with this is the
human's decision; otherwise it is fast-follow.
**Scope not yet known — the first two observations:**
- `findstr /n /c:"escape" /c:"markup" src\optica\utils\logging.py`, which shows
  whether `olog` escapes anything.
- `findstr /s /n /c:"n to exit" src\*.py`, which shows which path prints the
  overwrite prompt's options.

## Pass 6 — packaging and documentation

### Checkpoint 0 — the Rich markup fix, scoped and applied
**Pass:** 6   **Date:** 2026-09-21   **Where:** `src/optica/utils/logging.py`,
`tests/unit/utils/test_logging.py`
**Why this is `src/` in a no-`src/` pass:** assigned deliberately in the pass 6
opening message, the way pass 4 and pass 5 each received one.

**Scope, measured before the fix.** The two `findstr` probes the amendment
session 4 entry left behind were run first.

- `findstr /n /c:"escape" /c:"markup" src\optica\utils\logging.py` → **no
  matches**. `olog` escaped nothing; every helper interpolated caller text
  straight into a Rich markup string.
- `findstr /s /n /c:"n to exit" src\*.py` → `cli/classify.py:928`, a single
  site, and it spells the options `(n to exit)` in parentheses. Nothing bracketed.

Neither probe bounds the defect on its own, so the sweep was widened to the
whole of `src/`: an AST walk over every string literal **and** every f-string
(placeholders standing in for the expressions), rendering each through
`rich.text.Text.from_markup` and reporting any bracketed token that did not
survive. That is the sweep-for-what-should-no-longer-be-there rule — the
question asked was *which strings does Rich eat*, not *which strings did I mean
to change*.

**Eleven sites matched. Two are the defect:**

| Site | Token | Verdict |
|---|---|---|
| `exceptions.py:145` `OpticaWebError` | `[web]` | **Defect** — plan l.1536 |
| `exceptions.py:159` `OpticaCLIPError` | `[clip]` | **Defect** — plan l.1537 |
| `registries.py:141,152` `pip_extra` | `[web]`, `[clip]` | Not printed — a subprocess argv element (`cli/setup.py:578`) |
| `registries.py:435,438,441` `_PIP_NAME_HINTS` | `[web]`, `[clip]`, `[all]` | Not printed — dict keys, looked up only |
| `cli/setup.py:299` `choose("[auto/cpu/gpu]", …)` | `[auto/cpu/gpu]` | Not Rich — `prompts.choose` goes through `typer.prompt`, i.e. Click's echo |
| `export/pytorch.py:136` | `[index]` | Not printed — generated README text, written to a file |
| `input/classes.py:124` | `[a-z]` | Not printed — a regex |

The remaining matches were deliberate style tags (`[bold red]`, `[dim]`,
`[progress.description]`). **Two message strings is a handful**, so the fix
proceeded rather than stopping.

**Where the fix went, and why not in the literal.** The plan's text was never
wrong and `str(exc)` carried `optica[web]` correctly throughout; only the
*rendering* lost it. Writing `optica\[web]` into the message literal would have
fixed the screen and corrupted `str(exc)`, which the Python API hands to a
caller who never goes near Rich. So `logging.py` now escapes caller-supplied
text at the point it reaches a console — `status`, `detail`, `success`,
`incomplete`, `warn` (message, why, fix) and `render_error` (message, why, fix,
options, default). The style tags stay outside the escaped text. `escape()` is a
no-op on text with no brackets, including Windows paths, which was checked
before applying it.

No caller passes deliberate markup through an `olog` helper — verified; the
markup in `cli/` is written at direct `console.print` sites, which construct
their own tags — so escaping inside the helpers breaks nothing.

**Verified through the real CLI**, in `.smoke/ci-venv` (Core + `optica[test]`,
no clip, fastapi or torch), stdin from `/dev/null`, private home:

- `optica fetch -c cat,dog --mode clip --yes` → `… or pip install optica[clip]`
- `optica run -c cat,dog --yes` → `… or pip install optica[web]`

Both now match plan l.1536–1537 exactly.

**Proved by mutation**, four ways, because four of the eight new tests are
guards that must pass in both directions:

| Mutant | Fails |
|---|---|
| A — `escape` replaced by identity (the pre-fix behaviour) | the 4 survival tests |
| B — escape the whole formatted line, tags included | `test_the_style_tags_are_still_markup` |
| C — double-escape the message | the 3 that assert the backslash never reaches the screen |
| D — the rejected fix: escape written into the `exceptions.py` literal | `test_the_message_itself_was_never_wrong`, and 2 more |

Every one of the eight is killed by at least one mutant.

**Found, not fixed — deliberately out of scope.** Around sixty direct
`olog.*_console.print` sites under `cli/` bypass the helpers and interpolate
dynamic text — class names, paths, `exc.format_message()` — into a markup
string without escaping. No *specified* string is affected (the AST sweep found
none), so this is not the plan-conformance defect that was assigned; it is the
same mechanism reaching **user data**. A user whose class name or output path
contains a lowercase bracketed token would see it silently dropped. Left for the
human: it is a fast-follow candidate, and fixing it would have meant rewriting
sixty call sites under a "nothing else under `src/`" instruction.

**Gates.** Ruff clean, mypy clean (119 files), in both environments.

### Fast-follow backlog — unescaped caller text at the direct `console.print` sites
**Pass:** 6, checkpoint 0   **Date:** 2026-09-21   **Where:** `src/optica/cli/`
**Status:** found during checkpoint 0's sweep, deliberately not fixed. For
`optica-fast-follow-findings.md`, which lives outside the repo.

**Mechanism.** The same one checkpoint 0 fixed: Rich reads a bracketed token
whose first character is lowercase as a style tag and drops it with no error and
no warning. `[R]`, `[C]`, `[F]` are unaffected — uppercase tags are not markup —
which is why the whole class stayed invisible through five passes.

**Sites: 56 direct `olog.*_console.print` calls that bypass the `olog` helpers.**

| File | Sites |
|---|---|
| `cli/classify.py` | 31 |
| `cli/setup.py` | 11 |
| `cli/main.py` | 9 |
| `cli/config.py` | 5 |

Each formats its own string and prints straight to `out_console`/`err_console`,
so none of them passes through the escaping that `status`, `detail`, `success`,
`incomplete`, `warn` and `render_error` have had since checkpoint 0. Where such
a call interpolates caller-controlled text — a class name, a dataset or output
path, `exc.format_message()`, `type(exc).__name__: {exc}` — a bracketed token in
that text is silently dropped from the line.

**No specified string is affected.** Checkpoint 0's AST sweep over every literal
and f-string in `src/` found no remaining static message text that Rich eats;
the two that existed were the plan's missing-extra messages and are fixed. This
item is the same mechanism reaching **user data** instead.

**The fix is already built.** The helpers escape correctly. So this is routing
the 56 sites through them, or calling `escape()` at each — not new machinery.
Routing is the better shape where the site's only markup is a status glyph,
since the helper owns the glyph too; the handful that construct a genuinely
different line escape in place.

**Display-only. Disk contents are always correct.** The escape checkpoint 0
added is a render-time transformation and nothing else reads it: class names
reach folder names, the manifest and the config through their own paths, none of
which touches Rich. A user whose class name contains brackets gets a folder and
a manifest row with the name intact and a terminal line missing part of it. The
severity is a confusing screen, never a wrong file.

**Also carried to the README** at checkpoint 2, stated next to the other V1
limitations: class names and paths containing square brackets may display
incompletely in terminal output, while the files on disk are unaffected.

### Checkpoint 1 — the CI matrix
**Pass:** 6   **Date:** 2026-09-21   **Where:** `.github/workflows/ci.yml`,
`.github/constraints-min.txt`

**Extended, not rewritten.** `checkout@v6` and `setup-python@v6` were bumped by
hand before this pass and are unchanged. The triggers, the `concurrency` block,
`fail-fast: false`, the three runners and the `optica --version` tail step are
pass 1's, carried forward.

**The arrangement — four legs.**

| Leg | Runner | Python | Deps | Extras |
|---|---|---|---|---|
| `linux-min-py311` | `ubuntu-24.04` | 3.11 | **min** | none |
| `linux-max-py313-web` | `ubuntu-24.04` | 3.13 | max | **web** |
| `macos-max-py312` | `macos-latest` | 3.12 | max | none |
| `windows-max-py313` | `windows-latest` | 3.13 | max | none |

Both properties l.132 requires survive it: `optica[web]` on one leg, and three
legs installing no extras at all. It also covers 3.11/3.12/3.13 and both ends of
the declared dependency range without a cross product — 4 legs, against the 18 a
full `os × python × deps` product would cost.

**The min leg is real, not nominal.** `.github/constraints-min.txt` pins all
nine packages to the lowest release satisfying each `>=` bound; every floor
exists as a real release (`notes/verified.md`). The obvious objection — that
pinning Ruff to 0.16.0 and mypy to 2.3.0 reddens CI for reasons that have
nothing to do with Optica — was answered by building `.smoke/min-venv` and
running the full gate in it: Ruff clean, mypy clean, 2334 passed, identical to
the latest versions. So the min leg runs the whole gate rather than a reduced
one.

**`ubuntu-24.04`, pinned — the decision and why.** `ubuntu-latest` moves to
Ubuntu 26.04 over a rollout that **begins 19 October 2026 and completes 19
November 2026** (actions/runner-images#14748, fetched today). The brief gave the
start date; the month-long, *gradual* middle is the part that decides this. For
those four weeks `ubuntu-latest` is nondeterministic — two runs of the same
commit can land on different operating systems — and a red CI that cannot be
reproduced is exactly what *"it must not be left red"* forbids. Ubuntu is also
the only Linux check there is, since Windows is the development platform, so it
is the leg that should change when a human decides it changes and not otherwise.
GitHub's own README says to pin during a migration window. 24.04 is LTS,
supported to 2029, so the pin costs nothing near-term.
**Not pinned: `macos-latest` and `windows-latest`.** Deliberate asymmetry, on
the narrow grounds that no comparable migration is announced for either right
now. Three pins to maintain against one live hazard is worse than one. **When
the rollout completes, a human moves this leg to `ubuntu-26.04` or back to
`ubuntu-latest`** — that is the only maintenance this pin creates.

**A count in the brief that measurement did not support.** The brief says 27
tests — 19 route, 8 TestServe — skip without `optica[web]`. It is **62**: 49
route (34 parametrized functions), 8 `TestServe`, and 5 integration socket tests
the count omitted. Confirmed by difference, 2396 with the extra against 2334
without. Nothing about the requirement or the arrangement changes; CI recovers
more than the brief claimed.

**Two defects in the first draft of the workflow, both found by expanding it
rather than reading it.** A script walked the parsed YAML and printed each leg's
steps as concrete commands, with the `${{ }}` expressions evaluated:
- the extras expression produced `pip install -e ".[test],web"` — extras
  *outside* the bracket, which installs nothing optional and would have left the
  web leg silently skipping all 62 tests while reporting green. Now
  `".[test,web]"`.
- the Click/torch guard was written as `python -c … && exit 1 || echo …`, which
  depends on how the leg's shell treats a native command's non-zero exit;
  Windows legs default to `pwsh`, not bash. It now runs the check inside Python
  and exits on its own, so no shell semantics are involved.

Reading the file would have caught neither. This is the *print the breakdown,
not the total* rule applied to a config file: the expanded per-leg command list
is the breakdown.

**The guard is proved both ways.** `python -c "…find_spec…"` exits 0 in
`.smoke/ci-venv` and `.smoke/min-venv` (*"click and torch absent, as
required"*) and exits 1 in `.venv` (*"must not be installed on this leg: click,
torch"*). It runs only on the extras-free legs, because the web leg genuinely
has Click — uvicorn declares it.

**What is still unverifiable here.** A workflow cannot be checked without
pushing, and `git push` is denied to the agent (`pass-6.md` § "Known limit").
What *was* checked: the file parses as YAML; every leg's command list was
expanded and inspected; and each of the three distinct environments the matrix
creates was built locally and run through the whole step chain — install,
absence guard, Ruff, mypy, `optica setup --ci`, `pytest -m "not slow"`,
`optica --version`. The three stand-ins are `.smoke/min-venv`, `.smoke/ci-venv`
and `.smoke/web-venv`. All green. What that cannot cover: Linux and macOS
themselves, Python 3.12 and 3.13 (everything local is 3.11.9), and the runner
images.

### Plan l.289's folder-level `.gitignore` is not implemented — finding
**Pass:** 6, checkpoint 2   **Date:** 2026-09-21   **Where:** `src/optica/` — absent
**Found by:** verifying a README sentence before writing it.

**The plan requires it.** l.289: *"**Gitignored:** `./checkpoints/` and
`./optica-output/` … When Optica first creates either folder, **it drops a
`.gitignore` containing `*` inside that folder**. Optica never touches the
user's project-level or global `.gitignore`."* Two clauses; only the second one
ships.

**Observed:**
- `grep -rni gitignore src/ tests/ --include=*.py` returns **two docstring
  mentions** in `config/manager.py` and **no code**. No test covers it.
- Four folders created by the pass 4 live runs contain no `.gitignore`:
  `.smoke/pass4-live/milestone/optica-output/`,
  `…/milestone/checkpoints/`, `…/train-smoke/optica-output/`,
  `…/train-smoke/checkpoints/`.

**How it was missed.** The fast-follow reconciliation's line
(`notes/build-log.md`, F2) reads *"Advise users to add `.env` to their own
`.gitignore`. Optica never touches it (l.261, l.289)"* — it cites l.289 for its
second clause and does not register the first. The pass 6 opening message
inherited the same reading: *"Optica cannot, it writes folder-level `.gitignore`
files only."* Neither is wrong about `.env`; both assume a behaviour that was
never built. Four passes could have implemented it and none was told to.

**Not fixed.** Pass 6 writes no `src/`, and checkpoint 0 already spent this
pass's one deliberate exception. This is a missing feature rather than a wrong
plan, so the plan needs no amendment — the code needs the two lines, in
`export/manager.py` and wherever `checkpoints/` is first created, plus a test
that a fresh run leaves a `.gitignore` containing `*` in each. **Fast-follow.**

**What the README says instead.** The drafted sentence — *"it only ever writes a
`.gitignore` inside folders it creates itself"* — would have been false in the
one artifact every user reads. It now states the shipped truth, that Optica
never creates or edits any `.gitignore`, and gives the three lines to add:
`.env`, `checkpoints/`, `optica-output/`. That is more useful to a user than the
specified behaviour would have been, and it stays correct whether or not the
fast-follow lands.

### Checkpoint 2 — the README
**Pass:** 6   **Date:** 2026-09-21   **Where:** `README.md`

**Rewritten, not edited.** The file that was in the repo predated
implementation and described a package that does not exist: extras
`optica[onnx]` and `optica[server]` (the real ones are `web` and `clip`), a
`--format` flag and ONNX/REST export (both left V1), `--count` (it is
`--images-per-class`), and the space-separated `--classes "cat" "dog"` form
(V1 is comma-separated). Nothing in it could be salvaged by editing.

**Every checkable claim was checked against the package, not against the plan.**
A script parses the README and asserts against the installed `optica`:

| Checked | Result |
|---|---|
| The 20 config keys named | all exist in `config/defaults.py` |
| The 10 defaults quoted | all match (`epochs` 10, `batch_size` 32, `clip_threshold` 0.25, …) |
| The 33-flag table | 33 rows; every flag and alias exists; no flag invented; none omitted but `--checkpoint`, documented in `--checkpoint-rank`'s row as its alias |
| Each flag's *applies-to* column | matches the Typer command tree, flag by flag |
| The public names used in examples | all present, including `optica.classify.*` |
| The 7 `Classifier` properties | all real properties |
| `Status` values | `empty, data_ready, trained, exported` |
| Result attributes in examples | `RunResult.train/.export`, `TrainResult.best_val_accuracy`, `ExportResult.export_folder` |
| Config-object fields in examples | all real dataclass fields |
| Exit-code table | matches `ExitCode` exactly |

Two claims were corrected by it. The export folder holds **`model.pt`,
`class_names.json`, `model_info.json`, `usage_examples.md`** — the draft said "a
generated README", and the real filename is `usage_examples.md`; confirmed
against four real export folders from the pass 4 live run. And the Tier 5
checkpoint example named an invented path; `checkpoint_path` names a checkpoint
*folder*, so it now shows the real shape,
`./checkpoints/checkpoint_val0.983_epoch7`.

**The `~/.optica/logs/` claim is from a real run,** not from the plan: the pass 4
milestone wrote `run_20260915_141628_mobilenet_3classes.json` to both
`<output>/logs/` and `home3/.optica/logs/` — same filename, two locations.

**What the README deliberately does not say**, per the pass 6 brief and
`notes/build-log.md` § "The standing list":
- It does not describe any interactive flow as exercised. The Status section
  says the opposite, in the open: prompts are driven by tests, not typed at a
  terminal, and it names the other paths with no live exercise — Flickr, MPS,
  setup's first install and its CPU-only branch, and resumption after a genuine
  interruption.
- It does not call resume lossless. The *Start fresh* limitation from l.1020 is
  stated in full under Known limitations.
- It does not mention `optica.run(start_at=…)`. Amendment session 4 declined it.
- It does not present l.769's definition error as what an unattended caller
  sees. Known limitations carries l.1543's accepted order instead: the missing
  extra is reported first, CLI and API alike.
- Windows is *"supported and covered by CI; not a primary target"* — never
  untested.

**The CI badge is present and commented,** with a line saying why: a badge is a
claim, and it is uncommented after a human pushes and sees green.

**What the README says about CI coverage.** The matrix is four legs, so the
claim is made precisely: each of Python 3.11, 3.12 and 3.13 is tested on at
least one OS, and the minimum declared dependency versions are tested on one
leg. It states explicitly that this is *not* every Python version on every
platform, because a reader assumes a cross product otherwise.

**The bracket limitation** from checkpoint 0 is two sentences under Known
limitations, next to the others: display-only, disk always correct.

### Checkpoint 2b — l.289's folder-level `.gitignore`, implemented
**Pass:** 6   **Date:** 2026-09-21   **Where:** `src/optica/utils/workspace.py` (new),
`api/simple.py`, `cli/classify.py`, `training/trainer.py`
**Why this is `src/` in a no-`src/` pass:** assigned deliberately, as checkpoint
0 was. *"Checkpoint 0 already spent the exception"* was a reading, not a rule —
each exception is assigned per item.

**Sized first. Seven creation sites, in four modules.**

| Folder | Site | How it was created before |
|---|---|---|
| `--output` container | `api/simple.py:1474` (`_ensure_output`, train) | `output.mkdir(parents=True, exist_ok=True)` |
| | `api/simple.py:1736` (`_ensure_container`, export) | same |
| | `cli/classify.py:1477` (`_ensure_output`, train) | same |
| | `cli/classify.py:2032` (export, CREATE) | same |
| | `cli/classify.py:2060` (export, **N** — container is `path.parent`) | same |
| | `cli/classify.py:2063` (export, **C**) | same |
| `checkpoints/` | `training/trainer.py:379` | **never created explicitly** — it appeared as a `parents=True` side effect of `save_weights` |

The seventh is the one a `grep` for `mkdir` does not show as a defect: nothing
created `checkpoints/`, so there was no line to change — a call had to be added
at the moment of first write. Seven sites is a handful, so the work proceeded.

**`dataset/` was not touched.** `input/manager.py:349` and the rest of the input
layer are unchanged. The plan gitignores exactly two folders and `dataset/` is
the user's curated data. `TestTheContract::test_dataset_is_not_gitignored_by_any_call_site`
pins this by scanning the call sites, so extending the helper to `dataset/`
fails a test rather than quietly ignoring data someone meant to commit.

**The case l.289 does not settle, and the reading taken.** l.289's trigger is
*"when Optica **first creates** either folder"*. It says nothing about a folder
that already exists without a `.gitignore` — which is every `checkpoints/` and
output folder created by a build before this one.

**Reading taken: creation, and only creation.** `create_ignored` writes only
when its own `mkdir` succeeded; an existing folder gets nothing. Three reasons,
all from the text:
1. The trigger is literally creation.
2. l.289's second clause — *"Optica never touches the user's project-level or
   global `.gitignore`"* — sets a conservative posture toward ignore files that
   the loose reading would break, since Optica would be adding a file to a
   directory the user made.
3. It makes *never overwrite a user's `.gitignore`* structural rather than a
   special case: the only directory written into is one that did not exist a
   moment earlier, so there is nothing in it to overwrite.

**The gap this leaves, stated rather than hidden:** a folder created before this
shipped never gains a `.gitignore`. The README covers it — it tells users to add
such folders themselves and says Optica will not retrofit one.

**Other detail l.289 leaves open:** the file's exact bytes. It says *containing
`*`*; `GITIGNORE_BODY` is `"*\n"`, the trailing newline being text-file
convention. Git reads the two identically, and the test asserts
`GITIGNORE_BODY.strip() == "*"` so the specified content is what is pinned.

**Tested, and proved by mutation.** 13 tests in
`tests/unit/utils/test_workspace.py`, each constructing its folder state in its
own body, plus 3 wiring tests in `tests/unit/api/test_simple.py`. Four mutants:

| Mutant | Fails |
|---|---|
| A — never write the file (the pre-fix behaviour) | 4 |
| B — write it even when the folder already existed | 5 |
| C — write it beside the folder instead of inside | 5 |
| D — unwire the API call site, helper left intact | 2 |

D is the one that matters for the wiring: it leaves `create_ignored` perfect and
still fails, so those three tests are testing the call site rather than the
helper.

**Four existing tests changed, and why they had to.**
`tests/unit/cli/test_export_command.py::TestOutput` asserted *"the container
holds exactly one entry"* in four places. That assumption is now wrong by
design. They assert the same property through `_export_folders()`, which
excludes the ignore file, and one of them now asserts the full listing
`[".gitignore", "pets"]` outright. The count they were protecting — one export
per container — is unchanged.

**Verified against a real run, not against the source.** A real
`optica train` + `optica export` in `.smoke/cp2b/proj/`:
- `checkpoints/.gitignore` and `optica-output/.gitignore` both contain `*`.
- No `.gitignore` at the project root. None in `dataset/`.
- `git check-ignore -v` names the rules:
  `checkpoints/.gitignore:1:*` ignores `checkpoints/…/checkpoint.pt`, and
  `optica-output/.gitignore:1:*` ignores `optica-output/logs`. `git add -A`
  staged the whole `dataset/` and nothing under either ignored folder.
- Exporting into `mine/`, a folder created by hand holding
  `.gitignore` = `!keep.txt`, left that file byte-identical and still wrote the
  export into it.

**The README verification script was extended to do this itself.**
`verify_gitignore_claim.py` drives the installed `optica` binary in a throwaway
project, runs train and two exports, reads what is on disk, runs
`git check-ignore`, and then asserts the README paragraph says what the run
showed — 16 checks, all green. It is the same discipline as the flag table,
which is checked against the live Typer tree rather than against prose.

**Gates.** Ruff clean, mypy clean (121 files). `.venv` 2413 passed / 12 skipped
/ 76 deselected; `.smoke/ci-venv` 2351 passed / 26 skipped / 76 deselected.

### Checkpoint 3 — CHANGELOG, and the classifiers confirmed
**Pass:** 6   **Date:** 2026-09-21   **Where:** `CHANGELOG.md` (new), `pyproject.toml` (read only)

**`CHANGELOG.md` did not exist.** `pass-6.md` lists it as a pass 6 deliverable
and no earlier pass created it, so this is its first commit rather than an edit.

**The entry is `pass-6.md`'s exact string,** asserted rather than eyeballed:
`## [0.2.0] — Initial release.` is present as a whole line, it is the only `##`
heading in the file, and it carries no digits after the `]` — i.e. **no release
date.** The date is not known, and a wrong date in a changelog outlives the
mistake.

**Not a second copy of the README.** The file carries a three-line format note
and one pointer to the README's *Known limitations in V1* section. The anchor
`#known-limitations-in-v1` was derived from the actual heading text and checked,
not guessed. Both external links —
`keepachangelog.com/en/1.1.0/` and `semver.org/spec/v2.0.0.html` — were fetched
before being written into a shipped file.

**The version mismatch is deliberate and was left alone.** `pyproject.toml` says
`version = "0.1.1"`; the changelog entry says `[0.2.0]`. `0.1.1` is a published
placeholder held there so an accidental build-and-upload fails as a duplicate
rather than burning `0.2.0`, and a human bumps it at ship time. `CLAUDE.md`
§ "Hard don'ts" forbids the change. No reconciliation attempted.

**The classifiers were confirmed against the matrix, in both directions.**
Every classifier has a leg, and every leg's Python is classified:

| Classifier | Leg |
|---|---|
| 3.11 | `linux-min-py311` (ubuntu-24.04) — also the dependency floors |
| 3.12 | `macos-max-py312` (macos-latest) |
| 3.13 | `linux-max-py313-web` (ubuntu-24.04); `windows-max-py313` (windows-latest) |

All three are valid PyPI trove strings (checked against `pypi.org/classifiers/`
today), and `importlib.metadata` confirms all three survive into the metadata as
built, with `Requires-Python: >=3.11`. **No edit was needed.** Pass 0 authored
them under its step 5; the two-pass overlap logged at pass 0 resolved as
planned, with pass 6 verifying rather than authoring.

**Two things observed while confirming, neither changed** — both in
`notes/verified.md` in full:
- **`requires-python = ">=3.11"` has no ceiling.** Python 3.14 exists and is a
  recognised classifier, so pip will install Optica there, where no leg runs.
  The plan sets the target at 3.11–3.13 but specifies no upper bound, and adding
  one would hard-block 3.14 users — a release decision, not a pass 6 one.
- **`dist/` is stale.** `dist/optica-0.1.1.tar.gz` declares
  `Requires-Python: >=3.10` and carries no classifiers at all; it predates pass
  0's edits. Ship-time note: clear `dist/` before building 0.2.0, or
  `twine upload dist/*` will try to re-upload 0.1.0 and 0.1.1.

### Checkpoint 4 — the full suite, and the pass 6 boundary
**Pass:** 6   **Date:** 2026-09-21   **Where:** whole repo

**How it was run.** Background process writing to a log, as planned, then read
from the log's final counts line rather than from the exit code. It finished in
**80.8s**, so it would in fact have fitted inside the Bash tool's two-minute
foreground limit — the background run was the right call made on an estimate
that turned out conservative, and that is worth recording rather than
presenting the choice as necessary.

**The arithmetic, reconciled.**

```
collected, both runs                         2501

CI-style (.venv, -m "not slow")
    2413 passed + 12 skipped + 76 deselected = 2501   OK

full suite (.venv, no -m filter)
    2489 passed + 12 skipped +  0 deselected = 2501   OK
                                0 failed

slow tests that ran   = 2489 - 2413 =  76
slow tests deselected under -m "not slow" =  76   equal
```

So **all 76 slow tests passed; none skipped, none failed.** The skip count is
identical in both runs at 12, which means no slow test contributed a skip.

**The 12 skips, named** (`-rsf`), none of them slow:
- 5 x `tests/unit/test_tree.py` — the `_NO_LOGIC` package `__init__` files
  (`export/`, `input/`, `server/`, `training/`, `utils/`).
- 7 x deliberate stubs: `cli/test_classify.py:299` (pass 4);
  `cli/test_main.py:279`, `config/test_manager.py:389`,
  `utils/test_lockfile.py:204`, `utils/test_prompts.py:223`,
  `utils/test_system.py:190` and `:198` (pass 5).

**The 76 slow tests, by file:** `training/test_models.py` 31,
`training/test_engine.py` 10, `input/test_clip.py` 7,
`training/test_trainer.py` 6, `training/test_splits.py` 6,
`training/test_transforms.py` 5, `utils/test_mlstack.py` 3,
`training/test_data.py` 3, `export/test_pytorch.py` 3,
`training/test_checkpoints.py` 2.

---

## Pass 6 — boundary

**Milestone, as `pass-6.md` states it:** *"The workflow file parses as valid
YAML, README and CHANGELOG are complete, and the full test suite passes locally
including the slow tests."* **Met, all three.**
- `ci.yml` parses as valid YAML — 4 legs, 11 steps, `push` + `pull_request`.
- `README.md` complete: 14 sections, every checkable claim verified against the
  installed package and, for the `.gitignore` claim, against a real run.
- `CHANGELOG.md` complete: `pass-6.md`'s exact entry, no date.
- Full suite green locally including slow: 2489 passed, 12 skipped, 0 failed.

**Commits this pass**, in order:

| Commit | What |
|---|---|
| `f03930e` | `fix(logging)` — escape caller text so a bracketed extra survives Rich |
| `718135c` | `docs(build-log)` — the unescaped `console.print` sites, as fast-follow |
| `efe4dca` | `ci(workflow)` — the full version matrix, web and extras-free legs |
| `6d05eb7` | `docs(readme)` — rewritten for V1, verified against the shipped package |
| `133868a` | `feat(workspace)` — drop a `.gitignore` in the folders Optica creates |
| `a1fc3a6` | `docs(changelog)` — `CHANGELOG.md` with the 0.2.0 entry |

Two of them touch `src/`, both deliberate exceptions to `pass-6.md`'s *no
`src/` code*, each assigned per item: `f03930e` (checkpoint 0) and `133868a`
(checkpoint 2b).

**Ruff clean, mypy clean (121 source files), in `.venv`, `.smoke/ci-venv`,
`.smoke/min-venv` and `.smoke/web-venv`.** `version` in `pyproject.toml` is
untouched at `0.1.1`. Nothing was pushed.

### The standing list, restated in full at the pass 6 boundary

Everything below is implemented and tested and has **never run against the real
thing**. Pass 5 wrote it; this is it carried forward with pass 6's changes
marked.

1. **The whole browser surface.** `optica label`, `optica curate`,
   `optica.label()`, `optica.curate()`, and both browser stages of
   `optica run` / `optica.run()`. *(Pass 3 drove the server and both pages live;
   what has never run is a browser stage **inside the composite pipeline**.)*
   With it: the suppression of step-level resume prompts inside `run`, and the
   API's `Labeling complete` / `Curation complete` lines.
2. **The whole terminal prompt surface.** No prompt has ever been answered at a
   real terminal: R/C/S resumption, the **C** step selector, the discard
   confirmation, **S**, setup's environment prompts, the extras prompt, the
   variant prompt, the API-key prompt, the Review's `Proceed with installation?`,
   and both hardware safety prompts. Rich's rendering of those menus, and the
   default marker, are unverified.
3. **`optica run`'s resumption, executed.** No live run has ever *started from*
   a resume point.
4. **Interruption and its exit codes.** No live Ctrl+C inside a `run`-driven
   stage. 130 and 3 are asserted from raised exceptions and scripted answers.
5. **`optica setup`'s first-install path — all of it.** No `pip install` has run
   on any path: command construction, the two-command torch split, per-extra
   progress, the failure path, the incomplete message and its retry command,
   `--upgrade`, and the repair path.
6. **Setup's environment cases except case 1.** Never run: the mismatch hard
   error, the single-found confirmation, the more-than-one picker, creating a
   venv, the create-name collision, skip-into-system-Python, and **every conda
   path**.
7. **The no-GPU branch.** This machine has an RTX 4070 Ti: the
   `torch-gpu`-with-no-GPU safety prompt, CPU index resolution, and every CUDA
   index except `cu130` are unexercised.
8. **The MPS path.** Apple-silicon device selection, written and never run.
9. **The warning contract.** All sixteen `WarningCode` values and the
   `warnings.warn` emission are test-only.
10. **Tier 5.** `Classifier` has never been constructed outside a test.
11. **The Tier 3/4 functions individually.** `optica.fetch()`, `optica.train()`
    and `optica.export()` have run live only *inside* `optica.run()`;
    `optica.label()`/`optica.curate()` not at all.
12. **`discard_after` against a locked file**, and `--output`'s create prompt
    against a directory a real run had populated. *(Checkpoint 2b exported into
    a hand-made folder, but under `--yes`, so the prompt still has not fired.)*
13. **Every platform but Windows.** Every live run remains on Windows 11.
14. **From pass 2:** the **Flickr adapter** has never been exercised with a real
    key — no key, and one needs a Flickr Pro subscription.

**What pass 6 changed on this list.**
- **Advanced, not cleared — `optica setup --ci`.** Item 13 said it *"has never
  run on a runner, outside a venv — pass 6 adds it to the matrix, and that is
  the first time it will."* Pass 6 added it to all four legs and ran it locally
  in three venvs against a clean `HOME`, twice each (created, then already
  present), exit 0. It still has not run **on a runner**.
- **Advanced, not cleared — the 62 web tests.** From pass 3 to pass 6 they
  skipped on every runner. They now run in `.smoke/web-venv` locally (2396
  passed, with real Click present). They have still never run on Linux or macOS.
- **New item — the CI matrix itself has never run on a runner.** Four legs,
  verified only by local stand-ins (`.smoke/min-venv`, `.smoke/ci-venv`,
  `.smoke/web-venv`) plus a per-leg expansion of the YAML. `git push` is denied
  to the agent; `pass-6.md` § "Known limit" anticipates exactly this.
- **Nothing was removed.** Pass 6's two `src/` changes were both verified
  against real runs, but neither clears a standing-list item.

### Does the README agree with the standing list?

**Now, yes — after one correction made at this checkpoint.** They did not fully
agree when checkpoint 2 was committed.

The README's *Status* section is a deliberate **subset**: 6 of the 14 items,
chosen as the ones a user's own decisions depend on — prompts (2), Flickr (14),
MPS (8), setup's first install and its CPU-only branch (5, 7), resumption from a
real interruption (3, 4), and now platforms (13). No README statement is
contradicted by any item on the list; the rest are internal-facing (the warning
contract, Tier 5 construction, conda paths, `discard_after` against a locked
file) and belong in this log rather than in a user's first page.

**The gap that was found and closed.** Item 13 — *every live run has been on
Windows* — was missing from the README, and it stays true at ship time: CI
deliberately never installs PyTorch, so what runs on Ubuntu and macOS is the
test suite, not a training run. A reader of *Platform support* alone could
reasonably have concluded the pipeline had been run on Linux. A sixth Status
bullet now says so plainly. The three README verification scripts were re-run
after the edit: 0 failures.

**One thing the README says that is true at ship and not before.** *"CI runs on
Ubuntu, macOS and Windows"* describes the shipping configuration. The workflow
has never executed. That is the same gate the commented CI badge sits behind —
a human pushes, sees green, uncomments — so both become true together, and
neither is claimed before then.

### Protective-defaults conformance check — checkpoint 2a, sections A–G
**Pass:** none — a read-only audit between passes   **Date:** 2026-09-22
**Where:** `notes/verified.md` § *Protective-defaults conformance check —
2026-09-22*. **Nothing under `src/`, `tests/` or `spec/` was changed.**
**What ran:** checkpoint 1 enumerated 49 protective requirements from the plan,
read in place. Checkpoint 2a checked items 1–30 (sections A–G: secrets,
gitignore, the destructive-prompt taxonomy, the `dataset/` overwrite, user-owned
files, collision suffixing, atomicity and interruption).
**Method control:** l.289's folder-level `.gitignore` (built in pass 6, commit
`133868a`) was located from behaviour alone — `utils/workspace.py:54`
`create_ignored` and its 12 tests — before any other verdict was trusted.
**Found:**
- **One silent deviation.** Item 21, plan l.680: collisions suffix correctly on
  every path, but the *"count reported on completion so the renaming is never
  silent"* clause is honoured only by `--folder`/`--manifest` labeling
  (`cli/classify.py:1032`). `optica train --manifest` materialization drops
  `report.renamed`, and `renamed` appears nowhere in `api/simple.py`. No
  build-log entry decides this.
- **Two built differently, both decided.** Item 14 (`dataset/` overwrite removes
  at commit, not before writing) — decided at `notes/build-log.md:2119`, pass 3.
  Item 28 (only export-shaped `.partial` folders are removed) — decided at
  `notes/build-log.md:3335`, pass 4 item 11. Both verified in code and tests
  rather than taken from the log.
- **One untested clause.** Item 19: *user-provided images are never staged* rests
  on structure alone; no test would fail if a path began staging them.
- **One ambiguous.** Item 1: `.env` belongs in the user's `.gitignore` is a
  statement about a user's file, not an Optica behaviour.
- **25 of 30 BUILT AND TESTED**, each by a test that constructs its own
  condition. Test state: 2413 passed, 12 skipped, 76 deselected (`-m "not slow"`).
**Also noted, not changed:** `input/manager.py:338` `replace_destination` has no
production caller.
**Reversible?** Nothing to reverse — no code was touched. Checkpoint 2b (items
31–49, sections H–N) follows.

### Protective-defaults conformance check — checkpoint 2b, sections H–N
**Pass:** none — a read-only audit between passes   **Date:** 2026-09-22
**Where:** `notes/verified.md` § *Checkpoint 2b — sections H–N (items 31–49)*.
**Nothing under `src/`, `tests/` or `spec/` was changed.**
**What ran:** items 31–49 — deletion behind confirmation, path and filesystem
safety, config writes, the global lock, browser exposure, the exported
artifact, and the seven borderline items marked at checkpoint 1.
**Found:**
- **No item 31–49 is NOT BUILT, and none deviates silently.** 18 of 19 are
  BUILT AND TESTED; item 41 is BUILT DIFFERENTLY and decided.
- **Item 41 builds *more* browser security than the plan allows.** A `Host`
  check and an `HttpOnly`/`SameSite=Strict` per-port cookie sit on top of the
  two guards l.885 calls *"the whole of V1's browser-security surface"*.
  Decided at `notes/build-log.md:2017` (pass 3), mutation-checked there, and
  already carrying a human status line flagging it for plan ratification.
- **Four test gaps, no build gaps.** (1) Seven `@pytest.mark.skip` stubs still
  carry `stub - pass 4`/`stub - pass 5` reasons although both passes closed;
  two of them pin protective behaviour that is in fact built —
  `test_setup_takes_the_lock` and `test_yes_never_drives_optica_setup`.
  (2) Item 33's *K/A/D/S is suppressed inside `optica run`* clause is
  structurally true — `_run_body` routes through `api.run()` and never reaches
  `_train_body` — but no test asserts it, so a refactor could reinstate a
  prompt whose `D` branch deletes every prior checkpoint mid-pipeline.
  (3) Item 42's `weights_only=True` guarantee is tested only under
  `@pytest.mark.slow`, which CI never runs. (4) Item 49's flag-batching stub is
  unfilled; the behaviour was confirmed instead by a smoke run in `.smoke/`
  (`optica train --epochs 0 --batch-size 0` reports both violations).
- **`replace_destination` is confirmed dead and unsafe.** `git log -S` places
  it in `fadabd4` (pass 2) as the plan's literal remove-then-write form;
  `commit_dataset` superseded it in `508d8da` (pass 3). It has no production
  caller, is still in `input/manager.py`'s `__all__`, and still empties a
  destination with no completed replacement to put back. **Left in place**, per
  the instruction, and recorded so a later pass finds the note rather than the
  function.
**Test state:** `-m "not slow"` → 2413 passed, 12 skipped; `-m "slow"` → 76
passed (torch 2.14.0+cu130, timm 1.0.29 installed locally; CI runs neither).
**Whole check, both halves:** 49 requirements — 43 BUILT AND TESTED, 3 BUILT
DIFFERENTLY (all decided: items 14, 28, 41), 1 BUILT BUT UNTESTED (item 19),
1 AMBIGUOUS (item 1), and 1 partly NOT BUILT as a **silent deviation** (item
21, the collision-rename count on `train --manifest` and on every API path).
**Reversible?** Nothing to reverse — no code was touched.

### Item 21 of the protective-defaults check is decided: fast-follow
**Pass:** after 6   **Date:** 2026-09-22   **Where:** plan l.680; `cli/classify.py`, `api/simple.py`
**Found:** the protective-defaults check (`9d7eeb5`, `4e9d210`) left item 21 as
the one silent deviation of 49. l.680's collision-rename count is reported on
`--folder`/`--manifest` labeling but dropped on `optica train --manifest`
materialization and on every API path. The suffixing itself is correct
everywhere — no file is ever overwritten. What is missing is the notification
l.680 attaches to it: "so the renaming is never silent."
**Decided:** fast-follow, third in the post-release order, after item 33's test
and the removal of `replace_destination`. The CLI half is one line. The API half
needs a result field or a warning code, both permanent public surface, so it is
chosen deliberately after release rather than quickly before it.
**Why not before release:** no user file is harmed; the gap is a missing
message. The same audit found no protective behaviour unbuilt.
