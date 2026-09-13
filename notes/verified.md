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
