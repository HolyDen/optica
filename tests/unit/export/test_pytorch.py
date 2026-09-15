"""PyTorch ``.pt`` export.

Covers plan § "Export" → *Artifact contents*: ``model.pt`` is one dict of tensors
and JSON primitives with the plan's keys, loadable under ``weights_only=True``,
reconstructed in two lines; ``usage_examples.md`` is generated from
``model_info.json`` and teaches the evaluation transform with all six values.

The generator is pure and runs in CI. The export is ``slow``: a checkpoint is
built here from a ``pretrained=False`` model, and the generated usage example is
**executed** against the export and must predict what training's own evaluation
transform predicts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from optica.exceptions import OpticaExportError
from optica.export import pytorch


def _info(**overrides: Any) -> dict[str, Any]:
    info = {
        "export_folder": "efficientnet-small_2cls_20260915_120000",
        "model_family": "efficientnet-small",
        "base_model": "efficientnet_b0",
        "num_classes": 2,
        "classes": ["cat", "dog"],
        "exported_rank": 1,
        "exported_rank_of": 3,
        "val_accuracy": 0.9,
        "test_accuracy": None,
        "input_size": [224, 224],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "interpolation": "bicubic",
        "crop_pct": 0.875,
        "crop_mode": "center",
    }
    info.update(overrides)
    return info


class TestUsageExamples:
    def test_the_four_sections_in_order(self):
        text = pytorch.usage_examples(_info())
        headings = re.findall(r"^## (\d)\. (.+)$", text, flags=re.M)
        assert [h[0] for h in headings] == ["1", "2", "3", "4"]
        assert "reconstruct" in headings[0][1]
        assert "Preprocess" in headings[1][1]
        assert "inference" in headings[2][1]
        assert "class name" in headings[3][1]

    @pytest.mark.parametrize(
        ("size", "crop_pct", "resize"),
        [(224, 0.875, 256), (224, 0.95, 235), (320, 0.875, 365)],
    )
    def test_all_six_values_reach_the_transform(self, size, crop_pct, resize):
        text = pytorch.usage_examples(
            _info(input_size=[size, size], crop_pct=crop_pct, mean=[0.5, 0.4, 0.3])
        )
        assert (
            f"transforms.Resize({resize}, interpolation=InterpolationMode.BICUBIC)"
            in text
        )
        assert f"transforms.CenterCrop(({size}, {size}))" in text
        assert "mean=[0.5, 0.4, 0.3]" in text
        assert "std=[0.229, 0.224, 0.225]" in text

    def test_the_reconstruction_is_the_plans_two_lines(self):
        text = pytorch.usage_examples(_info())
        assert (
            'model = timm.create_model(checkpoint["base_model"], '
            'num_classes=checkpoint["num_classes"])' in text
        )
        assert 'model.load_state_dict(checkpoint["state_dict"])' in text
        assert "weights_only=True" in text

    def test_a_crop_mode_other_than_center_is_refused(self):
        with pytest.raises(OpticaExportError):
            pytorch.usage_examples(_info(crop_mode="squash"))

    def test_model_pt_keys_are_the_plans(self):
        assert pytorch.model_payload_keys() == (
            "state_dict", "base_model", "num_classes", "classes", "input_size",
            "mean", "std", "interpolation", "crop_pct", "crop_mode",
        )  # fmt: skip


def _checkpoint(tmp_path: Path, timm_model, base: str = "efficientnet_b0") -> Path:
    import torch

    from optica.training import checkpoints as ckpt
    from optica.training.models import configure_head

    torch.manual_seed(0)
    model = timm_model(base)
    configure_head(model, num_classes=2)
    folder = tmp_path / "checkpoints" / "checkpoint_val0.900_epoch1"
    ckpt.save_weights(folder, model, None)
    return folder


@pytest.mark.slow
class TestExport:
    def test_model_pt_loads_weights_only_and_reconstructs(self, tmp_path, timm_model):
        import timm
        import torch

        folder = tmp_path / "export"
        folder.mkdir()
        files = pytorch.export(folder, _checkpoint(tmp_path, timm_model), _info())
        assert files == ["model.pt", "usage_examples.md"]
        payload = torch.load(folder / "model.pt", map_location="cpu", weights_only=True)
        assert tuple(payload) == pytorch.model_payload_keys()
        assert payload["classes"] == ["cat", "dog"] and payload["crop_pct"] == 0.875
        # Only tensors and JSON primitives besides the state dict.
        for key in pytorch.model_payload_keys()[1:]:
            assert isinstance(payload[key], str | int | float | list)
        model = timm.create_model(
            payload["base_model"], num_classes=payload["num_classes"]
        )
        model.load_state_dict(payload["state_dict"])  # the plan's two lines

    def test_a_state_dict_that_does_not_reconstruct_is_never_exported(
        self, tmp_path, timm_model, monkeypatch
    ):
        from optica.training import checkpoints as ckpt

        source = _checkpoint(tmp_path, timm_model)
        real = ckpt.load_weights

        def renamed_head(folder, **kwargs):
            payload = real(folder, **kwargs)
            state = payload["state_dict"]
            state["head.weight"] = state.pop("classifier.weight")
            return payload

        monkeypatch.setattr(ckpt, "load_weights", renamed_head)
        folder = tmp_path / "export"
        folder.mkdir()
        with pytest.raises(OpticaExportError, match="does not reconstruct"):
            pytorch.export(folder, source, _info())

    def test_the_generated_example_runs_and_matches_training_exactly(
        self, tmp_path, timm_model, monkeypatch
    ):
        """Execute the generated snippets against the export.

        Two exact comparisons, each independent of how sensitive a randomly
        initialised model is (its logits barely move with the input — measured,
        notes/build-log.md): the example's preprocessed batch must equal
        training's evaluation transform pixel for pixel, and the model it
        reconstructs must carry exactly the checkpoint's weights.
        """
        import torch
        from PIL import Image
        from torchvision import transforms as tv
        from torchvision.transforms import InterpolationMode

        from optica.training import checkpoints as ckpt
        from optica.training.models import configure_head, resolve_data_config
        from optica.training.transforms import build_transforms

        folder = tmp_path / "export"
        folder.mkdir()
        source = _checkpoint(tmp_path, timm_model)
        pytorch.export(folder, source, _info())
        (folder / "class_names.json").write_text('["cat", "dog"]', encoding="utf-8")
        pixels = torch.rand(300, 420, 3, generator=torch.Generator().manual_seed(4)) * 255
        image_path = folder / "your_image.jpg"
        Image.fromarray(pixels.byte().numpy()).save(image_path)

        text = (folder / "usage_examples.md").read_text(encoding="utf-8")
        code = "\n".join(re.findall(r"```python\n(.*?)```", text, re.S))
        monkeypatch.chdir(folder)
        namespace: dict[str, Any] = {}
        exec(compile(code, "usage_examples.md", "exec"), namespace)

        # 1. Preprocessing: identical tensors, not merely close.
        reference = timm_model("efficientnet_b0")
        configure_head(reference, num_classes=2)
        config = resolve_data_config(reference)
        _, evaluation = build_transforms(config, augmentation=True)
        image = Image.open(image_path).convert("RGB")
        expected_batch = evaluation(image).unsqueeze(0)
        assert torch.equal(namespace["batch"], expected_batch)
        # Control: one resampling change gives a different tensor, so the
        # equality above can fail.
        bilinear = tv.Compose(
            [
                tv.Resize(256, interpolation=InterpolationMode.BILINEAR),
                tv.CenterCrop(224),
                tv.ToTensor(),
                tv.Normalize(config.mean, config.std),
            ]
        )
        assert not torch.equal(bilinear(image).unsqueeze(0), expected_batch)

        # 2. Reconstruction: exactly the checkpoint's weights.
        stored = ckpt.load_weights(source)["state_dict"]
        rebuilt = namespace["model"].state_dict()
        assert list(rebuilt) == list(stored)
        assert all(torch.equal(rebuilt[k], stored[k]) for k in stored)

        # 3. Inference and the index mapping, consistent with the above.
        with torch.no_grad():
            expected = namespace["model"](expected_batch).softmax(dim=1)[0]
        assert torch.equal(namespace["probabilities"], expected)
        assert namespace["class_names"][namespace["index"]] in ("cat", "dog")
