from __future__ import annotations

import re
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_RE = re.compile(r"[\r\n\t]+")
_MULTI_SPACE_RE = re.compile(r"\s+")


def sanitize_market_product_name(name: Any, max_length: int = 100) -> str:
    if name is None:
        return ""
    s = str(name)
    s = _TAG_RE.sub(" ", s)
    s = _CONTROL_RE.sub(" ", s)
    s = _MULTI_SPACE_RE.sub(" ", s).strip()
    if max_length and len(s) > max_length:
        s = s[:max_length].rstrip()
    return s


def apply_market_name_rules(
    name: Any,
    forbidden_keywords: list[str] | None = None,
    replacements: dict[str, str] | None = None,
    max_length: int = 100,
) -> str:
    base = sanitize_market_product_name(name, max_length=max_length)
    if not base:
        return base

    processed = base

    if replacements:
        for src, dst in replacements.items():
            if not src:
                continue
            processed = processed.replace(str(src), str(dst))

    if forbidden_keywords:
        for keyword in forbidden_keywords:
            if not keyword:
                continue
            processed = re.sub(re.escape(str(keyword)), " ", processed, flags=re.IGNORECASE)

    processed = _MULTI_SPACE_RE.sub(" ", processed).strip()
    if not processed:
        return base
    if max_length and len(processed) > max_length:
        processed = processed[:max_length].rstrip()
    return processed
