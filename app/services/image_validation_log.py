from __future__ import annotations

import re
from typing import Iterable


_LOG_RE = re.compile(
    r"이미지 검증 실패\(url=(?P<url>[^,]+), reason=(?P<reason>[^,]+), size=(?P<size>[^,]+), width=(?P<width>[^,]+), height=(?P<height>[^)]+)\)"
)


def parse_validation_failures(lines: Iterable[str]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for line in lines:
        match = _LOG_RE.search(line)
        if not match:
            continue
        results.append({
            "url": match.group("url").strip(),
            "reason": match.group("reason").strip(),
            "size": match.group("size").strip(),
            "width": match.group("width").strip(),
            "height": match.group("height").strip(),
        })
    return results
