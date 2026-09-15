"""Backbones, heads and phase parameter groups.

Covers plan § "Training" → *Training Engine* (``load_backbone()`` /
``configure_head()``, a timm-native head whose names match
``timm.create_model(base_model, num_classes=N)``), *"Last layers" per
architecture* as amended 14 September (efficientnets include ``bn2``; mobilenet
"last 3 blocks"), and *Input resolution and normalization* (all six values,
per backbone).

Expected values are ``notes/verified.md`` § task 4 (timm 1.0.29) plus this
pass's probe of mobilenet's post-pool ``conv_head`` — transcribed, not
re-derived. Every model is built with ``pretrained=False``.
"""

from __future__ import annotations

import pytest

from optica.exceptions import OpticaTrainingError
from optica.training import models

pytestmark = pytest.mark.slow

ALL = ["efficientnet_b0", "efficientnet_b4", "resnet50", "mobilenetv3_large_100"]


class TestFamilies:
    @pytest.mark.parametrize(
        ("family", "base"),
        [
            ("efficientnet-small", "efficientnet_b0"),
            ("efficientnet-large", "efficientnet_b4"),
            ("resnet", "resnet50"),
            ("resnet-50", "resnet50"),
            ("mobilenet", "mobilenetv3_large_100"),
            ("mobilenet-large", "mobilenetv3_large_100"),
        ],
    )
    def test_each_flag_value_names_its_timm_model(self, family, base):
        assert models.base_model_for(family) == base

    def test_the_families_match_the_config_domain(self):
        from optica.config.defaults import MODELS

        assert set(models.BASE_MODELS) == set(MODELS)

    def test_an_unknown_family_is_a_training_error(self):
        with pytest.raises(OpticaTrainingError):
            models.base_model_for("vit")


class TestHead:
    @pytest.mark.parametrize("name", ALL)
    def test_replace_head_matches_create_model_names_and_shapes(self, name, timm_model):
        model = timm_model(name)
        models.configure_head(model, num_classes=3)
        reference = timm_model(name, num_classes=3).state_dict()
        state = model.state_dict()
        assert list(state) == list(reference)
        assert all(state[k].shape == reference[k].shape for k in reference)

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("efficientnet_b0", {"classifier.weight", "classifier.bias"}),
            ("resnet50", {"fc.weight", "fc.bias"}),
            ("mobilenetv3_large_100", {"classifier.weight", "classifier.bias"}),
        ],
    )
    def test_the_head_is_found_whatever_it_is_called(self, name, expected, timm_model):
        model = timm_model(name)
        models.configure_head(model, num_classes=2)
        assert models.head_parameter_names(model) == expected


def _count(model, names: set[str]) -> int:
    return sum(p.numel() for n, p in model.named_parameters() if n in names)


class TestPhaseGroups:
    # Head params for 3 classes: efficientnet_b0/mobilenet 1280*3+3 = 3,843;
    # b4 1792*3+3 = 5,379; resnet50 2048*3+3 = 6,147 (verified.md task 4).
    @pytest.mark.parametrize(
        ("name", "phase2_body"),
        [
            # blocks.5 + blocks.6 + conv_head + bn2
            ("efficientnet_b0", 2_026_348 + 717_232 + 409_600 + 2_560),
            ("efficientnet_b4", 8_636_228 + 4_470_004 + 802_816 + 3_584),
            # layer4
            ("resnet50", 14_964_736),
            # blocks.4 + blocks.5 + blocks.6 + conv_head (the pass-4 decision)
            ("mobilenetv3_large_100", 600_544 + 2_023_944 + 155_520 + 1_230_080),
        ],
    )
    def test_phase2_trains_the_groups_and_the_head(self, name, phase2_body, timm_model):
        model = timm_model(name)
        models.configure_head(model, num_classes=3)
        head = models.phase_parameter_names(model, name, 1)
        phase2 = models.phase_parameter_names(model, name, 2)
        assert head <= phase2
        assert _count(model, phase2 - head) == phase2_body

    @pytest.mark.parametrize(
        ("name", "head"), [("efficientnet_b0", 3_843), ("resnet50", 6_147)]
    )
    def test_phase1_trains_the_head_only(self, name, head, timm_model):
        model = timm_model(name)
        models.configure_head(model, num_classes=3)
        params = models.set_phase(model, name, 1)
        assert sum(p.numel() for p in params) == head
        frozen = [n for n, p in model.named_parameters() if not p.requires_grad]
        assert len(frozen) == len(list(model.parameters())) - 2

    def test_mobilenet_phase2_includes_conv_head_and_not_blocks_3(self, timm_model):
        name = "mobilenetv3_large_100"
        model = timm_model(name)
        models.configure_head(model, num_classes=2)
        phase2 = models.phase_parameter_names(model, name, 2)
        assert {"conv_head.weight", "conv_head.bias"} <= phase2
        assert not any(n.startswith("blocks.3.") for n in phase2)

    def test_efficientnet_phase2_includes_bn2(self, timm_model):
        model = timm_model("efficientnet_b0")
        models.configure_head(model, num_classes=2)
        assert {"bn2.weight", "bn2.bias"} <= models.phase_parameter_names(
            model, "efficientnet_b0", 2
        )

    def test_a_prefix_that_matches_nothing_is_refused(self, timm_model, monkeypatch):
        model = timm_model("resnet50")
        monkeypatch.setitem(models.PHASE2_PREFIXES, "resnet50", ("layer4.", "layer9."))
        with pytest.raises(OpticaTrainingError, match="layer9"):
            models._check_prefixes(model, "resnet50")

    def test_every_prefix_matches_in_the_installed_timm(self, timm_model):
        for name in ALL:
            models._check_prefixes(timm_model(name), name)


class TestFrozenBatchNorm:
    def test_frozen_batchnorm_stays_in_eval_mode_and_trainable_ones_train(
        self, timm_model
    ):
        import torch

        name = "efficientnet_b0"
        model = timm_model(name)
        models.configure_head(model, num_classes=2)
        models.set_phase(model, name, 2)
        models.set_train_mode(model)
        norms = {
            n: m
            for n, m in model.named_modules()
            if isinstance(m, torch.nn.modules.batchnorm._BatchNorm)
        }
        assert norms["bn2"].training  # unfrozen in Phase 2
        assert norms["blocks.6.0.bn3"].training
        assert not norms["bn1"].training  # stem: frozen in both phases
        assert not norms["blocks.4.0.bn1"].training

    def test_running_statistics_of_a_frozen_batchnorm_do_not_move(self, timm_model):
        import torch

        name = "resnet50"
        model = timm_model(name)
        models.configure_head(model, num_classes=2)
        models.set_phase(model, name, 1)
        models.set_train_mode(model)
        before = model.bn1.running_mean.clone()
        model(torch.randn(2, 3, 64, 64))
        assert torch.equal(model.bn1.running_mean, before)


class TestDataConfig:
    @pytest.mark.parametrize(
        ("name", "size", "crop_pct"),
        [
            ("efficientnet_b0", 224, 0.875),
            ("efficientnet_b4", 320, 0.875),
            ("resnet50", 224, 0.95),
            ("mobilenetv3_large_100", 224, 0.875),
        ],
    )
    def test_the_six_values_per_backbone(self, name, size, crop_pct, timm_model):
        config = models.resolve_data_config(timm_model(name))
        assert config.input_size == (3, size, size)
        assert config.crop_pct == crop_pct
        assert config.interpolation == "bicubic"
        assert config.crop_mode == "center"
        assert config.mean == (0.485, 0.456, 0.406)
        assert config.std == (0.229, 0.224, 0.225)
        assert config.as_json()["input_size"] == [size, size]
