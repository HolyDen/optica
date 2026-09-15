"""PyTorch ``.pt`` export: ``model.pt`` and ``usage_examples.md``.

Implements plan § "Export" → *Artifact contents*.

**``model.pt`` is one dict — never a pickled module.** ``state_dict``,
``base_model``, ``num_classes``, ``classes`` and all six preprocessing values;
tensors and JSON primitives only, so it loads under ``torch.load``'s
``weights_only=True`` default. Reconstruction is two lines —
``timm.create_model(base_model, num_classes=…)`` then ``load_state_dict`` — valid
because the training head is timm-native.

**Both claims are checked on every export**, not assumed: the written file is
re-read with ``weights_only=True``, and the model is rebuilt with those two lines
(``pretrained=False``, so nothing downloads) and loaded with ``strict=True``. A
file that fails either check is never renamed into place (``notes/build-log.md``).

**``usage_examples.md`` is generated from ``model_info.json``** so it cannot drift
from the artifact beside it: load and reconstruct, preprocess with the six values,
run inference, map the index through ``class_names.json``. :func:`usage_examples`
is pure and runs in CI.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Final

from optica.exceptions import OpticaExportError
from optica.training import checkpoints as ckpt
from optica.utils.mlstack import import_torch_stack

__all__ = ["MODEL_FILE", "USAGE_FILE", "export", "model_payload_keys", "usage_examples"]

MODEL_FILE: Final = "model.pt"
USAGE_FILE: Final = "usage_examples.md"
_PREPROCESSING: Final = (
    "input_size",
    "mean",
    "std",
    "interpolation",
    "crop_pct",
    "crop_mode",
)


def model_payload_keys() -> tuple[str, ...]:
    """The keys of ``model.pt``'s dict, in the plan's order."""
    return ("state_dict", "base_model", "num_classes", "classes", *_PREPROCESSING)


def export(folder: Path, checkpoint_folder: Path, info: dict[str, Any]) -> list[str]:
    """Write ``model.pt`` and ``usage_examples.md`` into ``folder``.

    Args:
        folder: The export's ``.partial`` folder.
        checkpoint_folder: The checkpoint being exported.
        info: Its ``model_info.json``.

    Returns:
        The file names written.

    Raises:
        OpticaTorchError: The torch stack is missing.
        OpticaExportError: The checkpoint cannot be read, or the written model
            does not reload and reconstruct.
    """
    import_torch_stack()
    import timm
    import torch

    try:
        state_dict = ckpt.load_weights(checkpoint_folder)["state_dict"]
    except Exception as exc:
        raise OpticaExportError(
            f"The weights in {checkpoint_folder} could not be read.",
            why=str(exc),
            fix="Export a different rank, or train again.",
        ) from exc
    payload: dict[str, Any] = {
        "state_dict": state_dict,
        "base_model": info["base_model"],
        "num_classes": info["num_classes"],
        "classes": list(info["classes"]),
        **{key: info[key] for key in _PREPROCESSING},
    }
    path = folder / MODEL_FILE
    torch.save(payload, path)

    try:
        reloaded = torch.load(path, map_location="cpu", weights_only=True)
        model = timm.create_model(
            reloaded["base_model"], pretrained=False, num_classes=reloaded["num_classes"]
        )
        model.load_state_dict(reloaded["state_dict"], strict=True)
    except Exception as exc:
        raise OpticaExportError(
            f"The exported {MODEL_FILE} does not reconstruct.",
            why=f"{type(exc).__name__}: {exc}",
            fix="This is a bug in Optica; the checkpoint itself is unchanged.",
        ) from exc

    (folder / USAGE_FILE).write_text(usage_examples(info), encoding="utf-8")
    return [MODEL_FILE, USAGE_FILE]


_INTERPOLATION: Final[dict[str, str]] = {
    "bicubic": "BICUBIC",
    "bilinear": "BILINEAR",
    "nearest": "NEAREST",
    "lanczos": "LANCZOS",
    "box": "BOX",
    "hamming": "HAMMING",
}


def usage_examples(info: dict[str, Any]) -> str:
    """``usage_examples.md``, generated from ``model_info.json``.

    Raises:
        OpticaExportError: A ``crop_mode`` other than ``center`` — all four V1
            backbones resolve to ``center``, and an example for another mode
            would teach a transform nothing here has checked.
    """
    if info["crop_mode"] != "center":
        raise OpticaExportError(
            f"crop_mode {info['crop_mode']!r} has no generated usage example.",
            why="V1's backbones all resolve to 'center'.",
        )
    height, width = info["input_size"]
    resize = math.floor(height / info["crop_pct"])
    mode = _INTERPOLATION.get(info["interpolation"], info["interpolation"].upper())
    classes = ", ".join(info["classes"])
    test = info.get("test_accuracy")
    test_text = f"{test:.3f}" if isinstance(test, int | float) else "not evaluated"
    return f"""# Using `{info["export_folder"]}`

`{info["model_family"]}` (`{info["base_model"]}`), {info["num_classes"]} \
classes: {classes}.
Checkpoint rank {info["exported_rank"]} of {info["exported_rank_of"]} — val_accuracy \
{info["val_accuracy"]:.3f}, test_accuracy {test_text}.

Needs `torch`, `torchvision`, `timm` and `Pillow`. Run the snippets from this folder.

## 1. Load `model.pt` and reconstruct the model

```python
import timm
import torch

checkpoint = torch.load("{MODEL_FILE}", map_location="cpu", weights_only=True)
model = timm.create_model(checkpoint["base_model"], num_classes=checkpoint["num_classes"])
model.load_state_dict(checkpoint["state_dict"])
model.eval()
```

## 2. Preprocess an image

The six values this model was trained with, from `model_info.json`: resize the
shorter side to `floor({height} / {info["crop_pct"]})` = {resize} with
{info["interpolation"]} resampling, centre-crop to {height}x{width}, then normalise.

```python
from PIL import Image
from torchvision import transforms
from torchvision.transforms import InterpolationMode

preprocess = transforms.Compose([
    transforms.Resize({resize}, interpolation=InterpolationMode.{mode}),
    transforms.CenterCrop(({height}, {width})),
    transforms.ToTensor(),
    transforms.Normalize(mean={list(info["mean"])}, std={list(info["std"])}),
])

image = Image.open("your_image.jpg").convert("RGB")
batch = preprocess(image).unsqueeze(0)
```

## 3. Run inference

```python
with torch.no_grad():
    probabilities = model(batch).softmax(dim=1)[0]
```

## 4. Map the output index to a class name

```python
import json

with open("class_names.json", encoding="utf-8") as handle:
    class_names = json.load(handle)

index = int(probabilities.argmax())
print(class_names[index], float(probabilities[index]))
```
"""
