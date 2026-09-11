# Verified facts

Facts checked against the world during implementation. Not a specification —
`spec/optica-plan-v1-core.md` is. This file exists because facts held only in a
conversation do not survive compaction or a pass boundary.

**Every entry states the date and the command or URL that produced it.** An
entry with no source is not a verified fact, it is a memory, and memories are
what the September 2026 check found six errors in.

Format:

```
### <what was checked>
**Date:** YYYY-MM-DD
**How:** <exact command, or URL fetched>
**Result:** <what came back — the breakdown, not just the total>
**Consequence:** <what in the code depends on this>
```

---

## Pass 0 — open

### 0. The build machine

**Status:** not yet recorded.
GPU model, VRAM, driver version and CUDA version from `nvidia-smi`, and
`python --version`. The driver version decides whether the `cu130` index applies
or the `cu126` fallback does. Known in advance: this machine has an NVIDIA GPU,
so the CUDA device path is exercisable and the MPS path is not.

### 1. `download.pytorch.org` wheel metadata

**Status:** not yet checked.
Does the CUDA-index torchvision wheel declare the same exact `torch==<version>`
requirement as the PyPI wheel? The plan's pairing rule reads that declaration
locally via `importlib.metadata`. **If the CUDA-index wheels differ, stop and
ask — the rule needs a fallback and the plan changes.**

### 2. Torch stack download size

**Status:** not yet checked.
The ~3GB figure came from PyPI's dependency tree. Measure on
`download.pytorch.org`, and measure the CPU-only path separately. Record the
per-item breakdown.

### 3. Open Images V7 column schema

**Status:** not yet checked.
Do the V7 image CSVs still carry `OriginalURL` and `Thumbnail300KURL`? The fetch
path prefers `Thumbnail300KURL` and falls back to `OriginalURL`.

### 4. timm layer names and preprocessing values

**Status:** not yet checked.
Per backbone, against the pinned timm: Phase 2 unfreeze layer names from
`model.named_parameters()`, and exact `crop_pct` / `interpolation` from
`resolve_model_data_config()`.

---

## Verified
