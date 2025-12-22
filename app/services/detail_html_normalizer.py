import re

_OWNERCLAN_BREAK_RE = re.compile(r"_x000D_|_x000A_|_x0009_", re.IGNORECASE)


def normalize_ownerclan_html(html: str) -> str:
    s = str(html or "")
    if not s:
        return s
    return _OWNERCLAN_BREAK_RE.sub("", s)
