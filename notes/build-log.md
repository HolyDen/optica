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
