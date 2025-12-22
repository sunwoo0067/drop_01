from __future__ import annotations

from pathlib import Path
from typing import Any
import json
from datetime import datetime, timezone


STATE_PATH = Path("workplan/scheduler_state.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_scheduler_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def update_scheduler_state(name: str, status: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    state = read_scheduler_state()
    entry = {
        "status": status,
        "updated_at": _now_iso(),
    }
    if meta:
        entry["meta"] = meta
    state[name] = entry
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state
