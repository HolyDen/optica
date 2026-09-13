"""The image validation pipeline.

Covers plan § "Input & Acquisition" → *Class imbalance and image validation*
(format targets and conversion, the 128px resize, MD5 deduplication, the
post-deduplication floor re-check, the 50% imbalance warning), *Unreadable
images — pre-flight verification* (reasons, and the ownership rule), and the
manifest section's *Filename collisions* (the ``_x`` suffix sequence).
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from optica.exceptions import OpticaValidationError
from optica.input import validation as v


def _encode(image: Image.Image, fmt: str, **kwargs) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def _rgb(size=(200, 150), color="teal") -> Image.Image:
    return Image.new("RGB", size, color)


class TestPlanConstants:
    def test_values_transcribed_from_the_plan(self):
        assert v.SIZE_THRESHOLD == 128
        assert v.JPEG_QUALITY == 90
        assert v.HARD_FLOOR == 5
        assert v.IMBALANCE_RATIO == 2.0
        assert set(v.TARGET_EXTENSIONS) == {"JPEG", "PNG", "WEBP"}


class TestFormatTargets:
    @pytest.mark.parametrize(
        ("fmt", "ext"), [("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")]
    )
    def test_targeted_formats_pass_through_untouched(self, fmt, ext):
        data = _encode(_rgb(), fmt)
        result = v.process_owned(data)
        assert isinstance(result, v.ProcessedImage)
        assert result.data == data
        assert result.extension == ext
        assert not result.converted
        assert not result.resized

    def test_bmp_without_alpha_converts_to_jpeg(self):
        result = v.process_owned(_encode(_rgb(), "BMP"))
        assert isinstance(result, v.ProcessedImage)
        assert result.converted
        assert result.extension == ".jpg"
        assert Image.open(io.BytesIO(result.data)).format == "JPEG"

    def test_tiff_with_alpha_converts_to_png(self):
        image = Image.new("RGBA", (200, 200), (10, 20, 30, 128))
        result = v.process_owned(_encode(image, "TIFF"))
        assert isinstance(result, v.ProcessedImage)
        assert result.extension == ".png"

    def test_a_palette_image_converts_to_png(self):
        image = _rgb().convert("P")
        result = v.process_owned(_encode(image, "BMP"))
        assert isinstance(result, v.ProcessedImage)
        assert result.extension == ".png"

    def test_more_than_eight_bits_per_channel_converts_to_png(self):
        image = Image.new("I;16", (200, 200), 40000)
        result = v.process_owned(_encode(image, "TIFF"))
        assert isinstance(result, v.ProcessedImage)
        assert result.extension == ".png"

    def test_animated_gif_converts_from_its_first_frame(self):
        frames = [Image.new("RGB", (200, 200), c) for c in ("red", "blue")]
        data = _encode(frames[0], "GIF", save_all=True, append_images=frames[1:])
        result = v.process_owned(data)
        assert isinstance(result, v.ProcessedImage)
        assert result.converted
        # GIF is palette-based, so the lossless target applies.
        assert result.extension == ".png"
        first = Image.open(io.BytesIO(result.data)).convert("RGB")
        assert first.getpixel((5, 5)) == (255, 0, 0)

    def test_animated_webp_is_converted_even_though_webp_is_targeted(self):
        frames = [Image.new("RGB", (200, 200), c) for c in ("red", "blue")]
        data = _encode(frames[0], "WEBP", save_all=True, append_images=frames[1:])
        result = v.process_owned(data)
        assert isinstance(result, v.ProcessedImage)
        assert result.converted
        assert result.extension in {".jpg", ".png"}

    def test_jpeg_conversion_uses_quality_90_not_pillows_75(self):
        noisy = Image.effect_noise((300, 300), 80).convert("RGB")
        result = v.process_owned(_encode(noisy, "BMP"))
        assert isinstance(result, v.ProcessedImage)
        at_90 = _encode(noisy, "JPEG", quality=90)
        assert result.data == at_90


class TestResize:
    def test_undersized_upscales_shorter_side_to_128_preserving_aspect(self):
        result = v.process_owned(_encode(_rgb((100, 50)), "PNG"))
        assert isinstance(result, v.ProcessedImage)
        assert result.resized
        assert Image.open(io.BytesIO(result.data)).size == (256, 128)
        assert result.original_size == (100, 50)
        # Resizing a targeted format keeps its format.
        assert result.extension == ".png"

    def test_exactly_128_is_untouched(self):
        data = _encode(_rgb((128, 400)), "JPEG")
        result = v.process_owned(data)
        assert isinstance(result, v.ProcessedImage)
        assert not result.resized
        assert result.data == data

    def test_never_downscales(self):
        data = _encode(_rgb((4000, 3000)), "JPEG")
        result = v.process_owned(data)
        assert isinstance(result, v.ProcessedImage)
        assert result.data == data


class TestRejectReasons:
    def test_zero_bytes(self):
        assert v.process_owned(b"") is v.RejectReason.ZERO_BYTES

    def test_not_an_image(self):
        assert v.process_owned(b"<html>404</html>") is v.RejectReason.UNDECODABLE

    def test_truncated_jpeg_is_caught_by_the_full_decode(self):
        full = _encode(Image.effect_noise((300, 300), 64).convert("RGB"), "JPEG")
        assert v.process_owned(full[: len(full) // 2]) is v.RejectReason.TRUNCATED

    def test_reason_wording_matches_the_plan(self):
        assert {r.value for r in v.RejectReason} == {
            "could not be opened",
            "format Pillow cannot decode",
            "truncated file",
            "zero bytes",
        }


class TestInPlaceNeverWrites:
    def test_reports_convertible_and_undersized_without_writing(self, tmp_path):
        path = tmp_path / "small.bmp"
        path.write_bytes(_encode(_rgb((60, 60)), "BMP"))
        before = path.read_bytes()
        report = v.inspect_in_place(path)
        assert report.readable
        assert report.convertible
        assert report.undersized
        assert path.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir()) == ["small.bmp"]

    def test_zero_byte_file(self, tmp_path):
        path = tmp_path / "empty.jpg"
        path.write_bytes(b"")
        assert v.inspect_in_place(path).reason is v.RejectReason.ZERO_BYTES

    def test_text_file(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("hello", encoding="utf-8")
        assert v.inspect_in_place(path).reason is v.RejectReason.UNDECODABLE

    def test_a_header_check_does_not_see_a_half_jpeg(self, tmp_path):
        # Measured and logged: the plan specifies header validation for
        # pre-flight, and Pillow's verify() passes a JPEG cut in half.
        full = _encode(Image.effect_noise((300, 300), 64).convert("RGB"), "JPEG")
        path = tmp_path / "half.jpg"
        path.write_bytes(full[: len(full) // 2])
        assert v.inspect_in_place(path).readable

    def test_truncated_png_is_seen_by_the_header_check(self, tmp_path):
        path = tmp_path / "cut.png"
        path.write_bytes(_encode(_rgb(), "PNG")[:-20])
        assert v.inspect_in_place(path).reason is not None

    def test_missing_file(self, tmp_path):
        assert (
            v.inspect_in_place(tmp_path / "gone.jpg").reason is v.RejectReason.UNOPENABLE
        )

    def test_reasons_summary_truncates_past_ten(self, tmp_path):
        reports = [
            v.InPlaceReport(tmp_path / f"{i}.jpg", v.RejectReason.ZERO_BYTES)
            for i in range(12)
        ]
        lines = v.reasons_summary(reports)
        assert len(lines) == 11
        assert lines[-1] == "(and 2 more)"


class TestCollisionSuffixes:
    def test_the_x_sequence_in_offer_order(self):
        taken: set[str] = set()
        names = [v.unique_name("img.jpg", taken) for _ in range(3)]
        assert names == ["img.jpg", "img_2.jpg", "img_3.jpg"]

    def test_collision_is_case_insensitive(self):
        taken: set[str] = set()
        assert v.unique_name("IMG.jpg", taken) == "IMG.jpg"
        assert v.unique_name("img.jpg", taken) == "img_2.jpg"

    def test_post_conversion_names_collide(self):
        # photo.bmp converts to photo.jpg and meets photo.jpg: distinct sources,
        # one target name.
        taken: set[str] = set()
        assert v.unique_name("photo.jpg", taken) == "photo.jpg"
        assert v.unique_name("photo.jpg", taken) == "photo_2.jpg"

    def test_a_suffix_already_present_is_skipped(self):
        taken = {"img.jpg", "img_2.jpg"}
        assert v.unique_name("img.jpg", taken) == "img_3.jpg"


class TestDeduplication:
    def test_within_class_md5_keeps_the_first(self, tmp_path):
        a, b, c = (tmp_path / n for n in ("a.jpg", "b.jpg", "c.jpg"))
        a.write_bytes(b"same")
        b.write_bytes(b"other")
        c.write_bytes(b"same")
        unique, duplicates = v.find_duplicates([a, b, c])
        assert unique == [a, b]
        assert duplicates == [c]

    def test_md5_digest(self):
        assert v.md5_of(b"") == "d41d8cd98f00b204e9800998ecf8427e"


class TestFloors:
    def test_the_hard_floor_is_five(self):
        v.check_floor({"cat": 5, "dog": 7})
        with pytest.raises(OpticaValidationError):
            v.check_floor({"cat": 4, "dog": 7})

    def test_post_dedupe_message_matches_the_plan(self):
        with pytest.raises(OpticaValidationError) as info:
            v.check_floor_after_dedupe({"cat": 5, "dog": 9}, {"cat": 4, "dog": 9})
        err = info.value
        assert (
            err.message == "cat fell below the 5-image minimum after duplicate removal."
        )
        assert err.why == "cat: 5 images → 4 unique (1 duplicate removed)"
        assert err.fix == ["Add more images for cat and run again."]

    def test_a_labeling_session_adds_that_it_is_resumable(self):
        with pytest.raises(OpticaValidationError) as info:
            v.check_floor_after_dedupe({"cat": 5}, {"cat": 2}, resumable_session=True)
        assert any("resume" in line for line in info.value.fix)

    def test_every_fallen_class_is_named(self):
        with pytest.raises(OpticaValidationError) as info:
            v.check_floor_after_dedupe({"cat": 6, "dog": 6}, {"cat": 3, "dog": 1})
        assert "cat, dog" in info.value.message
        assert len([line for line in info.value.fix if "→" in line]) == 2

    def test_passes_at_the_floor(self):
        v.check_floor_after_dedupe({"cat": 9}, {"cat": 5})


class TestImbalance:
    def test_the_plans_example_warns(self):
        found = v.imbalanced_classes({"cat": 45, "dog": 8})
        assert found is not None
        assert found.short == {"dog": 8}
        assert found.largest == 45

    def test_exactly_half_does_not_warn(self):
        assert v.imbalanced_classes({"cat": 40, "dog": 20}) is None

    def test_just_below_half_warns(self):
        assert v.imbalanced_classes({"cat": 41, "dog": 20}) is not None

    def test_f_requests_the_shortfall_to_the_largest_class(self):
        assert v.shortfall({"cat": 45, "dog": 8}, "dog") == 37
        assert v.shortfall({"cat": 45, "dog": 8}, "cat") == 0

    def test_empty(self):
        assert v.imbalanced_classes({}) is None
