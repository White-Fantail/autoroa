import hashlib
import io
import logging
import warnings

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)
# Pillow reports some multi-picture JPEGs (commonly produced by iPhone photo
# workflows) as MPO. MPO's first frame is a normal JPEG image and the file uses
# the JPEG media type, so accept it as image/jpeg at the upload boundary.
SUPPORTED_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "MPO": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def _signature(content: bytes) -> str:
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return f"iso-bmff:{content[8:12].decode('ascii', 'replace')}"
    return content[:8].hex() or "empty"


def validate_image_content(content: bytes, declared_mime: str, max_pixels: int = 40_000_000):
    """Fully decode image pixels and validate the decoded format against the declared MIME."""
    fmt = None
    width = height = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                fmt = image.format
                if width * height > max_pixels:
                    raise ValueError("Image dimensions are too large")
                # Only the primary frame is used by OCR. Loading it completely is
                # the trust boundary; auxiliary MPO frames are not processed.
                image.seek(0)
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, EOFError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        logger.warning(
            "image_validation_decode_failed declared_mime=%s size=%s signature=%s error_type=%s error=%r",
            declared_mime,
            len(content),
            _signature(content),
            type(exc).__name__,
            exc,
        )
        raise ValueError(
            f"Image decode failed ({type(exc).__name__}); declared={declared_mime}; signature={_signature(content)}"
        ) from exc

    actual_mime = SUPPORTED_IMAGE_FORMATS.get(fmt or "")
    if not actual_mime:
        logger.warning(
            "image_validation_format_unsupported declared_mime=%s decoded_format=%s size=%s signature=%s",
            declared_mime,
            fmt,
            len(content),
            _signature(content),
        )
        raise ValueError(f"Decoded image format {fmt or 'unknown'} is unsupported")
    if actual_mime != declared_mime:
        logger.warning(
            "image_validation_mime_mismatch declared_mime=%s actual_mime=%s decoded_format=%s size=%s signature=%s",
            declared_mime,
            actual_mime,
            fmt,
            len(content),
            _signature(content),
        )
        raise ValueError(f"Image MIME mismatch: declared={declared_mime}, actual={actual_mime}")

    logger.info(
        "image_validation_ok declared_mime=%s actual_mime=%s decoded_format=%s width=%s height=%s size=%s signature=%s",
        declared_mime,
        actual_mime,
        fmt,
        width,
        height,
        len(content),
        _signature(content),
    )
    return width, height, hashlib.sha256(content).hexdigest()


def normalize_image_for_ocr(content: bytes, declared_mime: str) -> bytes:
    """Return provider-friendly bytes while leaving the stored original untouched.

    Most formats can be sent as-is. MPO is canonicalized to a single-frame JPEG
    because downstream vision providers are not required to understand the
    multi-picture container. The original object (and its EXIF/GPS) remains in
    storage for station inference.
    """
    if declared_mime != "image/jpeg":
        return content
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "MPO":
                return content
            image.seek(0)
            image.load()
            frame = image.convert("RGB")
            output = io.BytesIO()
            frame.save(output, format="JPEG", quality=95, optimize=True)
            normalized = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, EOFError) as exc:
        logger.warning("image_ocr_normalization_failed declared_mime=%s error_type=%s error=%r", declared_mime, type(exc).__name__, exc)
        raise ValueError("Image could not be normalized for OCR") from exc
    logger.info("image_ocr_normalized source_format=MPO target_format=JPEG source_size=%s target_size=%s", len(content), len(normalized))
    return normalized
