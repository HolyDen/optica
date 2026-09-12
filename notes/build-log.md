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
