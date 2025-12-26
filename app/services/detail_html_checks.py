from __future__ import annotations

import re
from typing import Any


FORBIDDEN_TAGS = {"script", "iframe", "object", "embed"}
_TAG_RE = re.compile(r"<\s*([a-zA-Z0-9:_-]+)")
_FORBIDDEN_TAG_RE = re.compile(
    r"<(script|iframe|object|embed)\b[^>]*>.*?</\1>|<(script|iframe|object|embed)\b[^>]*/>",
    re.IGNORECASE | re.DOTALL
)


def find_forbidden_tags(html: Any) -> list[str]:
    if html is None:
        return []
    text = str(html)
    if not text:
        return []
    tags: set[str] = set()
    for match in _TAG_RE.finditer(text):
        tag = match.group(1).lower()
        if tag in FORBIDDEN_TAGS:
            tags.add(tag)
    return sorted(tags)


def strip_forbidden_tags(html: str) -> str:
    """
    상세페이지에서 금지된 태그(script, iframe 등)를 제거합니다.
    """
    if not html:
        return html
    return _FORBIDDEN_TAG_RE.sub("", html)
