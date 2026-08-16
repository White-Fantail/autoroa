import hashlib
import io
import logging
import warnings

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)
SUPPORTED_IMAGE_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


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
    """Fully decode image pixels and validate the decoded format against the declared MIME.

    Pillow's ``verify()`` is intentionally not used here. It performs a second,
    stricter structural pass that can reject browser-generated JPEGs containing
    otherwise harmless ancillary metadata even though Pillow can fully decode
    their pixels. A successful ``load()`` is the trust boundary we need for OCR.
    """
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
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
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
        "image_validation_ok declared_mime=%s actual_mime=%s width=%s height=%s size=%s signature=%s",
        declared_mime,
        actual_mime,
        width,
        height,
        len(content),
        _signature(content),
    )
    return width, height, hashlib.sha256(content).hexdigest()
