from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

try:
    from PIL import Image
except Exception:
    Image = None


@dataclass
class ImageValidationResult:
    ok: bool
    width: int | None
    height: int | None
    size_bytes: int
    reason: str | None = None


def validate_image_bytes(content: bytes) -> ImageValidationResult:
    size_bytes = len(content or b"")
    if size_bytes <= 0:
        return ImageValidationResult(False, None, None, size_bytes, "empty")
    if size_bytes > 10 * 1024 * 1024:
        return ImageValidationResult(False, None, None, size_bytes, "too_large")
    if Image is None:
        return ImageValidationResult(True, None, None, size_bytes, "pil_unavailable")
    try:
        with Image.open(BytesIO(content)) as img:
            width, height = img.size
    except Exception:
        return ImageValidationResult(False, None, None, size_bytes, "invalid_image")

    if width < 500 or height < 500:
        return ImageValidationResult(False, width, height, size_bytes, "too_small")
    if width > 5000 or height > 5000:
        return ImageValidationResult(False, width, height, size_bytes, "too_large_dimensions")

    return ImageValidationResult(True, width, height, size_bytes, None)
