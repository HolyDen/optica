# Optica

> Transfer learning for everyone. Build an image classifier in one command.

![PyPI](https://img.shields.io/pypi/v/optica)
![Python](https://img.shields.io/pypi/pyversions/optica)
![License](https://img.shields.io/badge/license-Apache--2.0-blue)

Optica is a Python package that handles the full image classification pipeline — from sourcing training images to exporting a deployable model. No ML expertise required for the basics; full programmatic control available when you need it.

> **Status:** v0.1.1 is in active development. The API and CLI surface described here reflect the planned V1 feature set.

---

## Installation

```bash
pip install optica          # lightweight core
optica setup                # installs PyTorch with hardware detection (CPU/CUDA)
```

> **Why two steps?** PyTorch requires different installation sources depending on your hardware. `optica setup` detects your GPU and installs the correct version automatically — something `pip` alone cannot do.

**Optional extras:**

| Extra | Installs | Enables |
|---|---|---|
| `optica[clip]` | `open-clip-torch` | CLIP auto-filtering (`--mode clip`) |
| `optica[onnx]` | `onnx`, `onnxruntime` | ONNX export (`--format onnx`) |
| `optica[server]` | `FastAPI`, `uvicorn` | Browser curation, REST export |
| `optica[all]` | everything above | Full feature set |

```bash
pip install optica[all]     # recommended for full feature set
```

---

## Quickstart

```bash
optica run --classes "golden retriever" "husky" --mode clip --format pt
```

That's it. Optica fetches images, filters them with CLIP, trains a classifier, and exports a PyTorch model.

---

## Usage

Optica supports three tiers — pick the one that fits your workflow.

### Tier 1 — CLI

```bash
# Fetch images, curate in browser, train, export
optica run --classes "cat" "dog"

# Skip curation — let CLIP filter automatically
optica run --classes "cat" "dog" --mode clip

# Use your own images
optica run --classes "cat" "dog" --mode manual --dataset ./my-images

# Step by step, with full control
optica fetch --classes "cat" "dog" --count 100 --mode clip
optica train --epochs 20 --model efficientnet-large --batch-size 16
optica export --format onnx --name "cat-dog-classifier"
```

### Tier 2 — Simple API

```python
import optica

optica.fetch(classes=["cat", "dog"], count=100, mode="clip")
optica.train(epochs=20, model="efficientnet-large")
optica.export(format="onnx", name="cat-dog-classifier")

# Or run the full pipeline in one call
optica.run(classes=["cat", "dog"], mode="clip", format="pt")
```

### Tier 3 — Classifier class

```python
from optica import Classifier
from optica.api import FetchConfig, TrainConfig, ExportConfig

clf = Classifier(model="efficientnet-large", output="./my-output", verbose=True)
clf.fetch(classes=["cat", "dog"], config=FetchConfig(source="bing", images_per_class=200))
clf.train(config=TrainConfig(epochs=20, early_stopping=10, batch_size=32, train_split=0.70))
clf.export(config=ExportConfig(formats=["pt", "onnx"], checkpoint=1))

# Properties available anytime
print(clf.status)            # idle | fetched | trained | exported
print(clf.best_val_accuracy)
print(clf.training_history)  # per-epoch metrics
print(clf.export_paths)

# Chainable — all methods return self
clf.fetch(...).train(...).export(...)

# Skip steps with existing data
clf = Classifier(checkpoint_path="./existing.pt")
clf.export(config=ExportConfig(formats=["onnx"]))
```

---

## Export formats

| Format | Output | Use case |
|---|---|---|
| `pt` | `model.pt` | PyTorch inference, further fine-tuning |
| `onnx` | `model.onnx` | Cross-platform deployment, ONNX Runtime |
| `rest` | FastAPI folder with `model.pt` + `app.py` | Production REST API, ready to deploy |

Multiple formats in one command:

```bash
optica export --format pt onnx rest
```

---

## How it works

Optica is built around a single pipeline that all three input modes feed into:

```
Input → Preprocess → Train → Evaluate → Export
```

**Input modes:**
- `manual` — bring your own images
- `curate` — Optica fetches images, you review them in a browser UI
- `clip` — Optica fetches and filters automatically using CLIP similarity scoring

**Training** uses two-phase transfer learning via [timm](https://github.com/huggingface/pytorch-image-models): feature extraction first, then selective fine-tuning. Supports checkpointing, early stopping, and resume on interruption.

**Export** produces a named, timestamped output folder with your model file, class labels, and (for REST) a ready-to-deploy `app.py`.

---

## Tech stack

PyTorch · timm · torchvision · scikit-learn · open-clip-torch · FastAPI · Typer · Ruff · mypy · pytest

---

## License

Apache-2.0 — see [LICENSE](LICENSE).