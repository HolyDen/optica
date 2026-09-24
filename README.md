# Optica

> Transfer learning for everyone. Build an image classifier in one command.

![PyPI](https://img.shields.io/pypi/v/optica)
![Python](https://img.shields.io/pypi/pyversions/optica)
![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![CI](https://github.com/HolyDen/optica/actions/workflows/ci.yml/badge.svg)

Optica handles the whole image-classification pipeline — sourcing training
images, reviewing them, training a model, exporting something deployable. No ML
expertise needed for the basics; full programmatic control when you want it.

```bash
pip install optica
optica setup
optica run -c cat,dog --mode clip
```

---

## Status

**v0.2.0 is the initial release.** Everything documented here is implemented and
covered by an automated test suite of roughly 2,400 tests.

Some paths have had far less real-world exercise than others, and it is more
useful to say so than to let you find out. In this release the following are
covered by tests but have not been run end to end against the real thing:

- **Interactive prompts.** Every prompt is driven by tests rather than typed at
  a terminal — the resume menu, the setup prompts, the export checkpoint
  selection, the class-definition prompt.
- **The Flickr source.** `--source flickr` needs a key and a Flickr Pro
  subscription. `--source open-datasets` is the default and the exercised path.
- **Apple-silicon GPU (MPS).** Device selection falls back to CPU correctly, but
  the MPS branch itself has not run on Apple hardware.
- **`optica setup`'s first install**, and its CPU-only branch. Setup has so far
  been run against an already-provisioned machine with a CUDA GPU.
- **Resuming after a genuine interruption.** Resumption is driven by tests from
  constructed state, not from a real Ctrl-C.
- **The pipeline on Linux and macOS.** Every end-to-end run so far — fetch,
  train, export — has been on Windows. CI covers all three platforms, but it
  deliberately never installs PyTorch, so what runs there is the test suite
  rather than a real training run.

Please report anything you hit.

---

## Installation

```bash
pip install optica          # the lightweight core
optica setup                # installs PyTorch, matched to your hardware
```

**Why two steps?** PyTorch ships different builds for different hardware, from
different package indexes. `optica setup` detects your GPU, picks the right
build and installs it — something `pip install optica` alone cannot do, because
a wheel's index cannot depend on the machine it lands on.

> **`requirements.txt` note.** For the same reason, `pip freeze > requirements.txt`
> will not reproduce an Optica environment on a different machine: the torch
> build it captures is the one your hardware got. Pin `optica` in your
> requirements file and run `optica setup` as a separate step in your build.
> This is a known characteristic of the PyTorch ecosystem rather than an Optica
> bug — PyTorch itself documents the same two-step install.

### Optional extras

| Extra | Installs | Enables |
|---|---|---|
| `optica[web]` | FastAPI, uvicorn | `optica label`, `optica curate`, and `optica run` in label or curate mode |
| `optica[clip]` | open-clip-torch | CLIP auto-filtering (`--mode clip`) |
| `optica[all]` | both of the above | Everything |

```bash
pip install optica[all]
optica setup
```

`optica setup` can install these for you — `optica setup --include-extras web,clip`
— which is usually easier than getting the bracket quoting right for your shell.
If a command needs an extra you do not have, Optica tells you which one and how
to install it before it does any work.

### Where to start

The install you need depends on what you want to do, not on how experienced you
are:

| You want to | Install | Start at |
|---|---|---|
| One command, start to finish | `optica` + `optica setup` | `optica run` (Tier 1) |
| Run the steps separately | same | `optica fetch`, `train`, `export` (Tier 2) |
| Call it from Python | same | `optica.run()` (Tier 3) |
| Compose steps in Python | same | `optica.fetch()`, `optica.train()`, … (Tier 4) |
| Hold the model object | same | `Classifier` (Tier 5) |
| Review images in a browser | add `optica[web]` | `optica label`, `optica curate` |
| Filter images automatically | add `optica[clip]` | `--mode clip` |

`import optica` works with no extras and no PyTorch installed, so the whole API
surface is visible to your editor and type checker from the moment you install
the core.

---

## Quick Start (Tier 1)

One command does everything: fetch images, filter or review them, train, export.

```bash
optica run -c cat,dog --mode clip
```

That fetches 50 images per class from Open Images, keeps the ones CLIP agrees
are cats and dogs, trains a classifier and writes a `.pt` model.

Class names are used directly as search queries, so **be specific**:
`golden retriever` will fetch better images than `dog`, and `sedan` better than
`car`. Multi-word names are quoted per value:

```bash
optica run -c "golden retriever","border collie" --images-per-class 200
```

Three ways to get images in:

```bash
# Optica fetches, CLIP filters — fully unattended
optica run -c cat,dog --mode clip

# Optica fetches, you review in a browser                  (needs optica[web])
optica run -c cat,dog --mode curate

# Your own images, you label them in a browser             (needs optica[web])
optica run --folder ./my-images -c cat,dog --mode label
```

> **`--yes` does not skip browser curation.** It answers Y/N prompts; it cannot
> answer "which of these 400 images are actually cats". For a pipeline with no
> human in it, use `--mode clip` — that is the non-interactive acquisition path,
> and it is why clip mode exists.

---

## The CLI (Tier 2)

The same pipeline, one step at a time.

```bash
optica fetch  -c cat,dog --images-per-class 100 --mode clip
optica curate                                 # browser review    (optica[web])
optica label  --folder ./my-images -c cat,dog # browser labeling  (optica[web])
optica train  --epochs 20 --model efficientnet-large
optica export --checkpoint-rank 1
```

Add `--dry-run` to any of them to see what would happen without doing it.

```bash
optica config --view              # resolved settings, annotated with their source
optica config --set epochs 20     # write a setting
optica config --init              # create a project-local .optica.toml
optica setup                      # environment, packages, configuration
```

### Flags

| Flag | Alias | Default | Applies to / notes |
|---|---|---|---|
| `--classes` | `-c` | inferred (`train` only) | Required for `fetch`/`label`. Comma-separated; quote per value: `-c "orange cat",dog`. Ignored with a warning by `curate` |
| `--source` | `-s` | `open-datasets` | `fetch`, `run`. `flickr`, `open-datasets` |
| `--images-per-class` | `-i` | `50` | `fetch`, `run` |
| `--mode` | none | contextual | `fetch`, `run`. `label`, `curate`, `clip` — `fetch` takes `curate` or `clip`. Defaults to `curate` when fetching, `label` with `--folder`/`--manifest` |
| `--clip-threshold` | none | `0.25` | `fetch`, `run`. CLIP confidence cut-off for clip mode |
| `--model` | none | `efficientnet-small` | `train`, `run`. `efficientnet-small`, `efficientnet-large`, `resnet`/`resnet-50`, `mobilenet`/`mobilenet-large` (each pair names one model) |
| `--epochs` | `-e` | `10` | `train`, `run` |
| `--batch-size` | none | `32` | `train`, `run`. Reduce if you run out of memory |
| `--no-augmentation` | none | off | `train`, `run`. Disables all data augmentation |
| `--checkpoint-rank` | none | **prompts** | `export`, `run`. Absence is *not* rank 1 — it asks. Accepts `1,2,3`. `--checkpoint` is a permanent alias |
| `--folder` | none | — | `label`, `run`. A flat folder to label. Distinct from `--dataset` |
| `--manifest` | none | — | `label`, `run`; `train` when fully labeled. CSV or JSON |
| `--dataset` | `-d` | `./dataset` | `fetch`, `label`, `curate`, `train`, `run`. The organized dataset folder |
| `--output` | `-o` | `./optica-output` | `train`, `export`, `run`. Container for exports and the project-local log |
| `--overwrite` | none | off | Every path that writes `dataset/`. Authorizes the overwrite prompt unattended — neither `--yes` nor `--force` does |
| `--dry-run` | none | off | `fetch`, `train`, `export`, `run` |
| `--verbose` | none | off | Global, either position. More detail; does not affect warnings, prompts or errors |
| `--quiet` | none | off | Global, either position. Silences progress only — warnings, prompts and errors still print |
| `--yes` | `-y` | off | Global. Answers **Y**, not "accepts the default". Never destructive prompts. Not applicable to `optica setup` |
| `--force` | `-f` | off | Global. Suppresses *safety* prompts. Never destructive ones, never warnings, never hard errors |
| `--version` | none | — | Print the installed version |
| `--set` | none | — | `config` only: `optica config --set epochs 20` |
| `--init` | none | — | `config` only: create `.optica.toml` |
| `--view` | none | — | `config` only: show resolved config with sources |
| `--clear-staging` | none | — | `config` only: list and clear staging, with confirmation |
| `--global` | none | off | `config --set` only: force the write to the global config |
| `--include-extras` | none | — | `setup` only: extra keys to add, comma-separated |
| `--exclude-extras` | none | — | `setup` only: extra keys to remove |
| `--all-extras` | none | off | `setup` only. Conflicts with `--no-extras` |
| `--no-extras` | none | off | `setup` only. Conflicts with `--all-extras` |
| `--upgrade` | none | off | `setup` only, interactive. Surface upgradeable packages |
| `--ci` | none | off | `setup` only: config init — no install, no prompts, no hardware detection |
| `--skip-keys` | none | off | `setup` only: skip the API-key prompts |

Every multi-value flag takes commas, and repeating the flag works too — `-c cat
-c dog,bird` gives you three classes.

---

## Simple API (Tier 3)

The same one-call pipeline, from Python. The contract differs from the CLI on
purpose: **it raises instead of prompting**, and it returns a structured result
rather than printing one.

```python
import optica

result = optica.run(classes=["cat", "dog"], mode="clip")

print(result.train.best_val_accuracy)
print(result.export.export_folder)
print(result.warnings)                 # list[WarningEntry], in invocation order
```

Anything that would be a prompt on the CLI is an exception here — there is no
terminal to ask on. `dry_run=True` returns the same result shape with a `plan`
filled in and nothing written.

---

## Python API (Tier 4)

The steps individually, composable.

```python
import optica

optica.fetch(classes=["cat", "dog"], source="open-datasets", images_per_class=100)
optica.label(folder="./my-images", classes=["cat", "dog"])   # optica[web]
optica.curate()                                              # optica[web]
optica.train(epochs=20, model="efficientnet-large")
optica.export(checkpoint_rank=1)
```

Each returns its own result object — `FetchResult`, `TrainResult`,
`ExportResult` — and each carries `warnings`, `dry_run` and `plan`.

For settings with no keyword argument of their own, pass a config object:

```python
from optica.api import FetchConfig, TrainConfig

optica.fetch(classes=["cat", "dog"], config=FetchConfig(curation_port=9000))
optica.train(config=TrainConfig(optimizer="sgd", learning_rate=0.01))
```

The canonical names are task-namespaced — `optica.classify.run()`,
`optica.classify.train()` — and the flat forms above are aliases for them. Both
ship in V1, and the flat forms will keep working.

---

## Classifier (Tier 5)

Direct control of the model object, for when you want to hold state across
steps.

```python
from optica import Classifier
from optica.api import FetchConfig, TrainConfig, ExportConfig

clf = Classifier(model="efficientnet-large", output="./my-output")
clf.fetch(classes=["cat", "dog"], config=FetchConfig(images_per_class=200))
clf.train(config=TrainConfig(epochs=20, early_stopping=10))
clf.export(config=ExportConfig(checkpoint_rank=1))

clf.status              # empty | data_ready | trained | exported
clf.classes
clf.best_val_accuracy
clf.training_history    # one EpochRecord per completed epoch
clf.checkpoint_path
clf.export_paths
clf.warnings

# Methods return self, so they chain
clf.fetch(classes=["cat", "dog"]).train().export(config=ExportConfig(checkpoint_rank=1))

# Or start from a checkpoint you already have. `checkpoint_path` always names
# the checkpoint's *folder*, never the `.pt` file inside it.
Classifier(checkpoint_path="./checkpoints/checkpoint_val0.983_epoch7").export(
    config=ExportConfig(checkpoint_rank=1)
)
```

`Classifier` methods return `self` rather than a result object, which is why
`clf.warnings` exists: it accumulates across calls, so a programmatic caller can
still branch on a warning.

---

## How it works

```
Input → Preprocess → Train → Evaluate → Export
```

**Three ways in.** `label` (your images, you label them in a browser), `curate`
(Optica fetches, you review in a browser), `clip` (Optica fetches, CLIP filters,
nobody watches). All three converge on the same organized `dataset/` folder, so
everything downstream is identical.

**Training** is two-phase transfer learning over
[timm](https://github.com/huggingface/pytorch-image-models) backbones: a head
warm-up, then selective fine-tuning of the upper layers. Checkpoints are ranked
by validation accuracy and the top three kept. Early stopping is on by default.

**Export** writes a timestamped folder containing `model.pt`, a
`class_names.json`, a `model_info.json` describing the preprocessing the model
expects, and a generated `usage_examples.md` showing how to load it. V1 exports
PyTorch `.pt` only — ONNX and REST export are the next thing after this release.

**Class names are search queries.** Optica checks them before fetching anything
and stops on names that cannot be searched for — `other`, `defective`, `misc`,
`class_a`, bare numbers. It is not a block: it asks you to define the term
concretely (*"defective — what does that look like?"*) and searches for what you
give it. In an unattended run there is nobody to ask, so it raises rather than
fetching images that would be worthless.

---

## Configuration

Highest priority wins:

```
CLI flags  >  ./.optica.toml  >  environment  >  ~/.optica/config.toml  >  defaults
```

- `~/.optica/config.toml` — global, written by `optica setup`. Defaults and API keys.
- `./.optica.toml` — per project, written by `optica config --init`. Commit this one.
- Environment variables are `OPTICA_` plus the key, uppercased: `OPTICA_EPOCHS`,
  `OPTICA_CLIP_THRESHOLD`.
- A `.env` file in the project directory is loaded at the environment tier.

Keys: `default_mode`, `default_source`, `default_model`, `images_per_class`,
`epochs`, `learning_rate`, `optimizer`, `batch_size`, `early_stopping`,
`augmentation`, `train_split`, `val_split`, `test_split`, `max_checkpoints`,
`clip_threshold`, `finetune_ratio`, `max_open_datasets_per_class`,
`curation_port`, `curation_timeout_minutes`, `flickr_api_key`.
`optica config --view` prints all of them with the source of each value.

**API keys.** `FLICKR_API_KEY` keeps its own name — no `OPTICA_` prefix — since
it is a Flickr credential rather than an Optica setting. Open Images needs no
key. `optica config --view` masks it.

**What Optica gitignores, and what it leaves to you.** When Optica *creates*
`checkpoints/` or your `--output` container, it drops a `.gitignore` containing
`*` inside that folder, so large regenerable files never reach a commit by
accident. (A run's training log is kept in `~/.optica/logs/` regardless, so
ignoring the output folder loses no history.) It does this only for folders it
creates itself: a folder that already exists is left exactly as it is, including
any `.gitignore` you put there, and Optica never reads or edits your
project-level or global `.gitignore`. `dataset/` is deliberately not ignored —
it is your curated data, and you may well want it committed.

> **Add `.env` to your `.gitignore` yourself.** Nothing above covers a file at
> your project root, so this one is on you. `.env` is where keys live, which
> makes it the file that most needs to stay out of a commit — the opposite of
> `.optica.toml`, which is meant to be committed. If you created `checkpoints/`
> or an output folder by hand before Optica did, add those too; Optica will not
> retrofit an ignore file into a folder it did not create.

**Run history.** Every training run writes a JSON log to two places: a project
copy under `<output>/logs/`, which follows `--output` and disappears with the
output folder, and `~/.optica/logs/`, which is the durable one. If you want to
know what you ran three weeks ago, `~/.optica/logs/` is where to look.

---

## Exit codes

V1 is built to be scripted, so the exit code is the contract.

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Error |
| `2` | Usage error — a bad flag or a bad value |
| `3` | Declined, or an incomplete step |
| `130` | Interrupted (Ctrl-C) |

A prompt you answer **N** exits `3`, not `130`. `130` means a signal.

---

## Known limitations in V1

- **Search quality is only as good as the class name.** Names go straight to the
  source as search queries, and neither curate mode nor clip mode can rescue a
  bad fetch — one relies on your review, the other on CLIP's. Be specific.
- **Resuming is not lossless.** Choosing *Start fresh* for an interrupted fetch
  deletes that class's staged images, but it does not clear deselections already
  recorded for that class during curation. Since a re-fetch numbers images from
  `0001` again, a deselection can land on whichever new image takes that name,
  which then opens already deselected.
- **One curation session at a time.** Staging lives at a single per-user
  location, so a second curation session cannot run alongside the first.
- **A missing extra is reported before a class-name problem.** If a command
  needs an extra you do not have *and* is given a class name that needs
  defining, you are told about the extra first — on the CLI and from Python
  alike. Install it and run again to see the second problem.
- **Square brackets in class names and paths may display incompletely.** A name
  like `cat [indoor]` can lose the bracketed part in terminal output. Only the
  display is affected; the folders, manifests and exported files on disk always
  carry the full name.
- **`pip freeze` does not capture the torch install.** See the installation note
  above.
- **One export format.** V1 writes PyTorch `.pt`. ONNX and REST export follow.

---

## Platform support

Linux and macOS are the primary targets. Windows is supported and covered by
CI; it is not a primary target, and the filesystem differences it brings
(reserved device names, trailing dots, path length) are handled explicitly
rather than assumed away.

CI runs on Ubuntu, macOS and Windows. The matrix is four legs rather than a full
cross product, so to be precise about what that covers: **each of Python 3.11,
3.12 and 3.13 is tested on at least one operating system**, and the **minimum
declared version of every dependency is tested on one leg**, with the latest
versions on the others. It is not every Python version on every platform. The
PyTorch stack is never installed in CI — tests that need it are marked `slow`
and run locally.

---

## Tech stack

PyTorch · timm · torchvision · scikit-learn · open-clip-torch · FastAPI ·
Typer · Rich · pydantic-settings · httpx · Pillow · Ruff · mypy · pytest

---

## License

Apache-2.0 — see [LICENSE](LICENSE).
