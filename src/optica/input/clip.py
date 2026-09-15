"""The CLIP Adapter: image-text scoring that replaces human curation.

Implements plan § "Input & Acquisition" → *CLIP Adapter (clip mode)* and the
grouped path of *Undefinable classes in auto modes* ("each image is scored
against all sub-terms and keeps its original class label").

**Scoring.** ``ViT-B-32`` with ``openai`` weights, hardcoded. An image is scored
against ``"a photo of a {class}"``, the class name lowercased with ``_`` and
``-`` read as spaces. The score is the **cosine similarity of the L2-normalised
image and text embeddings** — never ``logits_per_image``, which open-clip scales
by ``logit_scale`` (≈100) and which would put every value far outside the 0.0 to
1.0 range the ``clip_threshold`` bands assume. With several prompts (a grouped
class's sub-terms) an image's score is its best match.

**Survivors.** An image passes when its score is at or above the threshold —
the plan discards "whatever scores below". Clip mode fetches
``images_per_class * 2`` and keeps up to ``images_per_class`` of what passes;
which ones, the plan does not say, and the highest-scoring are kept
(``notes/build-log.md``).

**Weights.** open-clip-torch resolves ``openai`` for ``ViT-B-32`` to
``open_clip_model.safetensors`` on the Hugging Face Hub (``huggingface_hub`` is
one of its hard dependencies, so the Hub route is always the one taken), and
that route checks nothing on a cached load. The plan requires cached weights to
be verified on every load, so this module fetches the same file itself, checks
its size and SHA-256 against :data:`PINNED_WEIGHTS` (recorded in
``notes/verified.md``), deletes and re-downloads a bad copy once, and only then
lets open-clip build the model from the cache it has just verified.

**QuickGELU.** The ``openai`` weights were trained with QuickGELU, and
open-clip's ``ViT-B-32`` config uses standard GELU. Given the tag, open-clip
3.3.0 *warns* about the mismatch and builds the GELU model anyway, so the plan's
call is made with ``force_quick_gelu=True`` (:data:`MODEL_KWARGS`). The model,
the weights and the template are unchanged; this is what loads those weights
into the architecture they belong to.

**Nothing here imports torch or open_clip at module level.** The pure half —
prompts, over-fetch arithmetic, survivor selection, weights verification — is
tested in CI; the half that needs the extra is imported lazily and raises
:class:`~optica.exceptions.OpticaCLIPError` when it is missing.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from optica.exceptions import OpticaCLIPError, OpticaCLIPLoadError
from optica.input.classes import ResolvedClass

if TYPE_CHECKING:
    import torch

__all__ = [
    "CLIP_MODEL",
    "CLIP_PRETRAINED",
    "MODEL_KWARGS",
    "OVERFETCH_FACTOR",
    "PINNED_WEIGHTS",
    "PROMPT_TEMPLATE",
    "WEIGHTS_FILENAME",
    "ClipFilterReport",
    "ClipScorer",
    "ImageScorer",
    "PinnedFile",
    "ensure_weights",
    "load_clip",
    "overfetch",
    "prompt_for",
    "select_device",
    "select_survivors",
    "sha256_of",
    "weights_problem",
]

CLIP_MODEL: Final = "ViT-B-32"
CLIP_PRETRAINED: Final = "openai"
PROMPT_TEMPLATE: Final = "a photo of a {}"
OVERFETCH_FACTOR: Final = 2
"""Hardcoded, not a config key: tuning it needs the threshold's score
distribution."""

MODEL_KWARGS: Final[dict[str, Any]] = {"force_quick_gelu": True}
"""Passed to ``create_model_and_transforms`` beside the plan's two arguments."""

WEIGHTS_FILENAME: Final = "open_clip_model.safetensors"
_SCORE_BATCH: Final = 32
_HASH_CHUNK: Final = 8 << 20


@dataclass(frozen=True)
class PinnedFile:
    """A file whose exact bytes are known in advance.

    Attributes:
        size: Size in bytes.
        sha256: Lowercase hex digest.
    """

    size: int
    sha256: str


PINNED_WEIGHTS: Final[dict[str, PinnedFile]] = {
    # Hugging Face repo `timm/vit_base_patch32_clip_224.openai`, revision
    # a6f597a30f7b82c51704746581f9a4e41421e878 — notes/verified.md, pass 4.
    WEIGHTS_FILENAME: PinnedFile(
        605_143_284,
        "e6d1bd7789aa45192b3bf90570a789b478bae1b74ebcce7eddd908e83a2b7c31",
    ),
}


# ------------------------------------------------------------------ prompts


def prompt_for(name: str) -> str:
    """The text an image is scored against for class or sub-term ``name``.

    ``golden_retriever`` → ``a photo of a golden retriever``. Underscores and
    hyphens become spaces and the name is lowercased; nothing else changes.
    """
    return PROMPT_TEMPLATE.format(name.replace("_", " ").replace("-", " ").lower())


def overfetch(cls: ResolvedClass) -> ResolvedClass:
    """The class as clip mode fetches it: ``OVERFETCH_FACTOR`` times the target.

    One bounded over-fetch pass, never a loop. For a grouped class the factor
    applies per sub-term, so the group's total doubles too.
    """
    return replace(
        cls, queries=list(cls.queries), per_query=cls.per_query * OVERFETCH_FACTOR
    )


# ---------------------------------------------------------------- survivors


@dataclass
class ClipFilterReport:
    """What CLIP filtering did to one class. Reported per class, never silently.

    Attributes:
        name: The class.
        target: Images the class aims to keep — ``None`` where every passing
            image is kept (the grouped path under curate, where a person
            selects afterwards).
        threshold: The ``clip_threshold`` applied.
        candidates: Images scored.
        passed: Images at or above the threshold.
        kept: Images kept — ``passed`` capped at ``target``.
        unreadable: Images that could not be opened for scoring; not kept.
        kept_paths: The kept images, best score first.
        rejected_paths: Every image not kept.
    """

    name: str
    target: int | None
    threshold: float
    candidates: int = 0
    passed: int = 0
    kept: int = 0
    unreadable: int = 0
    kept_paths: list[Path] = field(default_factory=list)
    rejected_paths: list[Path] = field(default_factory=list)

    @property
    def below_threshold(self) -> int:
        """Images scored below the threshold, or unreadable."""
        return self.candidates - self.passed

    @property
    def shortfall(self) -> int:
        """How far below target the class finished. Not an error."""
        return 0 if self.target is None else max(0, self.target - self.kept)


def select_survivors(
    name: str,
    scored: Sequence[tuple[Path, float | None]],
    threshold: float,
    keep: int | None,
) -> ClipFilterReport:
    """Apply the threshold and the keep cap to one class's scores.

    An image passes at ``score >= threshold``. Passing images are ranked best
    first — ties by path, so the result is deterministic — and the first
    ``keep`` are kept; ``keep=None`` keeps every one. An unreadable image
    (score ``None``) never passes.
    """
    report = ClipFilterReport(name, keep, threshold, candidates=len(scored))
    passing: list[tuple[float, Path]] = []
    for path, score in scored:
        if score is None:
            report.unreadable += 1
            report.rejected_paths.append(path)
        elif score >= threshold:
            passing.append((score, path))
        else:
            report.rejected_paths.append(path)
    passing.sort(key=lambda item: (-item[0], str(item[1])))
    report.passed = len(passing)
    cut = len(passing) if keep is None else keep
    report.kept_paths = [path for _, path in passing[:cut]]
    report.rejected_paths.extend(path for _, path in passing[cut:])
    report.kept = len(report.kept_paths)
    return report


# ------------------------------------------------------------------ weights


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def weights_problem(path: Path, pinned: PinnedFile) -> str | None:
    """Why the cached file at ``path`` is not the pinned one, or None if it is.

    Size first — a partial download is caught without hashing 600MB.
    """
    if not path.is_file():
        return "is missing"
    size = path.stat().st_size
    if size != pinned.size:
        return f"is {size} bytes, expected {pinned.size}"
    if sha256_of(path) != pinned.sha256:
        return "does not match its SHA-256 checksum"
    return None


def _remove_cached(path: Path) -> None:
    # A symlinked Hub cache points at a blob; remove both, so the next download
    # cannot find a stale half. Without symlinks (Windows by default) the
    # snapshot entry is the file itself.
    target = path.resolve() if path.is_symlink() else None
    path.unlink(missing_ok=True)
    if target is not None:
        target.unlink(missing_ok=True)


def ensure_weights(
    download: Callable[[bool], Path],
    pinned: PinnedFile,
    *,
    report: Callable[[str], None],
) -> Path:
    """Return a verified cached weights file, repairing a bad one once.

    Args:
        download: Returns the cached file's path, downloading it if absent;
            called with ``True`` to force a fresh download.
        pinned: What the file must be.
        report: Receives the repair notice, which names the cache path.

    Raises:
        OpticaCLIPLoadError: When the file is still wrong after one re-download,
            or cannot be downloaded at all.
    """
    try:
        path = download(False)
    except Exception as exc:  # network, disk, Hub errors: all are "cannot load"
        raise _load_error("could not be downloaded", None, exc) from exc
    problem = weights_problem(path, pinned)
    if problem is None:
        return path

    report(
        f"The cached CLIP weights at {path} {problem}; deleting them and "
        "downloading again."
    )
    _remove_cached(path)
    try:
        path = download(True)
    except Exception as exc:
        raise _load_error("could not be downloaded again", path, exc) from exc
    problem = weights_problem(path, pinned)
    if problem is not None:
        raise _load_error(f"{problem} after a fresh download", path, None)
    return path


def _load_error(
    what: str, path: Path | None, cause: BaseException | None
) -> OpticaCLIPLoadError:
    where = f" at {path}" if path is not None else ""
    why = f"{type(cause).__name__}: {cause}" if cause is not None else None
    return OpticaCLIPLoadError(
        f"The CLIP weights ({CLIP_MODEL}/{CLIP_PRETRAINED}){where} {what}.",
        why=why,
        fix=[
            "Check the network connection and free disk space, then run again.",
            *(
                [f"The cache file is {path}; deleting it forces a clean download."]
                if path
                else []
            ),
        ],
    )


# ------------------------------------------------------------------- scorer


class ImageScorer(Protocol):
    """Scores images against text prompts. The CLI and tests supply one."""

    def score(
        self,
        images: Sequence[Path],
        prompts: Sequence[str],
        *,
        on_image: Callable[[], None] | None = None,
    ) -> list[float | None]:
        """Each image's best cosine similarity over ``prompts``; None if unreadable."""
        ...


def select_device() -> torch.device:
    """CUDA if available, then MPS, then CPU.

    The MPS branch is written and has never been run: the build machine has an
    NVIDIA GPU and no Apple silicon (``notes/build-log.md``).
    """
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():  # TODO(test): MPS never exercised
        return torch.device("mps")
    return torch.device("cpu")


class ClipScorer:
    """An open-clip model, its preprocessing and its tokenizer, on one device."""

    def __init__(
        self,
        model: Any,
        preprocess: Callable[[Any], Any],
        tokenizer: Callable[[list[str]], Any],
        device: torch.device,
    ) -> None:
        self.model = model
        self.preprocess = preprocess
        self.tokenizer = tokenizer
        self.device = device

    def score(
        self,
        images: Sequence[Path],
        prompts: Sequence[str],
        *,
        on_image: Callable[[], None] | None = None,
    ) -> list[float | None]:
        """Each image's best cosine similarity over ``prompts``.

        Cosine similarity of L2-normalised embeddings — the value
        ``clip_threshold`` is calibrated against — and deliberately not
        ``logits_per_image``, which carries ``logit_scale``.
        """
        import torch
        from PIL import Image, UnidentifiedImageError

        if not prompts:
            raise ValueError("at least one prompt is required")
        scores: list[float | None] = [None] * len(images)
        with torch.no_grad():
            text = self.model.encode_text(self.tokenizer(list(prompts)).to(self.device))
            text = text / text.norm(dim=-1, keepdim=True)
            for start in range(0, len(images), _SCORE_BATCH):
                batch: list[Any] = []
                indices: list[int] = []
                for index in range(start, min(start + _SCORE_BATCH, len(images))):
                    try:
                        with Image.open(images[index]) as image:
                            batch.append(self.preprocess(image.convert("RGB")))
                        indices.append(index)
                    except (OSError, UnidentifiedImageError, ValueError):
                        pass  # stays None: unreadable, never passes
                if batch:
                    pixels = torch.stack(batch).to(self.device)
                    features = self.model.encode_image(pixels)
                    features = features / features.norm(dim=-1, keepdim=True)
                    best = (features @ text.T).max(dim=1).values
                    for index, value in zip(indices, best.tolist(), strict=True):
                        scores[index] = float(value)
                if on_image is not None:
                    for _ in range(start, min(start + _SCORE_BATCH, len(images))):
                        on_image()
        return scores


def _import_open_clip() -> Any:
    try:
        import open_clip
    except ImportError as exc:
        raise OpticaCLIPError() from exc
    return open_clip


def load_clip(
    *,
    report: Callable[[str], None],
    device: torch.device | None = None,
    quiet: bool = False,
) -> ClipScorer:
    """Load ``ViT-B-32``/``openai`` from a verified cache.

    Informs the user before a first-use download, which then shows the Hub's
    own progress bar (suppressed under ``quiet``).

    Raises:
        OpticaCLIPError: ``optica[clip]`` is not installed.
        OpticaCLIPLoadError: The weights cannot be downloaded, stay corrupt
            after one re-download, or fail to load.
    """
    # Before the Hub is imported: on Windows without Developer Mode it warns
    # about symlinks on every download, which is not the user's to act on.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    open_clip = _import_open_clip()
    import huggingface_hub

    cfg = open_clip.get_pretrained_cfg(CLIP_MODEL, CLIP_PRETRAINED)
    repo_id = str(cfg["hf_hub"]).strip("/")
    pinned = PINNED_WEIGHTS[WEIGHTS_FILENAME]

    cached = huggingface_hub.try_to_load_from_cache(repo_id, WEIGHTS_FILENAME)
    if not isinstance(cached, str):
        report(
            f"Downloading the CLIP model ({CLIP_MODEL}, {CLIP_PRETRAINED} weights, "
            f"{pinned.size / 1e6:.0f} MB) — first use only. "
            f"Cache: {huggingface_hub.constants.HF_HUB_CACHE}"
        )
    if quiet:
        # Exported at runtime but not re-exported for type checkers.
        from huggingface_hub.utils import (  # type: ignore[attr-defined, unused-ignore]
            disable_progress_bars,
        )

        disable_progress_bars()

    def download(force: bool) -> Path:
        path = huggingface_hub.hf_hub_download(
            repo_id, WEIGHTS_FILENAME, force_download=force
        )
        return Path(str(path))

    path = ensure_weights(download, pinned, report=report)
    device = device if device is not None else select_device()
    try:
        # The plan's call, with the tag rather than a file path: the tag supplies
        # the openai preprocessing (mean/std, interpolation, resize mode) and
        # resolves to the file verified above. It does NOT apply the tag's
        # QuickGELU — open-clip 3.3.0 only warns about the mismatch — hence
        # MODEL_KWARGS (notes/verified.md, pass 4).
        model, _, preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL, pretrained=CLIP_PRETRAINED, device=device, **MODEL_KWARGS
        )
        tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
    except Exception as exc:
        raise _load_error("failed to load", path, exc) from exc
    model.eval()
    return ClipScorer(model, preprocess, tokenizer, device)
