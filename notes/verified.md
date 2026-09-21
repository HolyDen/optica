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

Nothing. All four tasks answered, plus the machine record and step 1.

---

## Verified

### 0. The build machine

**Date:** 2026-09-12
**How:**
```
nvidia-smi
python -c "import sys; print(sys.executable)"
python --version
```
**Result:**

| Item | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 4070 Ti |
| VRAM | 12282 MiB (~12 GB), 972 MiB in use at idle |
| Driver | 591.86 |
| Driver CUDA | 13.1 |
| Compute mode | Default, WDDM |
| Python | 3.11.9 |
| Interpreter | `C:\dev\optica\.venv\Scripts\python.exe` — confirmed inside `.venv/Scripts`, not the system Python |

**Consequence:** the CUDA device path is exercisable on this machine and the MPS
path is not (pass 4 must record MPS as written-but-never-run). Driver CUDA 13.1
selects the **`cu130`** index, not the `cu126` fallback — see the index
availability entry below for why `cu132` is not the answer despite existing.

### Which CUDA indexes exist on `download.pytorch.org`

**Date:** 2026-09-12
**How:** `curl -s -o /dev/null -w '%{http_code}' "https://download.pytorch.org/whl/<variant>/torch/"` for each variant
**Result:**

| Variant | HTTP | Present |
|---|---|---|
| `cpu` | 200 | yes |
| `cu126` | 200 | yes |
| `cu128` | 200 | yes |
| `cu129` | 200 | yes |
| `cu130` | 200 | yes |
| `cu131` | 403 | **no — never published** |
| `cu132` | 200 | yes |

**Consequence:** resolves the `cu<XXX>` placeholder in `EXTRAS_REGISTRY`'s
`torch-gpu.index_url` (plan § "Registry and resolution", flagged there as a
pre-implementation-gate item). **Use `cu130`.** `cu132` exists but requires a
13.2-capable driver and this machine reports 13.1, so it would resolve to wheels
the driver cannot run. `cu126` remains a valid older fallback. Note that
`cu131` does not exist at all — a driver reporting 13.1 must select `cu130`, so
any code mapping a driver version to an index name by string-building
`cu{major}{minor}` is wrong and would 403.

### Package versions — plan's September 2026 snapshot re-checked

**Date:** 2026-09-12
**How:** `python -m pip index versions <pkg>` (probe venv, PyPI) and the same with `--index-url https://download.pytorch.org/whl/cu130`
**Result:**

| Package | Plan's snapshot | Latest now (PyPI) | Latest on `cu130` | Still accurate? |
|---|---|---|---|---|
| `torch` | 2.14.0 | 2.14.0 | 2.14.0+cu130 | yes |
| `torchvision` | 0.29.0 | 0.29.0 | 0.29.0+cu130 | yes |
| `timm` | 1.0.29 | 1.0.29 | **absent from index** | yes (PyPI) |

**Consequence:** the plan's Tech Stack version table needs no correction, and
the `pyproject.toml` bounds derived from it stand. See the next entry for the
consequence of timm's absence from the CUDA index.

### `timm` and `scikit-learn` are not on the PyTorch index

**Date:** 2026-09-12
**How:**
```
python -m pip index versions timm --index-url https://download.pytorch.org/whl/cu130
python -m pip index versions scikit-learn --index-url https://download.pytorch.org/whl/cu130
```
**Result:** both return `ERROR: No matching distribution found for <pkg>`. Only
`torch` and `torchvision` (and torch's own CUDA dependencies) are served there.
**Consequence:** plan § "Package install split" has `optica setup` install four
packages — `torch`, `torchvision`, `timm`, `scikit-learn` — and
§ "Registry and resolution" says each variant's `index_url` "builds the pip
command per variant". A single command passing `--index-url <variant>` for all
four **fails**, because `--index-url` *replaces* PyPI rather than adding to it.
`optica setup` must either add `--extra-index-url https://pypi.org/simple` or
split the install into two commands. Pass 5 (`cli/setup.py`) owns the choice;
logged in `notes/build-log.md`.

### Step 1 — which `pyproject.toml` is in the repo root

**Date:** 2026-09-12
**How:** read `C:\dev\optica\pyproject.toml`; checked against
`spec/optica-plan-v1-core.md` § "Tech Stack" (dependency-taxonomy table,
package-install split, extras table, version-bound strategy)
**Result:** the **prepared replacement** is present, not the placeholder. All
three of its markers are in the file and the placeholder's marker is absent:

| Marker | Expected in prepared file | Found |
|---|---|---|
| `requires` | `["hatchling>=1.27"]` | yes, line 2 |
| `license` | SPDX string `"Apache-2.0"` | yes, line 11 |
| `license-files` | `["LICENSE"]` | yes, line 12 |
| `license = { text = ... }` | placeholder only — must be absent | absent |

Conformance to the plan's Core rule — **6 packages, `click` and `pydantic`
absent**:

| Plan's Core member | Declared in `[project.dependencies]` |
|---|---|
| `typer` | `typer>=0.27,<1.0` |
| `rich` | `rich>=15.0,<16.0` |
| `python-dotenv` | `python-dotenv>=1.2,<2.0` |
| `pydantic-settings` | `pydantic-settings>=2.15,<3.0` |
| `httpx` | `httpx>=0.28,<1.0` |
| `Pillow` | `pillow>=12.3,<13.0` |
| `click` | **absent — correct**, arrives via typer |
| `pydantic` | **absent — correct**, arrives via pydantic-settings |

Extras match the plan's table exactly: `web` = fastapi + uvicorn, `clip` =
open-clip-torch, `all` = `optica[web,clip]`, `test` = pytest + ruff + mypy.
Tier 3 (`torch`, `torchvision`, `timm`, `scikit-learn`) is declared nowhere,
per plan § "Version-bound strategy" ("torch is never a direct dependency in
`pyproject.toml` in V1"). Pre-1.0 ceilings are `<1.0` for typer, httpx and
fastapi as the bound rule requires. `version = "0.1.1"` — left untouched.
**Consequence:** no file replacement needed; pass 0 step 5's three edits apply
to this file as it stands.

### 1. `download.pytorch.org` wheel metadata — the pairing-rule gate

**Date:** 2026-09-12
**How:**
```
python -m pip download torchvision==0.29.0 --no-deps -d tv_pypi
python -m pip download torchvision==0.29.0 --no-deps -d tv_cu130 \
    --index-url https://download.pytorch.org/whl/cu130
# then read <wheel>/*.dist-info/METADATA out of each .whl with zipfile
```
**Result:** **the two indexes declare the identical exact pin.** The gate does
not fire.

| Index | Wheel filename | Wheel `Version:` | Declared torch requirement |
|---|---|---|---|
| PyPI | `torchvision-0.29.0-cp311-cp311-win_amd64.whl` (1,376,792 B) | `0.29.0` | `torch (==2.14.0)` |
| `cu130` | `torchvision-0.29.0+cu130-cp311-cp311-win_amd64.whl` (6,406,123 B) | `0.29.0+cu130` | `torch (==2.14.0)` |

Full `Requires-Dist` on both: `numpy`, `torch (==2.14.0)`,
`pillow (!=8.3.*,>=5.3.0)`, `gdown (>=4.7.3) ; extra == 'gdown'`,
`scipy ; extra == 'scipy'`.

The CUDA wheel pins the **public** version `2.14.0`, not `2.14.0+cu130` — which
is precisely what plan § "Tech Stack" predicts: "Under PEP 440 a public-version
specifier ignores local labels, so `torch==2.14.0` is satisfied by a CUDA-index
`2.14.0+cu130` and the check behaves identically on the CPU and CUDA paths."
**Consequence:** the derived torch↔torchvision pairing rule needs **no fallback
and the plan does not change.** `training/` may read the pin locally through
`importlib.metadata` with no network call, on both the CPU and CUDA paths.
One parsing caveat: the `cu130` wheel's `METADATA` uses CRLF line endings, so
hand-rolled line splitting yields a trailing `\r` on each value
(`'torch (==2.14.0)\r'`). `importlib.metadata` parses the file as RFC 822
headers and normalises this; **do not hand-roll the parse.**

### 2. Torch stack download size

**Date:** 2026-09-12
**How:** `C:\Users\DEN\.claude\jobs\6084e881\tmp\measure2.py`, run by
`C:/dev/optica-probe/Scripts/python.exe` (Python 3.11.9). Method: read each
index's PEP 691/658 listing, pick the best cp311 wheel per platform by **exact**
tag predicate, take each wheel's size from a ranged `GET`
(`Range: bytes=0-0`, total read from `Content-Range` — `download.pytorch.org`
**403s on HEAD**), then walk `Requires-Dist` from the `.metadata` sidecar (or
from the remote wheel's zip central directory over byte ranges where no sidecar
is served, as for `nvidia-cudnn-cu13`), evaluating markers against a synthetic
target environment. Packages measured: the four `optica setup` installs —
`torch`, `torchvision`, `timm`, `scikit-learn` — plus their full transitive
closure.
**Cross-check:** for Windows + PyPI-default this method returns **34 packages /
200.4 MiB**; `pip install --dry-run --report` independently resolved the same
case to **34 packages / 200.4 MiB**. Two independent resolvers agreeing to
0.1 MiB is the reason this entry is trusted and the earlier one was not.

**Result — totals:**

| Platform | Index | Packages | Total | GB (decimal) |
|---|---|---|---|---|
| Linux x86_64 | `cu130` | 42 | 2,287.9 MiB | 2.40 |
| Linux x86_64 | `cpu` | 33 | **274.3 MiB** | **0.29** |
| Linux x86_64 | PyPI default | 42 | 2,289.0 MiB | 2.40 |
| Windows AMD64 | `cu130` | 34 | 1,985.3 MiB | 2.08 |
| Windows AMD64 | `cpu` | 34 | 200.3 MiB | 0.21 |
| Windows AMD64 | PyPI default | 34 | 200.4 MiB | 0.21 |

Row sizes below are rounded to 0.1 MiB while every total is summed from exact
byte counts, so a column of displayed rows can differ from its total by a
tenth or two. The "remaining N packages" figures are exact and make each
breakdown reconcile to its total in both count and bytes.

**Per-item breakdown — Linux x86_64 / `cu130`** — the 18 largest; the remaining
**24** packages total **5.5 MiB** (5,731,988 B), for 42 in all:

| Package | Version | Size |
|---|---|---|
| `torch` | 2.14.0+cu130 | 528.9 MiB |
| `nvidia-cudnn-cu13` | 9.24.0.43 | 527.5 MiB |
| `nvidia-cublas` | 13.7.0.27 | 420.1 MiB |
| `triton` | 3.8.0 | 235.4 MiB |
| `nvidia-nccl-cu13` | 2.30.7 | 206.0 MiB |
| `nvidia-cusparselt-cu13` | 0.8.1 | 162.3 MiB |
| `nvidia-nvshmem-cu13` | 3.4.5 | 57.6 MiB |
| `nvidia-cuda-nvrtc` | 13.4.59 | 50.8 MiB |
| `scipy` | 1.17.1 | 33.7 MiB |
| `numpy` | 2.4.6 | 16.1 MiB |
| `scikit-learn` | 1.9.1 | 8.9 MiB |
| `torchvision` | 0.29.0+cu130 | 7.1 MiB |
| `cuda-bindings` | 13.4.1 | 6.8 MiB |
| `pillow` | 12.3.0 | 6.6 MiB |
| `sympy` | 1.14.0 | 6.0 MiB |
| `hf-xet` | 1.6.0 | 4.3 MiB |
| `timm` | 1.0.29 | 2.5 MiB |
| `networkx` | 3.6.1 | 2.0 MiB |

The eight torch/CUDA rows alone are **2,188.5 MiB — 95.7% of the total.**

**Per-item breakdown — Linux x86_64 / `cpu`** (the path that cannot be measured
from PyPI at all):

| Package | Version | Size |
|---|---|---|
| `torch` | 2.14.0+cpu | 187.1 MiB |
| `scipy` | 1.17.1 | 33.7 MiB |
| `numpy` | 2.4.6 | 16.1 MiB |
| `scikit-learn` | 1.9.1 | 8.9 MiB |
| `pillow` | 12.3.0 | 6.6 MiB |
| `sympy` | 1.14.0 | 6.0 MiB |
| `hf-xet` | 1.6.0 | 4.3 MiB |
| `timm` | 1.0.29 | 2.5 MiB |
| `networkx` | 3.6.1 | 2.0 MiB |
| `torchvision` | 0.29.0+cpu | 1.6 MiB |
| 23 others | — | 5.5 MiB |

**Zero `nvidia-*` packages, and no `triton`** — `triton` is Linux-and-CUDA only
and is itself 235.4 MiB.

**Per-item breakdown — Windows AMD64 / `cu130`** — the 10 largest; the remaining
**24** packages total **4.7 MiB** (4,878,533 B), for 34 in all. `torch` is a
**single wheel with CUDA bundled inside it** and there are **no `nvidia-*`
packages at all**, which is the whole difference from the Linux table above:

| Package | Version | Size |
|---|---|---|
| `torch` | 2.14.0+cu130 | 1,898.4 MiB |
| `scipy` | 1.17.1 | 34.9 MiB |
| `numpy` | 2.4.6 | 12.0 MiB |
| `scikit-learn` | 1.9.1 | 7.9 MiB |
| `pillow` | 12.3.0 | 6.9 MiB |
| `torchvision` | 0.29.0+cu130 | 6.1 MiB |
| `sympy` | 1.14.0 | 6.0 MiB |
| `hf-xet` | 1.6.0 | 3.8 MiB |
| `timm` | 1.0.29 | 2.5 MiB |
| `networkx` | 3.6.1 | 2.0 MiB |
| 24 others | — | 4.7 MiB |

That one `torch` row is **1,898.4 MiB — 95.6% of the total**, and it is the only
torch/CUDA row there is.

**Consequences.**

1. **The "~3GB" figure is not the plan's.** It comes from
   `notes/passes/pass-0.md` line 63, which framed task 2 as checking a figure
   "computed from PyPI's dependency tree". Searched 2026-09-13 across all 1781
   lines of `spec/optica-plan-v1-core.md` for every `GB`, `MB`, `GiB`,
   `gigabyte` and `disk` token: **the plan contains no ~3GB figure in any
   spelling or unit.** Its `torch-gpu` estimate was `~2GB`, which this
   measurement finds slightly *low* — the opposite direction. Corrected
   2026-09-13 by the human between passes 1 and 2; the measurement itself
   (2.40 GB Linux, 2.08 GB Windows) is unchanged and stands.
2. **On Linux, the CUDA index and PyPI are the same size** — 2,287.9 vs
   2,289.0 MiB, a 1.1 MiB difference. This **confirms** plan § "Tech Stack":
   PyPI's Linux `torch` pulls the CUDA stack unconditionally. The interesting
   difference is not CUDA-index vs PyPI, it is **Linux vs Windows packaging**:
   Linux ships CUDA as six separate `nvidia-*` wheels plus `triton`, Windows
   bundles it inside one 1.9 GB `torch` wheel.
3. **The CPU-only path is 0.29 GB on Linux and 0.21 GB on Windows** — an 8.3×
   and 9.9× reduction. This is the number task 2 existed to obtain, and it is
   unobtainable from PyPI on Linux for the reason in (2).
4. **`EXTRAS_REGISTRY` `size_estimate` values need revising** (plan
   § "Registry and resolution"; they feed the review step's download total):

   | Entry | Declared | Measured | Verdict |
   |---|---|---|---|
   | `torch-cpu` | `~1GB` | 0.21–0.29 GB | **3–5× overestimate** |
   | `torch-gpu` | `~2GB` | 2.08–2.40 GB | close; slightly low |
   | `torch-auto` | `~1–2GB` | 2.08–2.40 GB | top of range too low |

   `torch-cpu`'s `~1GB` is the one worth fixing — it overstates by enough to
   push a user toward a GPU install they may not want. Logged for pass 5.

### 3. Open Images V7 column schema

**Date:** 2026-09-12
**How:**
```
curl -s https://storage.googleapis.com/openimages/web/download_v7.html
curl -s -r 0-700 <each image-metadata CSV>          # header row only
curl -s -r 0-8000000 <train CSV>                    # 8 MB sample, 21,856 rows
curl -sI <each CSV>                                 # Content-Length
```
**Result — the columns are present.** Both `OriginalURL` (col 3) and
`Thumbnail300KURL` (col 11) survive in V7. The header is identical across every
image-metadata CSV:

```
ImageID,Subset,OriginalURL,OriginalLandingURL,License,AuthorProfileURL,
Author,Title,OriginalSize,OriginalMD5,Thumbnail300KURL,Rotation
```

**Why this is a V7 answer and not a v6 one — the link, written down.** V7 does
not republish image metadata under a `v7/` path. `download_v7.html` (the page
whose own banner reads "You are viewing the description of the latest version
of Open Images (V7 - released Oct 2022)") serves the `2018_04` files *as* its
Image IDs. Verbatim from that page's "Annotations and metadata" table, the
`Image IDs` row:

```html
Image IDs</div>
  <div class="col-4"><a download
    href="https://storage.googleapis.com/openimages/2018_04/train/train-images-boxable-with-rotation.csv"
    ><button class="button">Train</button></a></div>
  <div class="col-4"><a download
    href="https://storage.googleapis.com/openimages/2018_04/validation/validation-images-with-rotation.csv"
    ><button class="button">Validation</button></a></div>
  <div class="col-4"><a download
    href="https://storage.googleapis.com/openimages/2018_04/test/test-images-with-rotation.csv"
    ><button class="button">Test</button></a></div>
```

Independently, the same page's § "Data formats" → *Image information* documents
the 12-column header inline, in V7's own words — "It has image URLs, their
OpenImages IDs, the rotation information, titles, authors, and license
information" — followed by the header line and a worked example row
(`000060e3121c7305,train,https://c1.staticflickr.com/5/4129/...`). So the schema
is confirmed twice over on the V7 page: by the files V7 links to, and by V7's
own documentation of their format.

Files measured, per item:

| File | Size | Header carries both columns |
|---|---|---|
| `2018_04/train/train-images-boxable-with-rotation.csv` (V7 "Train") | 608.8 MiB | yes |
| `2018_04/validation/validation-images-with-rotation.csv` (V7 "Validation") | 14.5 MiB | yes |
| `2018_04/test/test-images-with-rotation.csv` (V7 "Test") | 43.1 MiB | yes |
| `v6/oidv6-train-images-with-labels-with-rotation.csv` (linked in the image-labels row) | 2,560.3 MiB (2,684,720,962 B) | yes |
| `v7/oidv7-class-descriptions.csv` | 501,178 B | n/a — label mapping |
| `v7/oidv7-class-descriptions-boxable.csv` | 12,064 B | n/a — label mapping |

**Population rates, sampled from 21,856 rows of the V6-named train CSV:**

| Column | Populated | Empty | Empty % |
|---|---|---|---|
| `OriginalURL` | 21,856 | 0 | 0.00% |
| `Thumbnail300KURL` | 21,317 | **539** | **2.47%** |
| both empty | — | 0 | 0.00% |

**Consequence — and one correction the fetch path needs.** Plan § "Fetch
sources" reads: "Per image, `Thumbnail300KURL` is preferred, with `OriginalURL`
as the fallback **where that column is absent**." The column is never absent —
it is in all 12 headers, on every file. What varies is the **value**, empty on
2.47% of rows. A fallback conditioned on the column being absent would never
fire, and roughly one image in forty would be fetched from an empty URL. The
condition must be **per-row on an empty value**. `OriginalURL` is a sound
fallback target: 100% populated, and zero rows have both empty. Proposed plan
wording change is in `notes/build-log.md`; pass 2 owns `input/fetch.py`.
Second consequence: the plan's "~100KB label-mapping file" figure matches
neither measured candidate (501,178 B full, 12,064 B boxable), and per-class
*image URL* lookup needs a 608.8 MiB or 2,560.3 MiB CSV rather than anything
~100KB. Also logged for pass 2.

### 4. timm layer names and preprocessing values

**Date:** 2026-09-12
**Which interpreter produced these values — this matters, read it:**

| | |
|---|---|
| Interpreter | `C:\dev\optica-probe\Scripts\python.exe` |
| Python | 3.11.9 (same 3.11 as `.venv`, created from it with `-m venv`) |
| `torch` | **2.14.0+cpu** (CPU-only build, `--index-url https://download.pytorch.org/whl/cpu`) |
| `torchvision` | 0.29.0+cpu |
| `timm` | **1.0.29** (the pinned version, `pip install "timm==1.0.29"`) |
| `torch.cuda.is_available()` | `False` — CPU build, as intended |

**These values did NOT come from `C:\dev\optica\.venv`.** That venv was
deliberately left without torch, torchvision, timm or scikit-learn, and was
re-checked after the probe install to confirm it: `pip list` in `.venv` matches
none of them. Pass 1's milestone — `pip install -e .` then `optica --version`
with no torch present — is therefore still a real check rather than a vacuous
one. `C:/dev/optica-probe` is throwaway and belongs to no pass; delete it freely.

**How:** `C:\Users\DEN\.claude\jobs\6084e881\tmp\task4.py` —
`timm.create_model(<name>, pretrained=False, num_classes=3)`, then
`timm.data.resolve_model_data_config(model)` and `model.named_parameters()`.
**`pretrained=False` throughout: `pretrained_cfg` is still fully populated, so
every value below is the real one and no weights were downloaded.**

**Result — the six preprocessing values, per backbone:**

| timm name | default tag | `input_size` | `interpolation` | `crop_pct` | `crop_mode` |
|---|---|---|---|---|---|
| `efficientnet_b0` | `ra_in1k` | `(3, 224, 224)` | `bicubic` | **0.875** | `center` |
| `efficientnet_b4` | `ra2_in1k` | `(3, 320, 320)` | `bicubic` | **0.875** | `center` |
| `resnet50` | `a1_in1k` | `(3, 224, 224)` | `bicubic` | **0.95** | `center` |
| `mobilenetv3_large_100` | `ra_in1k` | `(3, 224, 224)` | `bicubic` | **0.875** | `center` |

`mean` and `std` are identical on all four — `mean=(0.485, 0.456, 0.406)`,
`std=(0.229, 0.224, 0.225)` (standard ImageNet). So of the six values, only
`input_size` and `crop_pct` actually vary between backbones.

**Result — Phase 2 unfreeze layer names. Every name the plan gives exists in
timm 1.0.29; there were no misses.**

| timm name | Plan's group | Real parameter prefix | Tensors | Params |
|---|---|---|---|---|
| `efficientnet_b0` | `blocks[5]` | `blocks.5.` | 52 | 2,026,348 |
| | `blocks[6]` | `blocks.6.` | 13 | 717,232 |
| | `conv_head` | `conv_head.` | 1 | 409,600 |
| | head | `classifier.weight`, `classifier.bias` | 2 | 3,843 |
| `efficientnet_b4` | `blocks[5]` | `blocks.5.` | 104 | 8,636,228 |
| | `blocks[6]` | `blocks.6.` | 26 | 4,470,004 |
| | `conv_head` | `conv_head.` | 1 | 802,816 |
| | head | `classifier.weight`, `classifier.bias` | 2 | 5,379 |
| `resnet50` | `layer4` | `layer4.` | 30 | 14,964,736 |
| | head | `fc.weight`, `fc.bias` | 2 | 6,147 |
| `mobilenetv3_large_100` | see caveat below | `blocks.4.` | 26 | 600,544 |
| | | `blocks.5.` | 39 | 2,023,944 |
| | | `blocks.6.` | 3 | 155,520 |
| | head | `classifier.weight`, `classifier.bias` | 2 | 3,843 |

Total parameters: `efficientnet_b0` 4,011,391; `efficientnet_b4` 17,553,995;
`resnet50` 23,514,179; `mobilenetv3_large_100` 4,205,875. Head-name split is
real and must be handled: **efficientnet and mobilenet use `classifier.`,
resnet50 uses `fc.`**

Top-level module order, for reference when freezing by prefix:

```
efficientnet_b0/b4    : conv_stem, bn1, blocks, conv_head, bn2, global_pool, classifier
resnet50              : conv1, bn1, act1, maxpool, layer1..layer4, global_pool, fc
mobilenetv3_large_100 : conv_stem, bn1, blocks, global_pool, conv_head, norm_head, act2, flatten, classifier
```

**`efficientnet_b4`'s two resolutions, confirmed exactly as the plan describes:**
`input_size=(3,320,320)`, `test_input_size=(3,384,384)`, `crop_pct=0.875`,
`test_crop_pct=1.0`, tag `ra2_in1k`. `resolve_model_data_config()` returns the
**training** values (320 / 0.875), which is what plan § "Training" says V1 uses
throughout; `test_input_size` 384 and `test_crop_pct` 1.0 are deliberately
unused in V1.

**Consequences, and two things pass 4 must decide.**

1. **`crop_pct` genuinely differs — `resnet50` is 0.95, the other three 0.875.**
   This confirms the plan's insistence that the six values are "resolved per
   model rather than shared across the four backbones". The plan's
   `model_info.json` example showing `crop_pct: 0.875` is for
   `efficientnet-small` and is correct for that backbone only. **Do not
   hardcode 0.875.**
2. **`mobilenetv3_large_100`'s "Last 3 InvertedResidual blocks" is ambiguous,
   and the two readings differ.** Stage types in timm 1.0.29:

   | | `blocks[0]` | `[1]` | `[2]` | `[3]` | `[4]` | `[5]` | `[6]` |
   |---|---|---|---|---|---|---|---|
   | `mobilenetv3_large_100` | DepthwiseSeparableConv | InvRes | InvRes | InvRes | InvRes | InvRes | **ConvBnAct** |
   | `efficientnet_b0` | DepthwiseSeparableConv | InvRes | InvRes | InvRes | InvRes | InvRes | **InvRes** |

   `blocks[6]` of mobilenetv3 is a **`ConvBnAct`, not an `InvertedResidual`**.
   So "last 3 InvertedResidual blocks" taken **literally** means
   `blocks[3], blocks[4], blocks[5]` (2,755,312 params), while taken
   **positionally** — last 3 stages — it means `blocks[4], blocks[5], blocks[6]`
   (2,780,008 params). Pass 4 must pick one. Logged in `notes/build-log.md`.
   Note that the same sentence is unambiguous for the efficientnets, whose
   `blocks[6]` *is* an InvertedResidual, so the plan's `blocks[5], blocks[6]`
   for `efficientnet_b0` is consistent and needs no decision.
3. **`bn2` is unlisted for the efficientnets.** Both have `bn2` immediately
   after `conv_head` (2,560 params on b0, 3,584 on b4). The plan's group is
   "`blocks[5]`, `blocks[6]` + `conv_head`" and does not mention it, so a
   literal implementation unfreezes a convolution while leaving its own
   BatchNorm frozen. Flagged for pass 4; also logged.
4. **Head-name divergence** (`classifier.` vs `fc.`) means `models.py`'s
   `replace_head()` / `configure_head()` cannot assume one attribute name.
   timm's `model.reset_classifier(num_classes)` or `get_classifier()` is the
   portable route.

### Task 2 — first attempt rejected (recorded so the defects are not repeated)

**Date:** 2026-09-12
**How:** `pip install --dry-run --report` per platform/index, then an
`urllib` **HEAD** request per resolved wheel URL for `Content-Length`.
**Result: invalid, discarded.** Two independent defects, both of which the
per-item breakdown exposed and a total alone would have hidden:

1. **`download.pytorch.org` returns `403 Forbidden` to HEAD.** `torch` and
   `torchvision` therefore recorded as `0.0 MiB` — the largest item in the tree
   scoring zero. The reported totals (78.6 MiB Linux / 80.8 MiB Windows on both
   the `cu130` and `cpu` indexes) are missing torch entirely, which is also why
   `cu130` and `cpu` came out byte-identical. Fix: ranged `GET` with
   `Range: bytes=0-0` and read `Content-Range`, not HEAD.
2. **`pip --platform` does not override environment markers.** Marker
   evaluation (`sys_platform`, `platform_system`) comes from the *running*
   interpreter, so the "linux" rows were resolved with Windows markers and never
   pulled the `nvidia-*` packages — exactly the CUDA stack that plan § task 2
   says PyPI's Linux torch drags in unconditionally. Both platforms resolving to
   the same 34 packages was the tell. Fix: resolve with a tool that supports
   real cross-platform markers (`uv pip compile --python-platform`), or evaluate
   markers manually against a Linux environment.

**Consequence:** this is the "print the breakdown, not the total" rule from
`CLAUDE.md` paying for itself a second time. The 78.6 MiB figure was plausible,
in range, and wrong. Kept here so a later pass does not re-derive it with HEAD.

---

## Pass 1

### Click's restriction of variable-length `nargs` to positional arguments

**Date:** 2026-09-12
**How:** Typer 0.27.2 (which vendors Click — see the next entry), in `.venv`.
Behavioural probe through `typer.testing.CliRunner` against a two-command app
with `classes: list[str] = typer.Option(None, "--classes", "-c")`, plus
`inspect.signature(typer.Option)`:

```
python -c "import inspect, typer; print('nargs' in inspect.signature(typer.Option).parameters)"
```

**Result: the plan's claim holds exactly, error text included.**

| Invocation | Exit | Parsed / message |
|---|---|---|
| `go --classes cat` | 0 | `['cat']` |
| `go --classes cat dog` | **2** | **`Got unexpected extra argument(s) (dog)`** |
| `go -c cat -c dog` | 0 | `['cat', 'dog']` |
| `go -c cat -c dog,bird` | 0 | `['cat', 'dog,bird']` |
| `go --classes cat,dog` | 0 | `['cat,dog']` |
| `go --classes` (no value) | 2 | `Option '--classes' requires an argument.` |

Two supporting facts, both stronger than the plan states:

- **`typer.Option()` has no `nargs` parameter at all** in 0.27.2 — variable-length
  nargs is not merely restricted for options, it is not expressible for one
  through Typer's public API. (`typer.Option(..., nargs=-1)` raises
  `TypeError: Option() got an unexpected keyword argument 'nargs'`.)
- Typer's vendored Click defines no `Option` class of its own; Typer's
  `TyperOption` subclasses `_click.Parameter` directly.

**Consequence:** the comma value-separator convention (plan § "CLI Layer &
Conventions" → *Value separator — comma, everywhere*) is sound as specified, and
the space-separated alternative it rejects is genuinely unimplementable rather
than merely undesirable. Note rows 4 and 5: **Click does not split on commas** —
`-c cat -c dog,bird` arrives as `['cat', 'dog,bird']`, so splitting, trimming and
the `-c cat -c dog,bird` to three-classes composition are Optica's own work in
the flag layer, not behaviour inherited from the parser. This closes the
pre-implementation-gate item handed to pass 1 by `notes/build-log.md` § "The
plan's pre-implementation gate is broader than pass 0's four tasks".

### Typer 0.27.2 vendors Click; `click` is **not** a transitive dependency

**Date:** 2026-09-12
**How:**
```
.venv/Scripts/python.exe -m pip install -e ".[test]"
.venv/Scripts/python.exe -c "import click"
.venv/Scripts/python.exe -c "import importlib.metadata as md; print(md.distribution('typer').requires)"
```
**Result:** after a clean `pip install -e ".[test]"` into an empty 3.11.9 venv,
**`import click` raises `ModuleNotFoundError`.** `typer` 0.27.2 declares exactly
four runtime requirements and Click is not among them:

```
shellingham>=1.3.0 ; rich>=13.8.0 ; annotated-doc>=0.0.2 ; colorama (Windows only)
```

Click is instead **vendored** inside the wheel as the private package
`typer._click` (`typer/_click/{core,exceptions,parser,types,...}.py`, with its
own `LICENSE.txt`). It carries no `__version__`. The exception tree is reachable
publicly only through `typer.TyperException`, which the vendored
`ClickException` subclasses:

```
typer._click.exceptions.UsageError < ClickException < typer.TyperException < Exception
typer.BadParameter is typer._click.exceptions.BadParameter   (public re-export)
typer.Abort       is typer.exceptions.Abort < RuntimeError   (NOT a UsageError)
```

`typer` publicly re-exports `Abort`, `BadParameter`, `Exit`, `Context`,
`confirm`, `prompt`, `echo` — but **not** `UsageError`, `MissingParameter`,
`BadOptionUsage` or `NoSuchOption`.

**Consequence:** two.

1. `CLAUDE.md` § "Settled points" says `click` "arrive[s] transitively through
   `typer`". **That premise is false for typer 0.27.2.** The conclusion it
   supports — *do not add `click` to the dependency list* — nonetheless still
   holds, and more strongly: adding real Click would install a **second,
   unrelated** `UsageError` class, and Typer would keep raising the vendored one,
   so every `except click.UsageError` would silently stop firing. Core stays at
   six packages. See `notes/build-log.md` for the assumption this forced.
2. The plan writes the handler's contract as `click.UsageError`. There is no
   importable `click` in a Core install, so the class must come from
   `typer._click.exceptions`. Pinned by a test that raises a real parser error
   through the app and asserts it is caught, so a Typer bump that moves the
   module fails loudly rather than letting tracebacks through.

### `typer.Typer` has no `exception_handler()` method

**Date:** 2026-09-12
**How:** `python -c "import typer; print([n for n in dir(typer.Typer) if not n.startswith('_')])"`
**Result:** `['add_typer', 'callback', 'command']` — three methods, and
`exception_handler` is not one of them. Checked against typer 0.27.2, the version
pass 0 verified and `pyproject.toml` resolves to. Nor is it a removal: Typer has
never shipped the method; `app.exception_handler()` is FastAPI's API, not
Typer's.

`typer.Typer.__call__` forwards `*args, **kwargs` to the Click group object
returned by `typer.main.get_command(self)`, so `app(standalone_mode=False)`
reaches Click's `BaseCommand.main(standalone_mode=False)` and exceptions
propagate to the caller instead of being printed and `sys.exit`-ed by Click.

**Consequence:** the plan names a mechanism that does not exist (plan
§ "Error handling and prompt conventions", and Implementation Note 1). The
**behaviour** it specifies is fully implementable and is implemented in full;
only the spelling changes. See `notes/build-log.md` § "The global exception
handler's mechanism" for what was built instead, and for why the
`[project.scripts]` entry point still reads `optica.cli.main:app` as the plan
requires.

### Which exception each parser-error shape actually raises

**Date:** 2026-09-12
**How:** `typer.main.get_command(app).main(args=..., standalone_mode=False)` per
shape, printing `type(e).__mro__` and `e.exit_code`.
**Result:**

| Invocation shape | Exception | `exit_code` |
|---|---|---|
| `--classes` with no value (trailing) | `BadOptionUsage` | 2 |
| `--classes cat dog` (space-separated) | `UsageError` | 2 |
| `--nope` (unknown option) | `NoSuchOption` | 2 |
| `--epochs ten` (non-integer for an int flag) | `BadParameter` | 2 |
| required option absent entirely | `MissingParameter` | 2 |
| unknown subcommand | `UsageError` | 2 |

All six are `UsageError` subclasses or `UsageError` itself, so catching at the
base covers every one — the plan's stated reason for catching at the base,
confirmed. `UsageError.exit_code` is `2`; plain `ClickException.exit_code` is
`1`. `typer.Abort` is a `RuntimeError` and is **not** in this tree, exactly as
the plan requires for its separate `130` handling.

**One plan imprecision, non-blocking:** the plan writes "redirecting to prompts
where applicable (**`MissingParameter`** on `--classes`)". The class raised by
`--classes` **with no value** is `BadOptionUsage`, not `MissingParameter`;
`MissingParameter` is what fires when a *required* parameter is absent entirely.
Both are `UsageError` subclasses, so the base catch reaches both and the
specified behaviour is unaffected — the handler routes on both shapes.

### Non-ASCII status glyphs crash on a non-UTF-8 Windows **stdout**

**Date:** 2026-09-12
**How:** on the build machine (console codepage **cp1255**), under `.venv`:
```
python -c "import sys; print(sys.stdout.errors, sys.stderr.errors)"
python -c "from rich.console import Console; Console().print(chr(0x2713) + ' Done')"
```
**Result:** `sys.stdout.errors` is **`surrogateescape`** and `sys.stderr.errors`
is **`backslashreplace`**. Writing U+2713 to **stdout** raises
`UnicodeEncodeError: 'charmap' codec can't encode character` — **through Rich as
well as through `print()`**, since Rich writes to the same stream. The same write
to **stderr** does not raise; it degrades to a literal escape.

The plan's user-facing marker set is four glyphs: U+2715 (12 uses), U+2713 (8),
U+2717 (6), U+26A0 (4). The box-drawing characters counted alongside them belong
to the plan's own diagrams, not to Optica's output.

**Consequence:** an unhandled `UnicodeEncodeError` on a status line is precisely
the "raw traceback reaching the user" that plan § "Coding Style" forbids, and it
fires on a default Windows console for output the user did nothing unusual to
request. `utils/logging.py` therefore resolves the marker set once against the
target stream's encoding and falls back to ASCII when the glyph cannot be
encoded. Logged as an assumption in `notes/build-log.md`; the fallback mapping is
recorded there.

### Installed toolchain snapshot for pass 1

**Date:** 2026-09-12
**How:** `.venv/Scripts/python.exe -m pip list` after `pip install -e ".[test]"`
**Result:** Python 3.11.9. Core resolved to typer 0.27.2, rich 15.0.0,
python-dotenv 1.2.3, pydantic-settings 2.15.0, httpx 0.28.1, pillow 12.3.0 —
all six inside their declared `>=min,<next_major` bounds. `[test]` resolved to
pytest 9.1.1, ruff 0.16.7, mypy 2.3.1. Transitive: pydantic 2.13.5 (via
pydantic-settings, as the plan states), plus annotated-doc, ast-serialize,
colorama, shellingham, librt, anyio, h11, httpcore, certifi, idna,
markdown-it-py, mdurl, pygments, typing-extensions, typing-inspection,
annotated-types, iniconfig, packaging, pathspec, pluggy, mypy-extensions.
**`click` is absent** — see the vendoring entry above.
**No torch, torchvision, timm or scikit-learn**, which is what makes pass 1's
milestone a real check.

---

## Pass 2

### Flickr API — endpoint, search method, limits, key access, response shape

**Date:** 2026-09-13
**How:** Flickr's own pages, fetched with `curl -sL` and read as text, plus one
live probe of the REST endpoint with a deliberately invalid key (no real key
exists — `.env` is empty, and was not opened):
```
https://www.flickr.com/services/api/request.rest.html
https://www.flickr.com/services/api/flickr.photos.search.html
https://www.flickr.com/services/api/response.json.html
https://www.flickr.com/services/api/misc.urls.html
https://www.flickr.com/services/developer/api/
https://www.flickr.com/services/api/misc.api_keys.html
https://www.flickrhelp.com/hc/en-us/articles/4404070036884-Flickr-API   (page reads "Updated August 06, 2025")
curl -s "https://www.flickr.com/services/rest/?method=flickr.photos.search&api_key=0000000000000000&text=cat&format=json&nojsoncallback=1&per_page=1"
curl -s "https://www.flickr.com/services/rest/?method=flickr.photos.search&text=cat&format=json&nojsoncallback=1"
```
**Result:**

| Item | Flickr's documentation says | Source |
|---|---|---|
| REST endpoint | `https://www.flickr.com/services/rest/` — plain GET or POST | request.rest.html |
| Search method | `flickr.photos.search`; "This method does not require authentication" (an `api_key` is still **required**) | flickr.photos.search.html |
| Arguments Optica uses | `api_key` (required), `text` (free text over title/description/tags), `sort` (`relevance` is a valid value; default `date-posted-desc`), `content_types` (`0` = photos), `media` (`photos`), `safe_search` (`1` = safe; "Un-authed calls can only see Safe content"), `extras` (includes `url_z`, `url_c`, `url_m`, `url_n`, `url_o`, …), `per_page` (default 100, **max 500**), `page` | flickr.photos.search.html |
| Result ceiling | "Flickr will return at most the first **4,000 results** for any given search query" | flickr.photos.search.html |
| Rate limit | "If your application stays under **3600 queries per hour across the whole key** … you'll be fine." Abuse leads to key expiry | developer/api/ |
| Caching | "Your application can cache API results and images for up to 24 hrs" | developer/api/ |
| Key access | "**The ability to request API keys is available exclusively to Pro subscribers.**" Non-commercial and commercial keys both exist; commercial use needs prior permission | flickrhelp.com article (2025-08-06); misc.api_keys.html |
| Free-account downloads | "Downloading original and large-size photos (**larger than 1024px**) from Free accounts is restricted via the Flickr API" | flickrhelp.com article |
| JSON format | `format=json` wraps in `jsonFlickrApi(...)`; success carries `"stat": "ok"`, failure carries `"stat": "fail"`, `"code"`, `"message"` | response.json.html |
| Image URL format | `https://live.staticflickr.com/{server-id}/{id}_{secret}_{size-suffix}.jpg`; suffix `z` = 640px longest edge, `c` = 800, `b` = 1024, `m` = 240; `h` (1600) and above have their own secret and "photo owner can restrict" | misc.urls.html |
| Search error codes | `100` Invalid API Key; `105` Service currently unavailable; `10` search API not currently available; `3` parameterless searches disabled | flickr.photos.search.html |

**Live probe result — both requests, verbatim:**

```
{"stat":"fail","code":100,"message":"Invalid API Key (Key has invalid format)"}
HTTP 200
```

**A failed call returns HTTP `200`.** The status line cannot detect an API
failure; only `stat` in the body can. `nojsoncallback=1` is honoured (the body
is bare JSON, no `jsonFlickrApi(...)` wrapper). A missing `api_key` returns the
same code 100 as a malformed one.

**Not found in Flickr's documentation:** what a *rate-limited* call receives —
no error code for it is listed under `flickr.photos.search`. The adapter
therefore treats HTTP `429`/`5xx` and `stat: fail` codes `10`/`105` as
retryable, and every other `stat: fail` as a hard `OpticaFetchError`.

**Consequence:** the plan's three claims hold — official `flickr.photos.search`,
`FLICKR_API_KEY` requiring a Pro subscription, 3,600 requests per hour per key.
The Flickr adapter checks `stat`, never the HTTP status alone; requests
`extras=url_z,url_c,url_m` so no second call per photo is needed; caps
`per_page` at 500; and stops paging at 4,000 results. `url_z` (640px) is
preferred — it matches the ~640×480 Open Images thumbnails and stays under the
1024px free-account restriction. **The adapter is written against this record
and never run against a real key.**

### Open Images — which files map a class to image URLs, and what they cost

**Date:** 2026-09-13
**How:**
```
curl -s https://storage.googleapis.com/openimages/web/download_v7.html     # 83 file links extracted
curl -sI <each link>                                                       # Content-Length, x-goog-hash
curl -s -D - -r 0-99 <label and metadata CSVs>                             # range support
curl -s -r <offset>-<offset+300> <CSV> at 0/25/50/75/100%                  # sort order
curl -s -r 0-67108863 v7/oidv7-train-annotations-human-imagelabels.csv     # + 4 x 32 MiB at 20/45/70/95%
curl -s -r 0-67108863 v5/train-annotations-human-imagelabels-boxable.csv
curl -s -r 0-8388607 and 8388608-16777215 v6/oidv6-train-images-with-labels-with-rotation.csv
curl -s -r 0-16777215 2018_04/image_ids_and_rotation.csv
```
Samples parsed by `.venv/Scripts/python.exe` (`csv`, `httpx` 0.28.1) under
`C:\Users\DEN\.claude\jobs\955142b7\tmp\`. All URLs are under
`https://storage.googleapis.com/openimages/`.

**Result 1 — the image-metadata CSVs carry no class labels.** Their 12 columns
(task 3, above) are URLs, licence and author fields. Mapping a class to images
needs a *label-annotation* file as well, joined on `ImageID`.

**Result 2 — candidate files, per item** (`Content-Length`):

| Role | File | Bytes | MiB |
|---|---|---|---|
| label mapping, full | `v7/oidv7-class-descriptions.csv` | 501,178 | 0.5 |
| label mapping, boxable | `v7/oidv7-class-descriptions-boxable.csv` | 12,064 | 0.0 |
| labels, V7 human-verified, train | `v7/oidv7-train-annotations-human-imagelabels.csv` | 2,735,816,020 | 2,609.1 |
| labels, V7 human-verified, val | `v7/oidv7-val-annotations-human-imagelabels.csv` | 28,392,297 | 27.1 |
| labels, V7 human-verified, test | `v7/oidv7-test-annotations-human-imagelabels.csv` | 93,606,939 | 89.3 |
| labels, boxable (600 classes), train | `v5/train-annotations-human-imagelabels-boxable.csv` | 376,764,810 | 359.3 |
| metadata, train images with labels | `v6/oidv6-train-images-with-labels-with-rotation.csv` | 2,684,720,962 | 2,560.3 |
| metadata, boxable train | `2018_04/train/train-images-boxable-with-rotation.csv` | 638,407,721 | 608.8 |
| metadata, all subsets | `2018_04/image_ids_and_rotation.csv` | 3,348,497,077 | 3,193.4 |

**Result 3 — access properties.** Every CSV probed answers `Range` with
`206 Partial Content` and `Accept-Ranges: bytes`, and carries
`x-goog-hash: md5=<base64>`. For both label-mapping files the header MD5 equals
the MD5 of the downloaded bytes:

| File | `x-goog-hash` md5 | MD5 of downloaded bytes |
|---|---|---|
| `oidv7-class-descriptions.csv` | `Kqy5GbIHxQ8qCEgipcJzbA==` | `Kqy5GbIHxQ8qCEgipcJzbA==` |
| `oidv7-class-descriptions-boxable.csv` | `xefLa4XQU5shBdstGXRoHw==` | `xefLa4XQU5shBdstGXRoHw==` |

**Result 4 — sort order.** Both **label** files are sorted by `ImageID`
(`000002b66c9c498e` first, `fffffdaec951185d` last, monotone at every probe).
The **metadata** files are **not** — first rows `4fa8054781a4c382`,
`d05c3e451f79174d`, and the 25/50/75% probes in no order. A metadata row cannot
be located by binary or interpolation search over byte ranges; only by reading.

**Result 5 — `oidv7-class-descriptions.csv`.** Header `LabelName,DisplayName`,
CRLF line endings, no BOM. **20,931 classes.** **Zero** display names are
shared by two MIDs, exact or case-folded, so display name → MID is unambiguous.
13 display names contain a comma (quoted); none contains an underscore.
`Cat` = `/m/01yrx`, `Dog` = `/m/0bt9lr`, `Golden retriever` = `/m/01t032`,
`Pug` = `/m/016wkx`, `Hamster` = `/m/03qrc`. `Golden retriever`, `Pug` and
`Tulip` are **absent** from the 600-class boxable list; `Cat`, `Dog`, `Hamster`
and `Screwdriver` are present.

**Result 6 — positive-label density is uneven along the V7 train file.**

| Window | Size | Rows | Images | Rows/image | Cat | Dog | Golden retriever | Pug | Hamster | Screwdriver |
|---|---|---|---|---|---|---|---|---|---|---|
| 0% | 64 MiB | 1,464,401 | 7,475 | 195.9 | 46 | 83 | 1 | 2 | 3 | 2 |
| 20% | 32 MiB | 729,903 | 18,027 | 40.5 | 112 | 203 | 14 | 6 | 1 | 0 |
| 45% | 32 MiB | 718,683 | 63,071 | 11.4 | 407 | 733 | 72 | 16 | 1 | 1 |
| 70% | 32 MiB | 718,070 | 146,645 | 4.9 | 1,112 | 1,799 | 69 | 31 | 17 | 0 |
| 95% | 32 MiB | 711,415 | 198,022 | 3.6 | 1,785 | 2,845 | 64 | 59 | 22 | 4 |

Counts are `Confidence` 1 rows. Pooled over the four 32 MiB windows (128 MiB,
4.91% of the file): Cat 3,416 → ~69,600 positives in the file; Golden retriever
219 → ~4,460; Pug 112 → ~2,280; Hamster 41 → ~840; Screwdriver 5 → ~100. The
pooled cells are the column sums of rows 20–95% (Cat 112+407+1,112+1,785 =
3,416). **Reading from the top of the file and stopping early samples the
sparsest region first** — 46 cats in the first 64 MiB, 1,785 in 32 MiB at 95%.

**Result 7 — the V6 metadata file covers the V7 train label images.** Of
45,838 sampled `v6/…with-labels…` rows, the 2,740 whose `ImageID` fell inside a
label window's ID range were **all** present in that window (2,740 of 2,740).
Implied coverage of the windows' 433,240 label images: 438,460 rows, 101.2% —
complete within sampling noise. `2018_04/image_ids_and_rotation.csv` (~9.18M
rows, all three subsets) over-covers: 2,393 of its 2,830 in-range rows had
labels.

**Result 8 — dead thumbnails.** 100 rows sampled at random (seed 7) from a
22,918-row window of the V6 metadata file; `Thumbnail300KURL` fetched
(`OriginalURL` where empty), redirects followed, sequentially:

| Outcome | Count |
|---|---|
| `200 image/jpeg` | 82 |
| `404 text/html` | 14 |
| `410 text/html` | 4 |
| **Total** | **100** |

Request hosts: `c1`–`c8.staticflickr.com` 98, `farm3`/`farm7.staticflickr.com`
2 (the two `OriginalURL` fallbacks); no redirect changed host. Live bodies
33,088 – 255,380 B, median 91,029. 100 requests took 44.0 s. In the window,
566 of 22,918 rows (2.47%) had an empty `Thumbnail300KURL` — matching task 3's
539 of 21,856 — and **no `Title` contained a newline**.

**Consequence:** the acquisition strategy chosen from these numbers is logged
in `notes/build-log.md` § "Open Images image-URL acquisition strategy". The
facts it rests on: labels are needed in addition to metadata; labels are sorted
and range-addressable, metadata is not; density depends on file position, so
sampling must spread across the file; ~18% of URLs are dead, so the pool needs
slack; the label map's integrity can be verified against GCS's own MD5.

### On Windows, `isatty()` is True for the `NUL` device

**Date:** 2026-09-13
**How:** Python 3.11.9 (`.venv`), Git Bash on the build machine:
```
python -c "import sys,os; print(sys.stdin.isatty(), os.isatty(0))" </dev/null
echo | python -c "import sys,os; print(sys.stdin.isatty(), os.isatty(0))"
python -c "import sys,os; print(sys.stdin.isatty(), os.isatty(0))" < pyproject.toml
python -c "import subprocess,sys; print(subprocess.run([sys.executable,'-c','import sys;print(sys.stdin.isatty())'],stdin=subprocess.DEVNULL,capture_output=True,text=True).stdout)"
# then, with stdin </dev/null: kernel32.GetFileType and kernel32.GetConsoleMode on msvcrt.get_osfhandle(0)
```
**Result:**

| stdin | `sys.stdin.isatty()` | `os.isatty(0)` |
|---|---|---|
| `</dev/null` (the `NUL` device) | **True** | **True** |
| `subprocess.DEVNULL` | **True** | — |
| a pipe (`echo \|`) | False | False |
| a regular file (`< pyproject.toml`) | False | False |

For `</dev/null`, `GetFileType` reports **`FILE_TYPE_CHAR`** and
`GetConsoleMode` **fails** — `NUL` is a character device but not a console.
**Consequence:** `isatty()` alone cannot tell "no stdin at all" from a terminal
on Windows. `utils/prompts.py:is_interactive` additionally requires
`GetConsoleMode` to succeed on Windows; see `notes/build-log.md` § "`is_interactive`
treated `NUL` as a terminal". POSIX is unaffected (`/dev/null` is not a tty).

### Which environment variables change Rich's output under the test suite

**Date:** 2026-09-13
**How:** Rich 15.0.0 (`.venv`). Every `environ.get` in
`rich/console.py` listed with `grep -n "environ"`; then the full suite
(`pytest tests -m "not slow"`, JUnit XML parsed for exact counts) run once per
variable from a parent environment with all of them removed —
`C:\Users\DEN\.claude\jobs\955142b7\tmp\env_matrix.py`.
**Result — variables Rich reads:** `FORCE_COLOR`, `NO_COLOR`, `TTY_COMPATIBLE`,
`TTY_INTERACTIVE`, `COLORTERM`, `TERM`, `COLUMNS`, `LINES`, `JUPYTER_COLUMNS`,
`JUPYTER_LINES`. `is_terminal` reads the environment on every call, but the
colour system is fixed once in `Console.__init__`.

**Result — suite outcome per variable, before the harness fix** (868 collected):

| Set in the environment | Passed | Failed | Skipped |
|---|---|---|---|
| none | 855 | 0 | 13 |
| `FORCE_COLOR=3` | 824 | **31** | 13 |
| `TTY_COMPATIBLE=1` | 824 | **31** | 13 |
| `NO_COLOR=1` | 855 | 0 | 13 |
| `TTY_INTERACTIVE=1` | 855 | 0 | 13 |
| `COLORTERM=truecolor` | 855 | 0 | 13 |
| `COLUMNS=30` | 855 | 0 | 13 |
| `TERM=dumb` | 855 | 0 | 13 |

Each row sums to 868. The 31 under `FORCE_COLOR=3`, by file: `test_logging` 13,
`test_main` 6, `test_fetch_command` 5, `test_classify` 4, `test_config_command`
2, `test_init` 1 (13 + 6 + 5 + 4 + 2 + 1 = 31). By authorship: **17 pass-1 tests,
14 pass-2 tests**. `TTY_COMPATIBLE=1` fails the same 31.
**Consequence:** the harness removes exactly those two before
`optica.utils.logging` is imported (`tests/conftest.py`). After the fix every row
above, plus all three of `FORCE_COLOR`/`TTY_COMPATIBLE`/`NO_COLOR` together,
gives 855 passed, 0 failed, 13 skipped — re-run with no scrubbing in the parent,
so the conftest alone holds.

### What cp1255 can and cannot encode, and what reaches the terminal

**Date:** 2026-09-13
**How:** `.venv` Python 3.11.9 in Git Bash on the build machine, stdout a pipe:
```
python -c "import sys, locale; print(sys.stdout.encoding, sys.stdout.errors, locale.getpreferredencoding(False))"
python -c "<char>.encode(sys.stdout.encoding)" for each character below
python -c "print('a—b')" | od -An -tx1
PYTHONIOENCODING=utf-8 python -c "print('a—b ✓')"
cmd //c chcp ; kernel32.GetConsoleOutputCP() / GetACP()
python -c "from optica.utils import logging as olog; olog.out_console.print('5 images → 4 unique')"
python -c "from optica.utils import logging as olog; olog.err_console.print('5 images → 4 unique')"
optica fetch -c café,dog --dry-run      (from .smoke/pass2-fetch/project, scratch home)
```
**Result:** stdout is `cp1255`, errors `surrogateescape`; console output code
page 862, ANSI code page 1255.

| Character | Encodable in cp1255 | Bytes |
|---|---|---|
| `—` U+2014 em dash | **yes** | `0x97` |
| `•` U+2022 bullet | **yes** | `0x95` |
| `✓` U+2713 | no | — |
| `✕` U+2715 | no | — |
| `✗` U+2717 | no | — |
| `⚠` U+26A0 | no | — |
| `→` U+2192 | **no** | — |
| `é` U+00E9 | **no** | — |

`print('a—b')` writes `61 97 62 0d 0a`; the terminal (Git Bash, decoding UTF-8)
shows `a�b`. With `PYTHONIOENCODING=utf-8` it shows `a—b ✓`.
`out_console.print('… → …')` raises **`UnicodeEncodeError`** (through
`rich/_win32_console.py` `write_text`); `err_console.print` of the same text
prints `\u2192` and exits 0. `optica fetch -c café,dog --dry-run` exits 1 with
`Optica hit an unexpected error: UnicodeEncodeError … '\xe9'`.
**Consequence:** two different problems that both render badly. The em dash and
bullet are **not** encoding failures — they encode, and the bytes are misread by
a UTF-8 terminal behind a pipe. `→` and `é` **are** encoding failures, and on
stdout they raise. See `notes/build-log.md` § "Correction — the em-dash finding
had the wrong mechanism".

### Why stderr escapes and stdout raises — CPython's stream error handlers

**Date:** 2026-09-13
**How:**
```
https://docs.python.org/3.11/using/cmdline.html#envvar-PYTHONIOENCODING
python -c "import sys; print(sys.stdout.errors, sys.stderr.errors)"                               # pipes, no overrides
PYTHONIOENCODING=ascii        python -c "import sys; print(sys.stdout.errors, sys.stderr.errors)"
PYTHONIOENCODING=ascii:strict python -c "import sys; print(sys.stdout.errors, sys.stderr.errors)"
PYTHONIOENCODING=ascii:strict python -c "from optica.utils import logging as olog; olog.err_console.print('Got: 猫')"
python -c "import io,sys; sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='ascii', line_buffering=True); from optica.utils import logging as olog; olog.err_console.print('Got: 猫')"
```
Python 3.11.9, `.venv`, stdout and stderr pipes.
**Result — documented:** the `PYTHONIOENCODING` entry reads, verbatim: *"For
stderr, the `:errorhandler` part is ignored; the handler will always be
`'backslashreplace'`."* It also says the Windows interactive-console exception
does not apply to "Files and pipes redirected through the standard streams".

**Result — measured:**

| Condition | `stdout.errors` | `stderr.errors` | `err_console.print('Got: 猫')` |
|---|---|---|---|
| pipes, no overrides | `surrogateescape` | `backslashreplace` | — |
| `PYTHONIOENCODING=ascii` | `strict` | `backslashreplace` | — |
| `PYTHONIOENCODING=ascii:strict` | `strict` | **`backslashreplace`** (the `:strict` is ignored) | prints `Got: 猫`, exit 0 |
| `sys.stderr` replaced by `TextIOWrapper(…, encoding='ascii')` | — | `strict` (the default for a new wrapper) | **`UnicodeEncodeError`**, exit 1 |

**Consequence:** stderr's degradation is guaranteed by CPython **for the
interpreter-created `sys.stderr` only**. It is incidental to Optica — nothing in
Optica set it — and it is lost the moment anyone replaces `sys.stderr` with an
ordinary text wrapper, whose default handler is `strict`. It also depends on Rich
writing text through the stream rather than encoding bytes itself, which is
Rich's current implementation (`rich/_win32_console.py` `write_text` →
`file.write`), not a documented contract. `PYTHONIOENCODING=ascii:strict` is a
reliable, documented way to make **stdout** strict ASCII on pipes on every
platform, which is what `tests/integration/test_output_encoding.py` uses.

---

## Pass 3

### FastAPI has not reached 1.0 — the `<1.0` ceiling stands

**Date:** 2026-09-14
**How:**
```
.venv/Scripts/python.exe -m pip index versions fastapi
curl -s https://pypi.org/pypi/fastapi/json          # every release, parsed with packaging.version
curl -s "https://api.github.com/repos/fastapi/fastapi/releases?per_page=5"
curl -s "https://api.github.com/repos/fastapi/fastapi/tags?per_page=100"
```
**Result:** latest is **0.141.1**. No release on PyPI has major ≥ 1, and no
pre-release of 1.0 exists either — the only pre-/dev releases ever published
are `0.100.0b1`–`b3`, `0.110.3.dev1`/`dev2` and `0.111.0.dev1`.

| Source | Latest | Published |
|---|---|---|
| PyPI `fastapi` | 0.141.1 | 2026-07-29T17:18:04 |
| PyPI, previous three | 0.141.0 / 0.140.13 / 0.140.12 | 2026-07-29 / 07-28 / 07-28 |
| GitHub releases, newest five | 0.141.1, 0.141.0, 0.140.13, 0.140.12, 0.140.11 | none marked pre-release |
| GitHub tags (100 newest) | all `0.*` except the ancient `v0.1.16` | — |

`fastapi` 0.141.1 metadata: `Requires-Python >=3.10`; runtime requirements
`starlette>=0.46.0`, `pydantic>=2.9.0`, `typing-extensions>=4.8.0`,
`typing-inspection>=0.4.2`, `annotated-doc>=0.0.2`.
**Consequence:** closes the plan's pre-implementation-gate item *"whether
FastAPI has reached 1.0, which changes the `<1.0` ceiling"* (plan
§ "Version-bound strategy", § "Two gates before implementation").
**`pyproject.toml`'s `fastapi>=0.141,<1.0` is correct and is not changed.** The
plan's Tech Stack snapshot (0.141.1) is still the latest.

### What `optica[web]` resolves to, and that it installs real Click

**Date:** 2026-09-14
**How:**
```
.venv/Scripts/python.exe -m pip install -e ".[test,web]"
.venv/Scripts/python.exe -m pip index versions uvicorn
.venv/Scripts/python.exe -m pip index versions starlette
python -c "import importlib.metadata as md; print(md.version(p), md.requires(p))"   # per package
python -c "import click; print(click.__file__)"
```
**Result:**

| Package | Resolved | Latest on PyPI | Declared runtime requirements (no extras) |
|---|---|---|---|
| `fastapi` | 0.141.1 | 0.141.1 | `starlette>=0.46.0`, `pydantic>=2.9.0`, … |
| `uvicorn` | 0.53.0 | 0.53.0 | **`click>=7.0`**, `h11>=0.8` |
| `starlette` | 1.6.0 | 1.6.0 | `anyio<5,>=3.6.2` |
| `click` | 8.5.0 | — | (pulled in by uvicorn) |
| `h11` | 0.16.0 | — | — |

`uvicorn` 0.53.0 sits inside `pyproject.toml`'s `uvicorn>=0.52,<1.0`.
`starlette` has passed 1.0, but it is not declared by Optica — FastAPI bounds it
from below only. All three ship `py.typed`.

**`import click` now succeeds** (`.venv/Lib/site-packages/click/__init__.py`).
**Consequence:** `CLAUDE.md` § "Settled points" ("`import click` fails in a Core
install") is still true for **Core**, and false once `optica[web]` is
installed. The danger it names — a second, unrelated `UsageError` class — is
therefore present in every `label`/`curate` environment. Optica is unaffected
only because it never imports `click`: Typer keeps raising its vendored
`typer._click` classes, which is what `cli/main.py` catches. `grep` for
`import click` across `src/` and `tests/` returns nothing. **Server code must
not import `click` either**, even though it would now import cleanly.

### uvicorn 0.53.0 can run in a worker thread on a socket Optica binds

**Date:** 2026-09-14
**How:** read `.venv/Lib/site-packages/uvicorn/server.py` (l.85–130, l.332–350)
and `uvicorn/config.py` (l.214–269, l.390–427, l.568–610).
**Result:**
- `Server.run(sockets: list[socket.socket] | None = None)` accepts pre-bound
  sockets, so the port Optica chose is the port served — no gap between probing
  a port and binding it.
- `Server.capture_signals()` installs signal handlers **only on the main
  thread** (`if threading.current_thread() is not threading.main_thread(): yield`).
  In a worker thread it leaves SIGINT to Python, so Ctrl+C reaches Optica's own
  main thread.
- `Server.started` is set at the end of `startup()`; `should_exit` is polled by
  `main_loop()` to stop.
- `Config(log_config=...)` defaults to uvicorn's `LOGGING_CONFIG` and applies it
  with `logging.config.dictConfig`; `log_config=None` skips that, leaving
  Optica's logging untouched. `access_log=False` silences per-request lines.
- A startup failure calls `sys.exit(STARTUP_FAILURE)` — inside a worker thread
  that ends the thread, so "thread dead and `started` False" is the failure test.
- uvicorn's own `bind_socket` sets `SO_REUSEADDR` (l.601) — relevant below.

### Binding a taken port on Windows, with and without socket options

**Date:** 2026-09-14
**How:** `.venv/Scripts/python.exe` on the build machine (win32): a listener on
`127.0.0.1:<ephemeral>`, then a second socket binding the same address under
each option; then the same against a `0.0.0.0` listener; then a rebind after a
server-side close.
**Result:**

| Second socket's option | Against a `127.0.0.1` listener | Against a `0.0.0.0` listener |
|---|---|---|
| none | refused, `10048` (WSAEADDRINUSE) | **bound** |
| `SO_REUSEADDR` | refused, `13` (access forbidden) | — |
| `SO_EXCLUSIVEADDRUSE` | refused, `10048` | **bound** |

Rebinding `127.0.0.1:<port>` with `SO_EXCLUSIVEADDRUSE` immediately after a
server-side close (the connection in `TIME_WAIT`): **bound**.
**Consequence:** a port already listening on the same address is refused on
Windows with no option set, so "try to bind, move on if refused" implements the
plan's auto-increment. `server/app.py` sets `SO_EXCLUSIVEADDRUSE` on Windows so no
later process can bind over Optica's port, and `SO_REUSEADDR` on POSIX so a port
left in `TIME_WAIT` by the previous run is reusable. **Not preventable on
Windows by either option:** binding `127.0.0.1:<p>` while another program
listens on `0.0.0.0:<p>` succeeds. The plan's "next free port" cannot see that
case. POSIX behaviour is not measured here; the port test constructs a
same-address listener, which is refused on every platform, and runs in CI.

### Hatchling ships `server/static/` in the wheel with no configuration

**Date:** 2026-09-14
**How:** `.venv/Scripts/python.exe -m pip wheel . --no-deps -w .smoke/wheel`, then
`zipfile.ZipFile(<wheel>).namelist()`.
**Result:** `optica-0.1.1-py3-none-any.whl` contains, under `optica/server/`:
`__init__.py`, `app.py`, `routes.py`, `static/shared.css`, `static/shared.js` —
5 of the 5 files on disk at the time. No `spec/` or `notes/` entry.
**Consequence:** non-Python files under `src/optica/` are package data by
default; `pyproject.toml` needs no `include` for the pages. Re-check when the two
HTML pages and their scripts land.

### Starlette 1.6.0's `TestClient` warns that `httpx` is deprecated for it

**Date:** 2026-09-14
**How:** `pytest tests/unit/server` under `.venv` (starlette 1.6.0, httpx 0.28.1).
**Result:** two warnings on importing `fastapi.testclient`, verbatim:
"StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is
deprecated; install `httpx2` instead." and "DeprecationWarning: The
anyio.abc.BlockingPortal alias is deprecated, use
anyio.from_thread.BlockingPortal instead." Tests pass.
**Consequence:** none now — test-only, and warnings are not errors in this
suite. `httpx` is Core, so moving the test client to `httpx2` would add a
package for tests alone; not done. Recorded so the warning is recognised rather
than chased when a later Starlette turns it into an error.

### `webbrowser.open` falls through to the real default browser when `BROWSER` fails

**Date:** 2026-09-14
**How:** read CPython 3.11.9's `Lib/webbrowser.py` in `.venv` (`open`, l.72–90;
`register`, l.23–36; `GenericBrowser`, l.159–185; the `BROWSER` block, l.584–596),
then, with `BROWSER='C:\Program Files\Git\usr\bin\true.exe'`:
```
python -c "import webbrowser; b = webbrowser.get(); print(type(b).__name__, b.name, b.args, webbrowser._tryorder[:3], b.open('http://127.0.0.1:9/probe'), webbrowser.open('http://127.0.0.1:9/probe'))"
"C:/Program Files/Git/usr/bin/true.exe" http://127.0.0.1:9/x; echo $?
```
**Result:**
- `BROWSER` is split on `os.pathsep`; each entry becomes `GenericBrowser(<entry>)`
  **prepended** to `_tryorder`. `GenericBrowser.open` runs `Popen([<entry>, url])`
  — the whole entry is the executable, with no arguments — and returns
  `not p.wait()`; `OSError` returns False.
- `webbrowser.open` walks `_tryorder` and **moves to the next browser whenever one
  returns False.**
- Measured: `_tryorder` head was `['C:\Program Files\Git\usr\bin\true.exe',
  'windows-default', 'C:\Program Files\Internet Explorer\IEXPLORE.EXE']`;
  `GenericBrowser`, args `['%s']`; both `open` calls returned `True`. `true.exe`
  with a URL argument exits `0`.
**Consequence:** to run `optica label`/`curate` live without opening a tab,
`BROWSER` must name an executable that exits 0. A value that is misspelt, needs
arguments, or exits non-zero **does not fail safe — `windows-default` opens the
real browser.** Independent of the test suite's `_no_real_browser` guard, which
exists only inside pytest.

### The wheel carries all eleven `server/` files

**Date:** 2026-09-14
**How:** `.venv/Scripts/python.exe -m pip wheel . --no-deps -w .smoke/wheel`, then
`zipfile.ZipFile(<wheel>).namelist()` filtered to `/server/`.
**Result:** `__init__.py`, `app.py`, `curation.py`, `labeling.py`, `routes.py`,
and under `static/`: `curation.html`, `curation.js`, `labeling.html`,
`labeling.js`, `shared.css`, `shared.js` — 5 modules + 6 static files = 11, every
file on disk. Closes the re-check promised in "Hatchling ships `server/static/`".

### Open Images Fetch More, live, through the curation page

**Date:** 2026-09-14
**How:** `optica curate --yes` from `.smoke/pass3-live/curate/` (scratch home
seeded from pass 2's `.smoke/pass2-fetch/home/.optica/`, `images_per_class = 12`),
driven over HTTP by `scratchpad/drive.py`: deselect 3 cat images, then
`POST /api/curate/fetch-more`.
**Result:** request `{"class": "cat", "requested": 3}` → finished `{"delivered":
3, "error": null}`; `cat` went from 9 of 12 selected to 12 of 15. The three new
files decode:

| File | Format | Size (px) | Bytes |
|---|---|---|---|
| `0013.jpg` | JPEG | 640×427 | 46,372 |
| `0014.jpg` | JPEG | 640×640 | 68,119 |
| `0015.jpg` | JPEG | 424×640 | 90,885 |

Numbering continued from `0012`; the class directory was renamed to `.partial`
and back during the fetch and the three deselections held. No label-map or index
download was needed — the seeded cache was reused.
**Consequence:** `input/curation.py:fetch_more` and the browser Fetch More path
are no longer "written but never run" for Open Images. Flickr remains unrun.

## Pass 4

### Windows drops a trailing `.` or space from a folder name
**Date:** 2026-09-15
**How:** on the build machine (Windows 11, NTFS), inside `.smoke/`:
```
python -c "import os; from pathlib import Path; d=Path('.smoke/cp0');
[os.makedirs(d/n, exist_ok=True) for n in ['cat','cat.','cat ']];
print(sorted(os.listdir(d)))"
```
**Result:** `['cat']` — three `makedirs` calls, one folder. `cat.` and `cat `
were both created as `cat` without an error.
**Consequence:** the amended class-name clause (plan l.242, "not end with `.` or
a space") is not cosmetic. Without it `-c cat,cat.` passes rule 2 (the two names
differ) and writes both classes into one folder on Windows.
`class_name_problem()` in `src/optica/input/classes.py`.

### open-clip-torch 3.3.0 — metadata, and where `ViT-B-32`/`openai` weights come from
**Date:** 2026-09-15
**How:**
```
pip download open-clip-torch --no-deps -d <scratch>        # wheel, unpacked
grep Requires-Dist open_clip_torch-3.3.0.dist-info/METADATA
open_clip/pretrained.py  : _VITB32["openai"], download_pretrained(), download_pretrained_from_url()
pip install --dry-run <wheel>                               # in .venv
python -c "import open_clip; print(open_clip.get_pretrained_cfg('ViT-B-32','openai'))"
```
**Result:**
- Latest on PyPI is still **3.3.0** (the plan's version table agrees). `Requires-Python >=3.9`.
  Unconditional: `torch>=2.0`, `torchvision`, `regex`, `ftfy`, `tqdm`,
  `huggingface-hub`, `safetensors`, `timm>=1.0.17`.
- Dry run into `.venv` would install exactly: `ftfy-6.3.1`, `open_clip_torch-3.3.0`,
  `regex-2026.9.10`, `wcwidth-0.8.3`. torch 2.14.0+cu130 untouched (re-checked after).
- `get_pretrained_cfg('ViT-B-32','openai')` = `url` openaipublic `.../40d36571.../ViT-B-32.pt`,
  `hf_hub` `timm/vit_base_patch32_clip_224.openai/`, mean `(0.48145466, 0.4578275, 0.40821073)`,
  std `(0.26862954, 0.26130258, 0.27577711)`, `interpolation` bicubic,
  `resize_mode` shortest, **`quick_gelu` True**.
- `download_pretrained` prefers the Hub whenever `huggingface_hub` imports — always,
  since it is a hard dependency. The Hub route asks for `open_clip_model.safetensors`
  first (`_get_safe_alternatives("open_clip_pytorch_model.bin")`). **Only the URL
  route checks a SHA-256**; the Hub route and a cached Hub file are not hashed.

**Consequence:** `input/clip.py` verifies the file itself (next entry).

### The CLIP weights file: size and SHA-256
**Date:** 2026-09-15
**How:** `HfApi().model_info('timm/vit_base_patch32_clip_224.openai', files_metadata=True)`;
then, after the live download, `ls -la <HF cache>/.../snapshots/*/`.
**Result:** repo revision `a6f597a30f7b82c51704746581f9a4e41421e878`, public, not gated,
licence apache-2.0.

| File | Size (bytes) | LFS SHA-256 |
|---|---|---|
| `open_clip_model.safetensors` | 605,143,284 | `e6d1bd7789aa45192b3bf90570a789b478bae1b74ebcce7eddd908e83a2b7c31` |
| `open_clip_pytorch_model.bin` | 605,225,782 | `9ecdaef325b20e7283dc6a32f92aa638d100899e4f084c2462d3832eeea0b26e` |
| `pytorch_model.bin` | 605,221,285 | `bd41409c7f2bb021cd96142f3a490caa78494cf4ec7f245d916bc33641a80d09` |

The downloaded safetensors file on disk is 605,143,284 bytes — matches. The plan's
"~600MB" is right (605 MB decimal, 577 MiB).

**Consequence:** `PINNED_WEIGHTS` in `input/clip.py`.

### The Hub cache on Windows without Developer Mode keeps no blob
**Date:** 2026-09-15
**How:** `HF_HUB_CACHE=.smoke/hfprobe`, `hf_hub_download(repo, 'open_clip_config.json')`, then `rglob`.
**Result:** the file sits directly at `snapshots/<rev>/open_clip_config.json`,
`is_symlink() == False`; `blobs/` is empty. huggingface_hub 1.31.0 also warns
"To support symlinks on Windows..." on each download.

**Consequence:** the expected hash cannot be read from a blob name on this
platform, so it is pinned. `load_clip` sets `HF_HUB_DISABLE_SYMLINKS_WARNING=1`.

### open-clip 3.3.0 does not apply the `openai` tag's QuickGELU — measured
**Date:** 2026-09-15
**How:** the first live `optica fetch --mode clip` printed
`UserWarning: QuickGELU mismatch between final model config (quick_gelu=False) and pretrained tag 'openai' (quick_gelu=True)`.
Source: `open_clip/factory.py` around l.430–452 — `force_quick_gelu` is the only
thing that sets it; the tag's value is compared only in order to warn. Then
`scratchpad/gelu_compare.py`: 120 Open Images candidates fetched in curate mode
(60 Cat, 60 Dog, human-verified labels), each scored on CUDA against
`a photo of a cat` and `a photo of a dog` by both builds.
**Result:**

| Build | class | n | own mean | own min | own max | own ≥ 0.25 | other mean | other ≥ 0.25 | own prompt best |
|---|---|---|---|---|---|---|---|---|---|
| plan's bare call (GELU) | cat | 60 | 0.2528 | 0.1825 | 0.2889 | 36 | 0.2147 | 2 | 54 |
| plan's bare call (GELU) | dog | 60 | 0.2468 | 0.1804 | 0.2850 | 32 | 0.1971 | 0 | 58 |
| `force_quick_gelu=True` | cat | 60 | 0.2587 | 0.1801 | 0.3059 | 45 | 0.2206 | 4 | 54 |
| `force_quick_gelu=True` | dog | 60 | 0.2500 | 0.1737 | 0.2915 | 31 | 0.2030 | 0 | 59 |

Per-image own-prompt change (QuickGELU minus GELU): cat mean +0.0060
(−0.0095 to +0.0220), **13 of 60 cross 0.25**; dog mean +0.0031 (−0.0096 to
+0.0213), **9 of 60 cross 0.25**. Only the QuickGELU build raised no warning.

**Consequence:** `MODEL_KWARGS = {"force_quick_gelu": True}`. Plan change proposed
in `notes/build-log.md`. A second observation, not acted on: on verified labels
the correct-class score averages about 0.25 in both builds — the plan's threshold
sits inside the true-positive distribution (build log).

### Live `optica fetch --mode clip`, three runs
**Date:** 2026-09-15
**How:** `.smoke/pass4-live/`, private `HOME`/`USERPROFILE`, real HF cache,
`optica fetch -c cat,dog --mode clip --yes ...`. Logs: `clip/run1.log`,
`clip/run2.log`, `clip2/run3.log`.
**Result:**

| Run | Code | Staging before | -i | Scored cat / dog | ≥ 0.25 cat / dog | Kept cat / dog | Wall |
|---|---|---|---|---|---|---|---|
| 1 | GELU (pre-fix); first use: 605 MB download + label index | empty | 20 | 40 / 40 | 23 / 22 | 20 / 20 | 3m10s |
| 2 | QuickGELU, `--overwrite` | 60 / 60, left by the comparison fetch (`--clear-staging` refuses unattended, correctly) | 20 | 60 / 60 | 45 / 31 | 20 / 20 | 8.5s |
| 3 | QuickGELU, fresh home, label cache copied in | empty | 25 | 50 / 50 | 38 / 27 | 25 / 25 | 12.2s |

Each reconciles. Run 3: cat 38 passed + 12 below = 50 scored, dog 27 + 23 = 50;
on disk 25 + 25 = 50, the success line's figure. Run 2's 45 / 31 equal the
comparison table's QuickGELU row on the same 120 files — the check that the CLI
builds the same model as the script. After runs 1 and 3 the class staging was
gone and no `.dataset.partial` remained. Exit 0 on all three, on `cuda`. Run 1's
first-use notice named the size and the cache path before downloading.

**Consequence:** clip mode is exercised end to end against Open Images and the
real model. The grouped path's scoring is exercised only by the fake-scorer
tests.

### What `.venv` holds, against `pyproject.toml`'s declared dependencies and extras
**Date:** 2026-09-15 (after pass 4 checkpoint 1's `open-clip-torch` install)
**How:** `.venv/Scripts/python scratchpad/env_audit.py` — reads `optica`'s own
installed `Requires-Dist` (the editable install's metadata, which matches
`pyproject.toml`), then for each root walks the installed dependency closure
through `importlib.metadata`, evaluating markers for this interpreter (CPython
3.11.9, Windows AMD64). The torch stack is audited as a fifth root although it is
not an extra: plan § "Package install split" gives it to `optica setup`. A second
query listed every installed `Requires-Dist` naming `click`.
**Result:** 65 installed distributions.

| Root | Declared | Installed (version) | State | Closure |
|---|---|---|---|---|
| Core | typer `>=0.27,<1.0`; rich `>=15.0,<16.0`; python-dotenv `>=1.2,<2.0`; pydantic-settings `>=2.15,<3.0`; httpx `>=0.28,<1.0`; pillow `>=12.3,<13.0` | 0.27.2; 15.0.0; 1.2.3; 2.15.0; 0.28.1; 12.3.0 | **full**, all in range | 22 |
| `[web]` | fastapi `>=0.141,<1.0`; uvicorn `>=0.52,<1.0` | 0.141.1; 0.53.0 | **full**, in range | 13 |
| `[clip]` | open-clip-torch `>=3.3,<4.0` | 3.3.0 | **full**, in range — since checkpoint 1; before it, **absent** | 32 |
| `[all]` | `optica[web,clip]` → the three above | as above | **full** (was partial: web only, until checkpoint 1) | 40 |
| `[test]` | pytest `>=9.1,<10.0`; ruff `>=0.16,<1.0`; mypy `>=2.3,<3.0` | 9.1.1; 0.16.7; 2.3.1 | **full**, in range | 13 |
| torch stack (setup-owned, not an extra) | torch, torchvision, timm, scikit-learn — no bounds, by design | 2.14.0+cu130; 0.29.0+cu130; 1.0.29; 1.9.1 | **full** | 34 |

**Partial extras: none.** **Reached by no root: `pip 26.2.1` only** — venv
tooling. Nothing arrived that no extra, Core, or the setup-owned stack accounts
for.

What checkpoint 1's install added, and nothing else: `open_clip_torch 3.3.0`,
`ftfy 6.3.1`, `regex 2026.9.10`, `wcwidth 0.8.3` (the dry run's list; each is now
reached only by `[clip]`/`[all]`). Everything else open-clip needs was already
present through the torch stack.

Distributions reached **only** by the torch stack (not by `[clip]`): scikit-learn
1.9.1 and its closure — scipy 1.17.1, joblib 1.6.0, threadpoolctl 3.6.0,
narwhals 2.26.0 (`scikit-learn` requires `narwhals>=2.0.1`), cloudpickle 3.1.2
(`joblib` requires `cloudpickle>=3.0`). Reached only by `[clip]`: ftfy, regex,
wcwidth, open-clip-torch.

**Real Click arrives through the torch stack, not only through `[web]`.**
`huggingface_hub 1.31.0` declares `click<9.0.0,>=8.4.2` **unconditionally**, and
both `timm` and `open-clip-torch` require `huggingface_hub`. Installed: click
8.5.0, reached by `[web]` (uvicorn `click>=7.0`), `[clip]`, `[all]` and the torch
stack. So `import click` succeeds in any environment with `optica[clip]` or
with what `optica setup` installs for training — not only under `optica[web]`, as
`CLAUDE.md`'s Click note currently says. Core alone still has no Click: typer
0.27.2 declares `shellingham>=1.3.0`, `rich>=13.8.0`, `annotated-doc>=0.0.2`,
`colorama; platform_system == "Windows"` — no `click` (`importlib.metadata.requires('typer')`).

**Consequence:** pass 5's `optica setup` installs torch, torchvision, timm and
scikit-learn; this entry is what a correct result looks like on CPython 3.11 /
Windows / CUDA 13.0 — including the six distributions only scikit-learn brings,
and real Click arriving with timm. The `except click.*` hazard `CLAUDE.md`
describes is live on every machine that can train, not only web installs.

**The shape of the problem, not just this instance:** `CLAUDE.md` names
`optica[web]` as *the* exception that lets real Click in. There are now at least
two routes — `[web]` (uvicorn) and the torch stack or `[clip]` (huggingface_hub)
— and a third could arrive with any dependency bump. A rule enumerating the
exceptions will go stale the same way; the durable statement is general: *real
Click may be importable in any environment beyond Core; never write `click.*`*.
The human replaces the `CLAUDE.md` wording at the pass boundary; it is not edited
by a pass.

### timm 1.0.29: the head, the top-level modules, and mobilenet's post-pool layers
**Date:** 2026-09-15
**How:** `.venv` (torch 2.14.0+cu130, timm 1.0.29), `scratchpad/timm_probe.py`:
`timm.create_model(name, pretrained=False)`, `named_children()` with parameter
counts, `reset_classifier(num_classes=3)` compared key-for-key and shape-for-shape
with `create_model(name, pretrained=False, num_classes=3).state_dict()`,
`get_classifier()`, `resolve_model_data_config()`, BatchNorm module names.
Extends § task 4; does not re-derive it — task 4's numbers are used as they stand.
**Result:**

| Model | `reset_classifier(3)` keys == `create_model(num_classes=3)` | shapes equal | keys | classifier |
|---|---|---|---|---|
| efficientnet_b0 | True | True | 360 | `Linear` → 3 |
| efficientnet_b4 | True | True | 706 | `Linear` → 3 |
| resnet50 | True | True | 320 | `Linear` → 3 |
| mobilenetv3_large_100 | True | True | 312 | `Linear` → 3 |

Top-level parameter counts not in task 4 (ImageNet heads, before replacement):

| Model | module | type | params |
|---|---|---|---|
| efficientnet_b0 | `bn2` | BatchNormAct2d | 2,560 |
| efficientnet_b4 | `bn2` | BatchNormAct2d | 3,584 |
| mobilenetv3_large_100 | `conv_head` (after `global_pool`) | Conv2d, with bias | **1,230,080** |
| mobilenetv3_large_100 | `norm_head` | **Identity** | 0 |
| mobilenetv3_large_100 | `act2`, `flatten` | Hardswish, Flatten | 0 |

mobilenet total 4,205,875 (task 4): `conv_head` is 29.2% of it. Last three
BatchNorm modules: b0 `blocks.6.0.bn2`, `blocks.6.0.bn3`, `bn2`; resnet50
`layer4.2.bn1/bn2/bn3`; mobilenet `blocks.5.2.bn2`, `blocks.5.2.bn3`,
`blocks.6.0.bn1`.
**Consequence:** `training/models.py` uses `reset_classifier` and finds the
head through `get_classifier()`; mobilenet's Phase 2 adds `conv_head` (build log).
`tests/unit/training/test_models.py` asserts every Phase 2 total against these
numbers.

### Evaluation preprocessing equals timm's own eval transform
**Date:** 2026-09-15
**How:** `tests/unit/training/test_transforms.py::TestTransforms::test_evaluation_matches_timms_own_eval_transform`
— a 300×420 random RGB image through Optica's torchvision pipeline
(`Resize(floor(input/crop_pct), bicubic)` → `CenterCrop(input)` → `ToTensor` →
`Normalize`) and through `timm.data.create_transform(**resolve_model_data_config(model), is_training=False)`.
**Result:** `torch.allclose(atol=1e-6)` for efficientnet_b0 (256→224),
resnet50 (235→224) and efficientnet_b4 (365→320).
**Consequence:** the transform `usage_examples.md` will teach at export is the
one timm itself uses for these configs.

### timm's pretrained weights on the Hugging Face Hub, per backbone
**Date:** 2026-09-15
**How:** `HfApi().model_info(<pretrained_cfg["hf_hub_id"]>, files_metadata=True)`
for each backbone's default tag.
**Result:** all public, not gated, licence apache-2.0.

| Backbone | Repo | Revision | `model.safetensors` bytes | SHA-256 |
|---|---|---|---|---|
| efficientnet_b0 | `timm/efficientnet_b0.ra_in1k` | `1b5383e5f79c` | 21,355,344 | `d569899762ea9b1384ee07f4af64805cf8caa1c55f9253ebb1080dc40e87a2cd` |
| efficientnet_b4 | `timm/efficientnet_b4.ra2_in1k` | `442c00e15609` | 77,933,206 | `8030f9c929ed71a06728db4b61323960e573b463e68f310bd1bfb31ed62cbf91` |
| resnet50 | `timm/resnet50.a1_in1k` | `767268603ca0` | 102,469,840 | `773525d5821de224f8f30c33377b7a795d7863e08522698200d3217d3f2a41bb` |
| mobilenetv3_large_100 | `timm/mobilenetv3_large_100.ra_in1k` | `96f46a1c5293` | 22,058,321 | `f425af34cc1cead2b5d6211f789a1f30b94835dc32f9c0fcc5a916e4fd2dde85` |

Sum of the four: 223,816,711 bytes (21.4 + 77.9 + 102.5 + 22.1 MB). Each repo
also carries a `pytorch_model.bin` 72.5–169.3 kB larger (b0 +86,561; b4 +169,319;
resnet50 +75,389; mobilenet +72,512 bytes).
**Consequence:** a first `optica train` downloads one of these (22–102 MB). The
plan gives timm weights no first-use notice or verification rule, unlike CLIP's;
none is added (build log).

### The "unauthenticated requests" warning is server-sent, and why it printed twice
**Date:** 2026-09-15
**How:** `grep` over `huggingface_hub 1.31.0` found no such string;
`huggingface_hub/utils/_http.py:_warn_on_warning_headers` logs the text of an
`X-HF-Warning` response header through the `huggingface_hub` logger, once per
topic per process. `huggingface_hub/utils/logging.py:_configure_library_root_logger`
adds its own `StreamHandler`; Optica's `configure_stdlib_logging` adds a root
handler via `basicConfig(force=True)`.
**Result:** the record went to the Hub's handler (bare text) and propagated to
the root handler (`WARNING huggingface_hub.utils._http: …`). The Hub's own
`disable_propagation()` docstring says propagation is off by default; on this
install the logger's `propagate` was True — the double print proves it.
**Consequence:** `utils/mlstack.py:prepare_hub` sets
`logging.getLogger("huggingface_hub").propagate = False` — one print, not
silenced. It also has to run *before* `import timm`, because timm imports the
Hub, which reads `HF_HUB_DISABLE_SYMLINKS_WARNING` at import: the first smoke run
still printed the symlink warning until `import_torch_stack` called it first.

### Smoke run — `optica train` on the clip-mode dataset
**Date:** 2026-09-15
**How:** `.smoke/pass4-live/train-smoke/`, dataset copied from `clip2/dataset`
(cat 25, dog 25), private home, `optica train --epochs 3 --yes`. Log `smoke1.log`.
**Result:** exit 0 in 15.9 s wall on `CUDA GPU: NVIDIA GeForce RTX 4070 Ti`.
Split per class 19/3/3 (25 → `n_val = floor(3.75) = 3`, `n_test = min(3, 21) = 3`,
19 + 3 + 3 = 25). Phases 1 + 2. Epochs: val_accuracy 1.000 all three; train
accuracy 0.526 → 0.763 → 0.868. Test accuracy 0.833, loss 0.619 (best
checkpoint, 6 test images). Three checkpoints retained; `checkpoint.pt` 16.4 MB
at epoch 1 (Phase 1 optimizer state: head only) and 41.7 MB at epoch 2 (Phase 2
state for the unfrozen groups). `torch.load(..., weights_only=True)` loads it;
keys `state_dict` (360 tensors, `classifier.weight`/`classifier.bias`) and
`optimizer_state`. Both log copies byte-identical.
**Consequence:** not the checkpoint 4 milestone — a smoke run, before the tests
were written. It found the symlink-warning ordering above.

### A `pretrained=False` backbone is nearly input-blind
**Date:** 2026-09-15
**How:** `.venv`; `torch.manual_seed(0)`; `timm.create_model("efficientnet_b0", pretrained=False, num_classes=2).eval()`;
two random inputs `rand(1,3,224,224)` and `rand(...)*3 - 1.5`; then the same model
built via `create_model(pretrained=False)` + `configure_head` (i.e.
`reset_classifier`), classifier weights scaled ×1e4, fed one random image through
Optica's evaluation transform, a no-`Normalize` pipeline and a bilinear pipeline.
**Result:** unscaled logits `[1.60e-4, -8.60e-5]` vs `[-2.46e-5, 6.87e-5]` — max
difference 1.85e-4; softmax 0.5001/0.4999 vs 0.5000/0.5000. Scaled, head from
`create_model(num_classes=2)`: logit shifts no-Normalize 2.006, bilinear 0.409,
resize-235 0.850. Scaled, head from `reset_classifier`: no-Normalize 0.0097,
bilinear 0.0045. Normal-init heads std 1 / std 100: bilinear 0.0000 / 0.0005.
**Consequence:** a test comparing a random model's outputs cannot detect a wrong
preprocessing. `tests/unit/export/test_pytorch.py` compares the preprocessed
tensor and the weights exactly instead.

### Pass 4 milestone — `optica fetch` → `optica train` → `optica export`, one chain
**Date:** 2026-09-15 (11:13:24–11:16:46 UTC)
**How:** `.smoke/pass4-live/milestone.sh`, started with the Bash tool's
`run_in_background`, in a fresh project `.smoke/pass4-live/milestone/` and a
fresh private home `home3` (only the Open Images class list copied in;
`HF_HOME` = the real Hugging Face cache, which held the CLIP weights and
efficientnet_b0 but **not** mobilenetv3). `PYTHONIOENCODING` deliberately unset.
The three commands run with `&&`, each writing `<step>.out`, `<step>.err` and an
`END <step>: exit N after Ns` line to `chain.log`. Verification is a separate
script, `.smoke/pass4-live/verify_milestone.py`, run afterwards in a new Python
process against the artifacts only.
**Result — the chain:**

| Step | Command | Exit | Wall |
|---|---|---|---|
| fetch | `optica fetch -c cat,dog,horse -i 30 --mode clip --yes` | 0 | 181 s |
| train | `optica train --model mobilenet --epochs 10 --yes` | 0 | 18 s |
| export | `optica export --yes` | 0 | 3 s |

Fetch: 60 candidates per class; at clip_threshold 0.25 cat 45, dog 31, horse 37
passed; 30 kept each (45 + 15 = 60, 31 + 29 = 60, 37 + 23 = 60); 90 in `dataset/`.
Train: `CUDA GPU: NVIDIA GeForce RTX 4070 Ti`; mobilenetv3_large_100 weights
downloaded on first use inside the run; split 22/4/4 per class (30 →
`n_val = floor(4.5) = 4`, `n_test = min(floor(4.5), 25) = 4`; 3 × 30 = 90);
phases 3 + 7; val accuracy per epoch 0.833, 0.917, 0.917, 1.000, 1.000, 1.000,
1.000, 0.917, 0.750, 0.833; three checkpoints retained (epochs 5, 6, 7, all val
1.000 — rank 1 is epoch 7 by the higher-epoch tie-break, although epoch 5's test
accuracy is higher: test metrics never rank, as the plan requires). Completion
block: best val_accuracy 1.000; Epochs 10 of 10; Test accuracy 0.833, loss 0.704.
Export: `optica-output/mobilenet_3cls_20260915_141645/`, rank 1 of 3.

**Result — the handoff: 24 `[OK]` lines, no `[FAIL]`.** Of the 24, 23 are
checks that can fail; one ("copies the checkpoint's metrics…") is a summary
printed unconditionally, its 18 per-key comparisons each printing `[FAIL]` on a
mismatch — which the bite run below shows them doing:
- every checkpoint carries one `run_id` (`20260915_141628`), the run-end pair,
  `interrupted: false`; the two log copies are byte-identical; the log's
  `checkpoint_paths` equal the folders on disk;
- `model_info.json`: `run_id` is the run's; rank 1 of 3; `checkpoint_path`
  `checkpoints/checkpoint_val1.000_epoch7/` — the rank-1 checkpoint; metrics,
  preprocessing, config, `dataset_path`, `log_file` copied unchanged from it;
  `class_names.json` = checkpoint `classes` = sorted dataset folders
  (`cat, dog, horse`); `log_file` expands to the global log;
- `model.pt` loads with `weights_only=True`, keys in the plan's order, and its
  `state_dict` equals the rank-1 checkpoint's tensor for tensor (312 tensors);
- the generated `usage_examples.md`, executed on the **real test split**
  (reproduced from the checkpoint's `random_state` and split ratios, and equal
  to the log's split counts): preprocessing tensor-identical to training's
  evaluation transform for 12 of 12 images; 10 correct of 12 = 0.833333 =
  recorded `test_accuracy`; mean loss 0.704148 on CPU vs recorded 0.704209 on
  CUDA (|Δ| 6.1e-5). Per image: cat 3/4 (0043 → dog), dog 4/4, horse 3/4 (0049 →
  dog).

**The verifier can fail:** with `checkpoint_val1.000_epoch5`'s `epoch` set to 99
on disk (making it rank 1), 7 checks failed — checkpoint_path, val_loss,
test_accuracy, test_loss copied, state_dict equality, usage-example accuracy and
loss. File restored (byte-compared); all checks pass again.

**Consequence:** pass 4's milestone — `optica train` and `optica export` running
to completion on a small real dataset, export consuming that training run — is
met. What the path did **not** exercise is recorded in the build log's close.

## Pass 5

### Pass 5 milestone, claim 1 — `optica.run()` works from Python
**Date:** 2026-09-20
**How:** `.smoke/pass5/drive_run.py`, a plain Python caller (not the CLI, not
pytest), run by `.venv`'s interpreter in `.smoke/pass5/project/` with a private
`HOME`/`USERPROFILE` (`.smoke/pass5/home`, seeded only with the Open Images
class-list cache) and the real Hugging Face cache. It calls
`optica.run(["cat","dog"], mode="clip", images_per_class=10,
train_config=optica.TrainConfig(epochs=2))`, writes `result.json`, and asserts
nothing. Verification is a separate script, `.smoke/pass5/verify_run.py`, which
reads `result.json` and the project tree and **never opens `drive.out` or
`drive.err`** — a run that reported success while writing nothing fails it.

**How the browser was kept out:** `mode="clip"`. Clip mode has no browser stage
at all — the plan's own answer for a fully non-interactive pipeline. Nothing was
stubbed, monkeypatched or answered; the label and curate stages were therefore
**not exercised** (see the standing list in `notes/build-log.md`).

**Result:** exit 0 in **27.6 s**. Fetch (clip) → train → export, one call.

| Artifact | What the checker found |
|---|---|
| `dataset/` | cat 10, dog 10 — equal to `FetchResult.counts`; no `.dataset.partial` |
| Checkpoints | 2 retained; `best_checkpoint` is the first of `TrainResult.checkpoints` |
| `checkpoint_info.json` | `val_accuracy` 0.500 = `best_val_accuracy`; `epochs_trained` 2 = `epochs_run`; `early_stopped` **false**, equal to `TrainResult.early_stopped` — read from the file, not from the object that produced it; `config` block holds exactly `TrainConfig`'s eleven keys; `classes` = the dataset's sorted folder names |
| Phases | `[1, 1]`, summing to `epochs_requested` 2 |
| Logs | both copies present and byte-identical |
| Export folder | `class_names.json`, `model.pt`, `model_info.json`, `usage_examples.md` — exactly `ExportResult.files`; no `.partial` |
| Cross-artifact | `class_names.json` == `model_info["classes"]` == the checkpoint's `classes`; `model_info`'s `epochs_trained`/`early_stopped` equal the checkpoint's |
| `model.pt` | loads under `torch.load(weights_only=True)`; its `classes` and `num_classes` agree with `class_names.json` |
| Staging | consumed: `~/.optica/staging` empty |

**24 checks, 24 passed.** Proved to bite by three artifact mutations, each
reverted: one dataset image removed (`counts` check failed, 9 vs 10),
`model_info.json`'s `classes` edited to `["cat","fox"]` (the three-way class
agreement failed), and `early_stopped` deleted from the **best** checkpoint's
info (two checks failed). A fourth attempt deleted the field from a *non-best*
checkpoint and correctly changed nothing — the checker reads the folder the
result names — which is why that attempt was repeated against the right one.

**Note:** the run produced **zero warnings**, so `RunResult.warnings` was empty
and no `OpticaWarning` was emitted. The warning contract is exercised by tests
only.

### Pass 5 milestone, claim 2 — `optica setup` redoes no work on a second run
**Date:** 2026-09-20
**How:** `.smoke/pass5/setupproj/`, private `HOME`/`USERPROFILE`
(`.smoke/pass5/setuphome`), whose `~/.optica/config.toml` was seeded with
`epochs = 20` before anything ran. Then: snapshot → `optica setup --all-extras`
→ snapshot → `optica setup --all-extras` → snapshot, each snapshot written by
`.smoke/pass5/snapshot.py`. `.smoke/pass5/verify_setup.py` compares the three
and **opens neither run's log**.
**What "without redoing work" was taken to mean**, stated rather than assumed:
no watched distribution's version changed, no distribution's `dist-info`
directory was rewritten (`mtime_ns` is what pip touches on a reinstall),
site-packages gained no entry, and the config's bytes are identical.

**Result:** both runs exit 0. All seven watched distributions — torch,
torchvision, timm, scikit-learn, fastapi, uvicorn, open-clip-torch — were
**already installed before either run**, which is the premise and the limit.
Run 1 wrote the config and preserved `epochs = 20`; run 2 changed no version, no
`dist-info` mtime, no site-packages entry count (146 → 146) and not even the
config's `mtime_ns`. **11 checks, 11 passed**, proved to bite by four snapshot
mutations, each reverted: a bumped version, a bumped `dist-info` mtime with a
site-packages entry, a changed config digest and mtime, and run 1's config text
with the user's value stripped out.

**This is the Skip path and nothing more.** No `pip install` ran, so it is
evidence that setup does not redo work and **not** evidence that installation
works.

### `optica setup`'s Review printed a raw glyph on a non-UTF-8 console
**Date:** 2026-09-20
**How:** the live run above, on this machine's cp1255 console.
**Result:** `PackageState.INSTALLED` held the plan's literal
`already installed ✓`, and the tick reached the stream as a data string rather
than through `Markers`, so `protect_streams` escaped it: the Review read
`already installed ✓`. Not a crash — that is the designed degradation for
arbitrary text — but the tick is one of the four status glyphs `Markers` exists
to resolve.
**Consequence:** fixed; the state stores `already installed` and `_review` adds
`marks.ok`. Re-run live: `already installed +`. A glyph with a good ASCII
stand-in must go through `Markers`, not into a constant.

## Pass 6

### `ubuntu-latest` moves to Ubuntu 26.04 — the window, and that it is gradual
**Date:** 2026-09-21
**How:** fetched `https://github.com/actions/runner-images/issues/14748` and
`https://raw.githubusercontent.com/actions/runner-images/main/README.md`
**Result:** the issue is titled *"[Ubuntu] `ubuntu-latest` label will use Ubuntu
26.04 in November 2026"* and is **open**. The rollout *"will be rolled out over
a period of several weeks beginning October 19, 2026"*, completing *"by November
19, 2026"*. The README's current label table:

| Label | Today |
|---|---|
| `ubuntu-latest` | Ubuntu 24.04 |
| `ubuntu-24.04` | Ubuntu 24.04 |
| `ubuntu-26.04` | Ubuntu 26.04 |
| `macos-latest` | macOS 26, arm64 |
| `windows-latest` | Windows Server 2025 |

The README's own guidance: *"To avoid unintended OS version changes during the
`-latest` label migration period, specify a specific OS version in the yaml
file."*
**Consequence:** the pass 6 brief gave the date as *"migrates to Ubuntu 26 from
19 October 2026"*. The start date is right; the migration **completes a month
later, on 19 November**, and is **gradual** in between — which is the fact that
decides the question. For that month `ubuntu-latest` is nondeterministic: two
runs of the same commit can land on different operating systems. `ci.yml`
therefore pins **`ubuntu-24.04`**. Reasoning in `notes/build-log.md`.

### Every declared lower bound is a real release
**Date:** 2026-09-21
**How:** `python -m pip index versions <pkg>` for each of the nine packages a CI
leg installs, then `pip install -e ".[test]" -c .github/constraints-min.txt`
into a fresh `.smoke/min-venv`.
**Result:** each `>=` bound in `pyproject.toml` has an exact release at the
floor, so the `min` leg pins to a version that exists rather than to the lowest
release above a gap:

| Package | Bound | Floor release | Installed in `.smoke/min-venv` |
|---|---|---|---|
| `typer` | `>=0.27` | 0.27.0 | 0.27.0 |
| `rich` | `>=15.0` | 15.0.0 | 15.0.0 |
| `python-dotenv` | `>=1.2` | 1.2.0 | 1.2.0 |
| `pydantic-settings` | `>=2.15` | 2.15.0 | 2.15.0 |
| `httpx` | `>=0.28` | 0.28.0 | 0.28.0 |
| `pillow` | `>=12.3` | 12.3.0 | 12.3.0 |
| `pytest` | `>=9.1` | 9.1.0 | 9.1.0 |
| `ruff` | `>=0.16` | 0.16.0 | 0.16.0 |
| `mypy` | `>=2.3` | 2.3.0 | 2.3.0 |

`rich` and `pillow` are at their floor *and* their ceiling — 15.0.0 and 12.3.0
are the latest releases — so for those two the `min` and `max` legs install the
same version until the next release.
**Consequence:** `.github/constraints-min.txt` is these nine pins. The `min` leg
is not speculative: the full gate was run against it (next entry).

### The minimum-version leg is green — measured, not assumed
**Date:** 2026-09-21
**How:** in `.smoke/min-venv` (the nine floors above, Python 3.11.9):
`ruff check`, `mypy`, `pytest -m "not slow"`
**Result:** Ruff *All checks passed*; mypy *Success: no issues found in 119
source files*; pytest **2334 passed, 26 skipped, 76 deselected** — identical to
`.smoke/ci-venv` at the latest versions.
**Consequence:** the risk that pinning Ruff and mypy to their floors reddens CI
for a reason unrelated to Optica was checked rather than argued about, and did
not materialize. The `min` leg runs the full gate, not a reduced one.

### `optica[web]` unskips 62 tests, not 27 — and brings real Click
**Date:** 2026-09-21
**How:** `pytest --collect-only -q` per file in `.venv`; then a fresh
`.smoke/web-venv` built with `pip install -e ".[test,web]"` — exactly what the
web leg installs — and the full gate run in it.
**Result:** the breakdown:

| Skipped without `optica[web]` | Tests |
|---|---|
| `tests/unit/server/test_routes.py` (module-level `importorskip`) | 49 |
| `tests/unit/server/test_app.py::TestServe` | 8 |
| `tests/integration/test_server.py` (socket tests) | 5 |
| **Total** | **62** |

Confirmed by difference: 2396 passed with the extra, 2334 without.
`.smoke/web-venv` resolved `fastapi` 0.141.1, `uvicorn` 0.53.0, `starlette`
1.6.0 and **`click` 8.5.0**, with no torch and no `open-clip-torch`. Gate:
Ruff clean, mypy clean, **2396 passed, 12 skipped, 76 deselected**.
**Consequence:** the pass 6 brief's figure — *"27 tests — 19 route, 8
TestServe"* — undercounts. `test_routes.py` collects 49 (34 `def test_`
functions, parametrized), and the 5 integration socket tests were not in the
brief's count at all. The requirement is unchanged and the arrangement is
unchanged; only the number CI recovers is larger. The web leg is also where
real Click is present, which is why the `import click` guard runs on the
extras-free legs instead.

### `optica setup --ci` on a clean home, twice
**Date:** 2026-09-21
**How:** with `HOME`/`USERPROFILE` pointed at an empty directory:
`optica setup --ci` twice in `.smoke/min-venv`, then once each in
`.smoke/ci-venv` and `.smoke/web-venv`.
**Result:** first run *"configuration created at …\.optica\config.toml"*, exit
0; second run *"configuration already present at …"*, exit 0. One file written,
`.optica/config.toml`. No prompt, no install, no environment detection. Same in
all three environments, and `optica --version` printed `optica 0.1.1` in each.
**Consequence:** the step is safe to put on every matrix leg. It had never run
outside a developer venv before this; it does not read or write anything outside
`$HOME/.optica/`, so a runner's home is all it needs.
