from __future__ import annotations

from collections import Counter
import json
from typing import Iterable


def parse_validation_failures_from_logs(lines: Iterable[str]) -> dict[str, int]:
    """
    Parse 'validationFailures' dicts from image_processing logs.
    """
    counts: Counter[str] = Counter()
    for line in lines:
        if "validationFailures=" not in line:
            continue
        tail = line.split("validationFailures=", 1)[1]
        if "}" not in tail:
            continue
        raw = tail.split("}", 1)[0] + "}"
        try:
            raw = raw.replace("'", "\"")
            data = json.loads(raw)
            if isinstance(data, dict):
                for k, v in data.items():
                    try:
                        counts[str(k)] += int(v)
                    except Exception:
                        continue
        except Exception:
            continue
    return dict(counts)
