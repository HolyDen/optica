"""The CLIP Adapter.

Covers plan § "Input & Acquisition" → *CLIP Adapter (clip mode)*: the
``"a photo of a {class}"`` template and its name normalisation, cosine similarity
of L2-normalised embeddings rather than ``logits_per_image``, the ``* 2``
over-fetch keeping up to ``images_per_class``, weights verified on every load and
repaired once, ``OpticaCLIPError`` for a missing extra and
``OpticaCLIPLoadError`` for a load failure; and § *Undefinable classes in auto
modes* — a grouped image is scored against all sub-terms.

The classes without a ``slow`` mark import neither torch nor open_clip and run in
CI. Those with it construct their model: a hand-built one whose embeddings are
chosen, or open-clip's ``ViT-B-32`` with ``pretrained=None`` — never the 605 MB
download.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from optica.exceptions import OpticaCLIPError, OpticaCLIPLoadError
from optica.input import clip
from optica.input.classes import ResolvedClass

# --------------------------------------------------------------------- pure


class TestPrompt:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            # The plan's own example.
            ("golden_retriever", "a photo of a golden retriever"),
            ("Golden-Retriever", "a photo of a golden retriever"),
            ("cat", "a photo of a cat"),
            ("orange cat", "a photo of a orange cat"),
            ("T-shirt", "a photo of a t shirt"),
        ],
    )
    def test_the_template_and_normalisation(self, name, expected):
        assert clip.prompt_for(name) == expected

    def test_the_model_and_weights_are_the_plans(self):
        assert (clip.CLIP_MODEL, clip.CLIP_PRETRAINED) == ("ViT-B-32", "openai")
        assert clip.PROMPT_TEMPLATE == "a photo of a {}"


class TestOverfetch:
    def test_an_ordinary_class_fetches_twice_its_target(self):
        cls = ResolvedClass("cat", ["cat"], 50)
        doubled = clip.overfetch(cls)
        assert doubled.target == 100
        assert cls.target == 50  # the plan's class keeps the keep-cap

    def test_a_grouped_class_doubles_per_sub_term(self):
        cls = ResolvedClass("defective", ["cracked", "dented"], 25, "defective", True)
        doubled = clip.overfetch(cls)
        assert (doubled.per_query, doubled.target) == (50, 100)
        assert doubled.queries == ["cracked", "dented"]
        assert doubled.queries is not cls.queries

    def test_the_factor_is_two(self):
        assert clip.OVERFETCH_FACTOR == 2


def _scored(*scores: float | None) -> list[tuple[Path, float | None]]:
    return [(Path(f"{i:04d}.jpg"), score) for i, score in enumerate(scores, start=1)]


class TestSurvivors:
    def test_a_score_equal_to_the_threshold_passes(self):
        # "CLIP discards whatever scores below the threshold."
        report = clip.select_survivors("cat", _scored(0.25, 0.2499999), 0.25, None)
        assert report.kept_paths == [Path("0001.jpg")]
        assert report.rejected_paths == [Path("0002.jpg")]

    def test_up_to_keep_are_kept_best_first(self):
        report = clip.select_survivors("cat", _scored(0.3, 0.9, 0.1, 0.5, 0.7), 0.25, 2)
        assert report.kept_paths == [Path("0002.jpg"), Path("0005.jpg")]
        assert (report.candidates, report.passed, report.kept) == (5, 4, 2)

    def test_fewer_passing_than_keep_is_a_shortfall_not_an_error(self):
        report = clip.select_survivors("cat", _scored(0.3, 0.1, 0.1), 0.25, 5)
        assert report.kept == 1
        assert report.shortfall == 4

    def test_ties_are_broken_by_path(self):
        scored = [(Path(f"{i:04d}.jpg"), 0.5) for i in (9, 3, 5)]
        report = clip.select_survivors("cat", scored, 0.25, 2)
        assert report.kept_paths == [Path("0003.jpg"), Path("0005.jpg")]

    def test_an_unreadable_image_never_passes(self):
        report = clip.select_survivors("cat", _scored(None, 0.9), 0.0001, None)
        assert report.unreadable == 1
        assert report.kept_paths == [Path("0002.jpg")]

    def test_keep_none_keeps_every_passing_image(self):
        report = clip.select_survivors("defective", _scored(0.3, 0.4, 0.1), 0.25, None)
        assert report.kept == 2
        assert report.shortfall == 0

    @pytest.mark.parametrize("keep", [None, 0, 1, 3, 10])
    def test_the_breakdown_reconciles(self, keep):
        report = clip.select_survivors(
            "cat", _scored(0.9, None, 0.1, 0.3, 0.25, 0.26), 0.25, keep
        )
        assert report.candidates == report.passed + report.below_threshold
        assert report.kept + len(report.rejected_paths) == report.candidates
        assert set(report.kept_paths).isdisjoint(report.rejected_paths)


# ------------------------------------------------------------------ weights


class _Cache:
    """A download callable over a file on disk, recording each call."""

    def __init__(self, path: Path, *, first: bytes, fresh: bytes | None = None) -> None:
        self.path = path
        self.fresh = fresh
        self.calls: list[bool] = []
        self.existed_at_force: list[bool] = []
        path.write_bytes(first)

    def __call__(self, force: bool) -> Path:
        self.calls.append(force)
        if force:
            self.existed_at_force.append(self.path.exists())
            assert self.fresh is not None
            self.path.write_bytes(self.fresh)
        return self.path


GOOD = b"weights" * 1000


def _pinned(data: bytes = GOOD) -> clip.PinnedFile:
    return clip.PinnedFile(len(data), hashlib.sha256(data).hexdigest())


class TestWeights:
    def test_the_pinned_file_is_the_verified_one(self):
        # notes/verified.md, pass 4: timm/vit_base_patch32_clip_224.openai.
        pinned = clip.PINNED_WEIGHTS[clip.WEIGHTS_FILENAME]
        assert clip.WEIGHTS_FILENAME == "open_clip_model.safetensors"
        assert pinned.size == 605_143_284
        assert pinned.sha256.startswith("e6d1bd7789aa4519")

    def test_a_good_cache_is_used_without_a_download(self, tmp_path):
        cache = _Cache(tmp_path / "w.safetensors", first=GOOD)
        reports: list[str] = []
        path = clip.ensure_weights(cache, _pinned(), report=reports.append)
        assert path == cache.path
        assert cache.calls == [False]
        assert reports == []

    @pytest.mark.parametrize(
        ("bad", "problem"),
        [
            (GOOD[:-10], "bytes, expected"),  # interrupted download
            (b"X" + GOOD[1:], "SHA-256"),  # same size, corrupt
        ],
        ids=["truncated", "corrupt"],
    )
    def test_a_bad_cache_is_deleted_reported_and_downloaded_again(
        self, tmp_path, bad, problem
    ):
        cache = _Cache(tmp_path / "w.safetensors", first=bad, fresh=GOOD)
        reports: list[str] = []
        path = clip.ensure_weights(cache, _pinned(), report=reports.append)
        assert cache.calls == [False, True]
        assert cache.existed_at_force == [False]  # deleted before re-downloading
        assert path.read_bytes() == GOOD
        [line] = reports
        assert str(cache.path) in line  # the cache path is reported
        assert problem in line

    def test_still_bad_after_one_download_is_a_load_error_naming_the_path(
        self, tmp_path
    ):
        cache = _Cache(tmp_path / "w.safetensors", first=b"bad", fresh=b"still bad")
        with pytest.raises(OpticaCLIPLoadError) as info:
            clip.ensure_weights(cache, _pinned(), report=lambda _: None)
        assert cache.calls == [False, True]  # once, not a loop
        assert str(cache.path) in info.value.message

    def test_a_failed_download_is_a_load_error(self, tmp_path):
        def offline(force: bool) -> Path:
            raise OSError("no route to host")

        with pytest.raises(OpticaCLIPLoadError) as info:
            clip.ensure_weights(offline, _pinned(), report=lambda _: None)
        assert "could not be downloaded" in info.value.message
        assert "no route to host" in (info.value.why or "")

    def test_a_missing_file_is_reported_as_missing(self, tmp_path):
        assert clip.weights_problem(tmp_path / "absent", _pinned()) == "is missing"

    def test_sha256_matches_hashlib_across_chunks(self, tmp_path, monkeypatch):
        monkeypatch.setattr(clip, "_HASH_CHUNK", 7)
        target = tmp_path / "f"
        target.write_bytes(GOOD)
        assert clip.sha256_of(target) == hashlib.sha256(GOOD).hexdigest()


class TestLoadWiring:
    """``load_clip`` against a recording open_clip and Hub — no torch, no network."""

    def test_the_plans_call_plus_quick_gelu_on_a_verified_file(
        self, tmp_path, monkeypatch
    ):
        import types

        calls: dict[str, object] = {}
        weights = tmp_path / clip.WEIGHTS_FILENAME
        weights.write_bytes(GOOD)

        class Model:
            def eval(self):
                calls["eval"] = True

        fake_clip = types.ModuleType("open_clip")
        fake_clip.get_pretrained_cfg = lambda model, tag: {  # type: ignore[attr-defined]
            "hf_hub": "timm/vit_base_patch32_clip_224.openai/"
        }

        def create(model_name, **kwargs):
            calls["create"] = (model_name, kwargs)
            return Model(), None, "preprocess"

        fake_clip.create_model_and_transforms = create  # type: ignore[attr-defined]
        fake_clip.get_tokenizer = lambda name: "tokenizer"  # type: ignore[attr-defined]

        fake_hub = types.ModuleType("huggingface_hub")
        fake_hub.try_to_load_from_cache = lambda repo, name: str(weights)  # type: ignore[attr-defined]

        def download(repo, name, force_download=False):
            calls["download"] = (repo, name, force_download)
            return str(weights)

        fake_hub.hf_hub_download = download  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "open_clip", fake_clip)
        monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
        monkeypatch.setitem(clip.PINNED_WEIGHTS, clip.WEIGHTS_FILENAME, _pinned())

        reports: list[str] = []
        scorer = clip.load_clip(report=reports.append, device="cpu")  # type: ignore[arg-type, unused-ignore]

        assert calls["download"] == (
            "timm/vit_base_patch32_clip_224.openai",
            clip.WEIGHTS_FILENAME,
            False,
        )
        assert calls["create"] == (
            "ViT-B-32",
            {"pretrained": "openai", "device": "cpu", "force_quick_gelu": True},
        )
        assert calls["eval"] is True
        assert str(scorer.tokenizer) == "tokenizer"
        assert reports == []  # cached: no first-use notice

    def test_a_first_use_download_is_announced_with_its_size_and_cache(
        self, tmp_path, monkeypatch
    ):
        import types

        fake_clip = types.ModuleType("open_clip")
        fake_clip.get_pretrained_cfg = lambda model, tag: {"hf_hub": "org/repo/"}  # type: ignore[attr-defined]
        fake_hub = types.ModuleType("huggingface_hub")
        fake_hub.try_to_load_from_cache = lambda repo, name: None  # type: ignore[attr-defined]
        fake_hub.constants = types.SimpleNamespace(HF_HUB_CACHE="/cache/hub")  # type: ignore[attr-defined]

        def offline(repo, name, force_download=False):
            raise OSError("offline")

        fake_hub.hf_hub_download = offline  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "open_clip", fake_clip)
        monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
        reports: list[str] = []
        with pytest.raises(OpticaCLIPLoadError):
            clip.load_clip(report=reports.append, device="cpu")  # type: ignore[arg-type, unused-ignore]
        [notice] = reports
        assert "605 MB" in notice
        assert "first use only" in notice
        assert "/cache/hub" in notice


class TestMissingExtra:
    def test_no_open_clip_is_the_capability_named_error(self, monkeypatch):
        # Constructed: a None entry makes `import open_clip` raise ImportError,
        # whether or not this machine has the extra.
        monkeypatch.setitem(sys.modules, "open_clip", None)
        with pytest.raises(OpticaCLIPError) as info:
            clip.load_clip(report=lambda _: None)
        assert "CLIP filtering requires the clip extra" in info.value.message


# --------------------------------------------------------------------- slow


def _write_images(folder: Path, count: int) -> list[Path]:
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        path = folder / f"{i + 1:04d}.png"
        Image.new("RGB", (32, 32), (i * 40 % 256, 10, 200)).save(path)
        paths.append(path)
    return paths


@pytest.mark.slow
class TestScorerMath:
    """A model whose embeddings are chosen, so the expected score is exact."""

    def _scorer(
        self, image_vectors: list[list[float]], text_vectors: list[list[float]]
    ) -> clip.ClipScorer:
        import torch

        class Model:
            logit_scale = torch.tensor(100.0).log()

            def encode_text(self, tokens):
                return torch.tensor(text_vectors, dtype=torch.float32)[: len(tokens)]

            def encode_image(self, pixels):
                # The preprocess below stores each image's index in the pixels.
                idx = pixels[:, 0, 0, 0].long().tolist()
                return torch.tensor([image_vectors[i] for i in idx], dtype=torch.float32)

        seen: list[int] = []

        def preprocess(image):
            seen.append(len(seen))
            return torch.full((3, 2, 2), float(len(seen) - 1))

        def tokenizer(texts):
            return torch.zeros((len(texts), 4), dtype=torch.long)

        return clip.ClipScorer(Model(), preprocess, tokenizer, torch.device("cpu"))

    def test_the_score_is_cosine_similarity_not_scaled_logits(self, tmp_path):
        images = _write_images(tmp_path, 2)
        # Unnormalised on purpose: normalisation is part of what is tested.
        scorer = self._scorer([[3.0, 4.0], [0.0, 2.0]], [[1.0, 0.0]])
        scores = scorer.score(images, ["a photo of a cat"])
        assert scores == pytest.approx([0.6, 0.0])
        assert all(s is not None and -1.0 <= s <= 1.0 for s in scores)

    def test_several_prompts_take_the_best_match(self, tmp_path):
        images = _write_images(tmp_path, 1)
        scorer = self._scorer([[3.0, 4.0]], [[1.0, 0.0], [0.0, 1.0]])
        assert scorer.score(images, ["a", "b"]) == pytest.approx([0.8])

    def test_an_unreadable_image_scores_none_and_the_rest_still_score(self, tmp_path):
        images = _write_images(tmp_path, 1)
        broken = tmp_path / "0002.png"
        broken.write_bytes(b"not an image")
        scorer = self._scorer([[1.0, 0.0]], [[1.0, 0.0]])
        ticks: list[int] = []
        scores = scorer.score([broken, *images], ["x"], on_image=lambda: ticks.append(1))
        assert scores[0] is None
        assert scores[1] == pytest.approx(1.0)
        assert len(ticks) == 2


@pytest.mark.slow
class TestRealOpenClip:
    def test_open_clip_resolves_the_tag_to_the_pinned_file(self):
        # If an open-clip upgrade changes which file `openai` loads, verification
        # would check one file while open-clip loads another. This fails first.
        import open_clip
        from open_clip.pretrained import HF_WEIGHTS_NAME, _get_safe_alternatives

        cfg = open_clip.get_pretrained_cfg(clip.CLIP_MODEL, clip.CLIP_PRETRAINED)
        assert cfg["hf_hub"].strip("/") == "timm/vit_base_patch32_clip_224.openai"
        assert clip.WEIGHTS_FILENAME in list(_get_safe_alternatives(HF_WEIGHTS_NAME))

    @staticmethod
    def _quick_gelu_modules(**kwargs: object) -> int:
        import open_clip
        from open_clip.transformer import QuickGELU

        model = open_clip.create_model(clip.CLIP_MODEL, pretrained=None, **kwargs)
        return sum(isinstance(module, QuickGELU) for module in model.modules())

    def test_the_model_is_built_with_the_weights_activation(self):
        # The openai tag was trained with QuickGELU. open-clip 3.3.0 does not
        # apply that from the tag — it warns — so MODEL_KWARGS must, and the
        # model it builds must actually contain QuickGELU.
        import open_clip

        cfg = open_clip.get_pretrained_cfg(clip.CLIP_MODEL, clip.CLIP_PRETRAINED)
        assert cfg["quick_gelu"] is True
        assert clip.MODEL_KWARGS.get("force_quick_gelu") is True
        assert self._quick_gelu_modules(**clip.MODEL_KWARGS) > 0

    def test_the_plans_bare_call_would_build_gelu(self):
        # Why MODEL_KWARGS exists. If open-clip starts applying the tag's
        # activation itself, this fails and the kwarg becomes redundant (harmless).
        assert self._quick_gelu_modules() == 0

    def test_a_random_weight_vit_b_32_scores_within_cosine_range(self, tmp_path):
        import open_clip
        import torch

        model, _, preprocess = open_clip.create_model_and_transforms(
            clip.CLIP_MODEL, pretrained=None
        )
        model.eval()
        scorer = clip.ClipScorer(
            model,
            preprocess,
            open_clip.get_tokenizer(clip.CLIP_MODEL),
            torch.device("cpu"),
        )
        images = _write_images(tmp_path, 3)
        scores = scorer.score(
            images, [clip.prompt_for("cat"), clip.prompt_for("golden_retriever")]
        )
        assert len(scores) == 3
        assert all(s is not None and -1.0 <= s <= 1.0 for s in scores)


@pytest.mark.slow
class TestDevice:
    def test_cuda_is_chosen_when_available(self, monkeypatch):
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        assert clip.select_device().type == "cuda"

    def test_cpu_when_neither_accelerator_is_available(self, monkeypatch):
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
        assert clip.select_device().type == "cpu"

    def test_mps_when_only_mps_is_available(self, monkeypatch):
        # Constructs the condition; the MPS device itself is never used here.
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
        assert clip.select_device().type == "mps"
