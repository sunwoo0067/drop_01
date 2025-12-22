from __future__ import annotations

import re
from typing import Any


FORBIDDEN_TAGS = {"script", "iframe", "object", "embed"}
_TAG_RE = re.compile(r"<\s*([a-zA-Z0-9:_-]+)")


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
