import io

import pytest
from PIL import Image

from app.image_validation import SUPPORTED_IMAGE_FORMATS, normalize_image_for_ocr, validate_image_content


def jpeg_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_valid_jpeg_is_fully_decoded_without_verify(monkeypatch):
    monkeypatch.setattr(Image.Image, "verify", lambda self: (_ for _ in ()).throw(AssertionError("verify must not be used")))
    width, height, digest = validate_image_content(jpeg_bytes(), "image/jpeg")
    assert (width, height) == (32, 24)
    assert len(digest) == 64


def test_mime_mismatch_reports_actual_format():
    with pytest.raises(ValueError, match="declared=image/png, actual=image/jpeg"):
        validate_image_content(jpeg_bytes(), "image/png")


def test_unknown_bytes_report_decode_failure():
    with pytest.raises(ValueError, match="Image decode failed"):
        validate_image_content(b"not-an-image", "image/jpeg")


def test_pillow_mpo_is_a_supported_jpeg_container():
    assert SUPPORTED_IMAGE_FORMATS["MPO"] == "image/jpeg"


def test_regular_jpeg_is_not_reencoded_for_ocr():
    content = jpeg_bytes()
    assert normalize_image_for_ocr(content, "image/jpeg") is content
