# Pass 0 — Verification

**Attended pass. No implementation code.**

## Read
`spec/optica-plan-v1-core.md` § "Tech Stack" and § "Implementation Notes".

## Do
1. **Determine which `pyproject.toml` is in the repo root.** A placeholder and a
   prepared replacement both exist; which one is committed is not known. The
   prepared file carries `license-files = ["LICENSE"]`, `requires =
   ["hatchling>=1.27"]` and the SPDX form `license = "Apache-2.0"`. The
   placeholder carries `license = { text = "Apache-2.0" }`. Check the file
   against the plan's Tech Stack section — Core is exactly six packages, and
   `click` and `pydantic` must **not** appear, since they arrive transitively.
   Report which one is present before changing anything. Do not reconstruct the
   file from any other document.
2. Record the machine in `notes/verified.md`: GPU model, VRAM, driver and CUDA
   version from `nvidia-smi`, and `python --version`. The driver version decides
   whether the `cu130` index applies or the `cu126` fallback does.
   **Also confirm the interpreter you are actually using:** run
   `python -c "import sys; print(sys.executable)"` and check it points inside
   `.venv/Scripts`. Claude Code executes through Git Bash on Windows, and if the
   venv was activated in a different shell this can silently be the system
   Python. Stop and say so if it is.
3. The four verification tasks below. Every result goes to `notes/verified.md`
   with its date and the exact command or URL that produced it.
4. Extend the repo `.gitignore`. It already carries `dist/`, `.venv/`,
   `__pycache__/`, `*.egg-info/` and `.env` — do not duplicate those. Add:
   `dataset/`, `checkpoints/`, `optica-output/`, `.smoke/`,
   `.claude/settings.local.json`, `build/`, `*.py[cod]`, `.pytest_cache/`,
   `.mypy_cache/`, `.ruff_cache/`. The existing file ends without a trailing
   newline, so append a newline first or the first new entry will fuse onto
   `.env`.
5. Three `pyproject.toml` edits: sdist exclusions for `spec/` and `notes/`;
   `markers = ["slow: requires torch"]` under `[tool.pytest.ini_options]`; and
   the Python version classifiers for 3.11, 3.12 and 3.13.

## Stop and ask if
Task 1 finds the CUDA-index wheels do not declare the same exact
`torch==<version>` requirement as PyPI's. That breaks the derived pairing rule
and the plan has to change. Propose the change in `notes/build-log.md`; do not
apply it.

## Out of scope
Anything under `src/`. Any test.

## Done when
`notes/verified.md` holds four answered entries plus the machine record, and
`pyproject.toml` is in place.

---

## The four tasks

1. **`download.pytorch.org` wheel metadata.** The plan derives torch↔torchvision
   compatibility from torchvision's own declared `torch==<version>`
   requirement, read locally via `importlib.metadata` with no network call.
   That pin was verified against PyPI's wheels only. Check whether the
   CUDA-index wheels declare the same exact requirement. **If they do not, the
   derived pairing rule needs a fallback and the plan must change — stop and
   ask.**
2. **The torch stack download size.** The ~3GB figure was computed from PyPI's
   dependency tree; `download.pytorch.org` packages CUDA differently. Also
   measure the CPU-only path, which is unmeasurable from PyPI because on Linux
   PyPI's torch pulls the CUDA stack unconditionally. Print the per-item
   breakdown, not just the total.
3. **Open Images V7 column schema.** Confirm the V7 image CSVs still carry
   `OriginalURL` and `Thumbnail300KURL`. High confidence they do — documented
   with a worked example in the dataset's own earlier READMEs — but unconfirmed
   for V7. The fetch path depends on them: prefer `Thumbnail300KURL`, fall back
   to `OriginalURL`.
4. **timm layer names and preprocessing values.** Instantiate the four backbones
   against the pinned timm and read `model.named_parameters()` for the Phase 2
   unfreeze layers, plus exact `crop_pct` and `interpolation` per backbone from
   `resolve_model_data_config()`. Layer names change between timm releases, so
   this cannot be taken from anywhere else.
