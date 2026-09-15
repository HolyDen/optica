"""Backbones, heads, and which parameters each phase trains.

Implements plan § "Training" → *Training Engine* (the ``load_backbone()`` /
``configure_head()`` split, timm-native heads), *"Last layers" per architecture*
and *Input resolution and normalization*.

**The head stays timm-native.** ``replace_head(model, num_classes=N)`` is
``model.reset_classifier(num_classes=N)``, which produces exactly the parameter
names ``timm.create_model(base_model, num_classes=N)`` builds — measured for all
four backbones (``notes/verified.md``). The exported ``model.pt``'s two-line
reconstruction depends on it. The head's parameters are found through
``get_classifier()``, never by name: efficientnet and mobilenet call it
``classifier``, resnet50 calls it ``fc``.

**Phase 2's groups** are the plan's table as amended on 14 September, as
parameter-name prefixes checked against timm 1.0.29:

=========================  =====================================================
``efficientnet_b0`` / b4   ``blocks.5``, ``blocks.6``, ``conv_head``, ``bn2``
``resnet50``               ``layer4``
``mobilenetv3_large_100``  ``blocks.4``, ``blocks.5``, ``blocks.6`` — and ``conv_head``
=========================  =====================================================

**mobilenet's ``conv_head`` is a decision, not the table.** In
``mobilenetv3_large_100`` the 1x1 ``conv_head`` (1,230,080 parameters, 29% of
the model) sits *after* ``global_pool``, between the last block and the
classifier; ``norm_head`` is an ``Identity``. Read literally, "last 3 blocks"
leaves it frozen through both phases, so Phase 2 would fine-tune the top blocks
through a fixed ImageNet projection the new head never sees adapt. The rule
applied to all four backbones instead is one sentence: *the named blocks, and
every parameterised module after them up to the classifier.* For the
efficientnets that is exactly the amended row (``conv_head`` + ``bn2``), for
resnet50 exactly ``layer4`` (nothing parameterised follows it), and for
mobilenet it adds ``conv_head``. Logged for the amendment session.

**Frozen BatchNorm stays in eval mode.** A frozen BatchNorm put in train mode
still rewrites its running statistics from each batch; on a dataset of a few
dozen images that damages the pretrained features the frozen phase exists to
protect. The plan does not say; :func:`set_train_mode` decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from optica.exceptions import OpticaTrainingError
from optica.utils.mlstack import import_torch_stack, prepare_hub

if TYPE_CHECKING:
    import torch
    from torch import nn

__all__ = [
    "BASE_MODELS",
    "PHASE2_PREFIXES",
    "DataConfig",
    "base_model_for",
    "configure_head",
    "head_parameter_names",
    "load_backbone",
    "phase_parameter_names",
    "replace_head",
    "resolve_data_config",
    "set_phase",
    "set_train_mode",
]

BASE_MODELS: Final[dict[str, str]] = {
    "efficientnet-small": "efficientnet_b0",
    "efficientnet-large": "efficientnet_b4",
    "resnet": "resnet50",
    "resnet-50": "resnet50",
    "mobilenet": "mobilenetv3_large_100",
    "mobilenet-large": "mobilenetv3_large_100",
}
"""``--model`` value to timm name. Two alias pairs, one model each."""

PHASE2_PREFIXES: Final[dict[str, tuple[str, ...]]] = {
    "efficientnet_b0": ("blocks.5.", "blocks.6.", "conv_head.", "bn2."),
    "efficientnet_b4": ("blocks.5.", "blocks.6.", "conv_head.", "bn2."),
    "resnet50": ("layer4.",),
    "mobilenetv3_large_100": ("blocks.4.", "blocks.5.", "blocks.6.", "conv_head."),
}


def base_model_for(model_family: str) -> str:
    """The timm name for a ``--model`` value.

    Raises:
        OpticaTrainingError: For a family no table row covers — unreachable
            through config validation, which checks the same list.
    """
    try:
        return BASE_MODELS[model_family]
    except KeyError:
        raise OpticaTrainingError(
            f"{model_family} is not a known architecture.",
            options=sorted(BASE_MODELS),
        ) from None


def load_backbone(base_model: str, *, pretrained: bool = True) -> nn.Module:
    """Create a timm backbone with its pretrained ImageNet weights.

    Generic across tasks: no head is configured here.

    Raises:
        OpticaTorchError: The torch stack is missing.
        OpticaTrainingError: The weights cannot be downloaded or loaded.
    """
    import_torch_stack()
    import timm

    prepare_hub()
    try:
        model: nn.Module = timm.create_model(base_model, pretrained=pretrained)
    except Exception as exc:  # network, cache, or a corrupt download
        raise OpticaTrainingError(
            f"The pretrained weights for {base_model} could not be loaded.",
            why=f"{type(exc).__name__}: {exc}",
            fix="Check the network connection and free disk space, then run again.",
        ) from exc
    _check_prefixes(model, base_model)
    return model


def _check_prefixes(model: nn.Module, base_model: str) -> None:
    # Layer names change between timm releases (Implementation Note 3). A prefix
    # that matches nothing would silently freeze that group for good.
    names = [name for name, _ in model.named_parameters()]
    missing = [
        prefix
        for prefix in PHASE2_PREFIXES[base_model]
        if not any(name.startswith(prefix) for name in names)
    ]
    if missing:
        raise OpticaTrainingError(
            f"{base_model} in this timm version has no layers named "
            f"{', '.join(p.rstrip('.') for p in missing)}.",
            why="Phase 2 would leave those layers frozen without saying so.",
            fix="Install the timm version Optica was verified against: optica setup",
        )


def replace_head(model: nn.Module, num_classes: int) -> None:
    """Replace the classifier for ``num_classes`` outputs, timm-natively.

    ``num_classes`` is explicit rather than inferred, so a later caller can pass
    ``old + new`` without a signature change.
    """
    model.reset_classifier(num_classes=num_classes)  # type: ignore[operator, unused-ignore]


def configure_head(model: nn.Module, num_classes: int) -> None:
    """The classification task's head: timm's own classifier, replaced."""
    replace_head(model, num_classes=num_classes)


def head_parameter_names(model: nn.Module) -> set[str]:
    """Names of the classifier's parameters, found through ``get_classifier()``."""
    classifier = model.get_classifier()  # type: ignore[operator, unused-ignore]
    head_ids = {id(p) for p in classifier.parameters()}
    return {name for name, p in model.named_parameters() if id(p) in head_ids}


def phase_parameter_names(model: nn.Module, base_model: str, phase: int) -> set[str]:
    """Names of the parameters phase ``phase`` trains.

    Phase 1: the head only. Phase 2: the head and :data:`PHASE2_PREFIXES`.
    """
    head = head_parameter_names(model)
    if phase == 1:
        return head
    if phase != 2:
        raise ValueError(f"phase must be 1 or 2, got {phase}")
    prefixes = PHASE2_PREFIXES[base_model]
    return head | {
        name for name, _ in model.named_parameters() if name.startswith(prefixes)
    }


def set_phase(model: nn.Module, base_model: str, phase: int) -> list[torch.nn.Parameter]:
    """Freeze everything, then unfreeze what ``phase`` trains.

    Returns:
        The trainable parameters, in model order — what the optimizer gets.
    """
    trainable = phase_parameter_names(model, base_model, phase)
    params = []
    for name, parameter in model.named_parameters():
        parameter.requires_grad = name in trainable
        if parameter.requires_grad:
            params.append(parameter)
    return params


def set_train_mode(model: nn.Module) -> None:
    """``model.train()``, with every fully frozen BatchNorm kept in eval mode."""
    import_torch_stack()
    import torch

    model.train()
    for module in model.modules():
        if isinstance(module, torch.nn.modules.batchnorm._BatchNorm):
            own = list(module.parameters(recurse=False))
            if own and not any(p.requires_grad for p in own):
                module.eval()


@dataclass(frozen=True)
class DataConfig:
    """The six timm-resolved preprocessing values.

    All six are carried into ``checkpoint_info``-adjacent metadata and the export,
    because a later timm may resolve the same tag differently.

    Attributes:
        input_size: ``(channels, height, width)``.
        mean: Per-channel normalisation mean.
        std: Per-channel normalisation std.
        interpolation: Resampling name, e.g. ``bicubic``.
        crop_pct: Evaluation resizes to ``input_size / crop_pct`` first.
        crop_mode: ``center`` for all four V1 backbones.
    """

    input_size: tuple[int, int, int]
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    interpolation: str
    crop_pct: float
    crop_mode: str

    def as_json(self) -> dict[str, Any]:
        """JSON primitives — ``input_size`` as ``[height, width]``, as exported."""
        return {
            "input_size": [self.input_size[1], self.input_size[2]],
            "mean": list(self.mean),
            "std": list(self.std),
            "interpolation": self.interpolation,
            "crop_pct": self.crop_pct,
            "crop_mode": self.crop_mode,
        }


def resolve_data_config(model: nn.Module) -> DataConfig:
    """``timm.data.resolve_model_data_config(model)``, typed.

    Returns the **training** values — ``efficientnet_b4`` resolves to 320, not
    its 384 test size, which V1 deliberately does not use.
    """
    import_torch_stack()
    import timm

    resolve: Any = timm.data.resolve_model_data_config  # type: ignore[attr-defined, unused-ignore]
    cfg = resolve(model)
    size = tuple(int(v) for v in cfg["input_size"])
    return DataConfig(
        input_size=(size[0], size[1], size[2]),
        mean=(float(cfg["mean"][0]), float(cfg["mean"][1]), float(cfg["mean"][2])),
        std=(float(cfg["std"][0]), float(cfg["std"][1]), float(cfg["std"][2])),
        interpolation=str(cfg["interpolation"]),
        crop_pct=float(cfg["crop_pct"]),
        crop_mode=str(cfg["crop_mode"]),
    )
