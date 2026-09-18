"""Conservative scheduler and circuit breaker for repository bots."""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .advanced_bots import ADVANCED_BOTS

STATE = Path(".skeleton-bot-state.json")
MAX_CONCURRENT = 3
COOLDOWN_SECONDS = 6 * 60 * 60
MAX_FAILURES = 3


@dataclass(frozen=True)
class BotHealth:
    name: str
    enabled: bool = True
    failures: int = 0
    last_run: float = 0.0
    circuit_open: bool = False


BASE_BOTS = {
    "triage": "issue triage and bounded repair proposals",
    "ci": "CI diagnosis and focused repair",
    "security": "security regression review",
    "cleanup": "safe repository cleanup",
}
SPECIALIST_BOTS = {bot.name: bot.trigger for bot in ADVANCED_BOTS}
DEFAULT_BOTS = {**BASE_BOTS, **SPECIALIST_BOTS}


def _default_state() -> dict[str, dict[str, Any]]:
    return {name: asdict(BotHealth(name)) for name in DEFAULT_BOTS}


def _normalise_item(name: str, raw: object) -> dict[str, Any]:
    default = asdict(BotHealth(name))
    if not isinstance(raw, dict):
        return default

    enabled = raw.get("enabled", True)
    failures = raw.get("failures", 0)
    last_run = raw.get("last_run", 0.0)
    circuit_open = raw.get("circuit_open", False)

    if not isinstance(enabled, bool):
        enabled = True
    if isinstance(failures, bool) or not isinstance(failures, int):
        failures = 0
    failures = max(0, min(failures, MAX_FAILURES))
    if isinstance(last_run, bool) or not isinstance(last_run, (int, float)):
        last_run = 0.0
    last_run = float(last_run)
    if not math.isfinite(last_run) or last_run < 0.0:
        last_run = 0.0
    if not isinstance(circuit_open, bool):
        circuit_open = failures >= MAX_FAILURES

    return {
        "name": name,
        "enabled": enabled,
        "failures": failures,
        "last_run": last_run,
        "circuit_open": circuit_open,
    }


def normalise_state(raw: object) -> dict[str, dict[str, Any]]:
    source = raw if isinstance(raw, dict) else {}
    return {name: _normalise_item(name, source.get(name)) for name in DEFAULT_BOTS}


def load_state() -> dict[str, dict[str, Any]]:
    if not STATE.exists():
        return _default_state()
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_state()
    return normalise_state(data)


def save_state(state: dict[str, dict[str, Any]]) -> None:
    payload = normalise_state(state)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, raw_tmp = tempfile.mkstemp(
        prefix=f".{STATE.name}.",
        suffix=".tmp",
        dir=STATE.parent,
        text=True,
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = -1
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, STATE)
    finally:
        if fd >= 0:
            os.close(fd)
        tmp.unlink(missing_ok=True)


def _due_from(names: list[str], state: dict[str, dict[str, Any]], now: float) -> list[str]:
    if not math.isfinite(now) or now < 0.0:
        raise ValueError("now must be a finite non-negative timestamp")
    due = []
    for name in names:
        item = _normalise_item(name, state.get(name))
        if item["enabled"] and not item["circuit_open"]:
            if now - item["last_run"] >= COOLDOWN_SECONDS:
                due.append(name)
    return due


def select_base_due(
    state: dict[str, dict[str, Any]],
    now: float | None = None,
) -> list[str]:
    now = time.time() if now is None else now
    return _due_from(list(BASE_BOTS), state, now)[:MAX_CONCURRENT]


def select_due(
    state: dict[str, dict[str, Any]],
    now: float | None = None,
) -> list[str]:
    now = time.time() if now is None else now
    return _due_from(list(DEFAULT_BOTS), state, now)[:MAX_CONCURRENT]


def select_specialists_due(
    state: dict[str, dict[str, Any]],
    now: float | None = None,
) -> list[str]:
    """Return an independent specialist lane for the secretary."""
    now = time.time() if now is None else now
    return _due_from(list(SPECIALIST_BOTS), state, now)[:MAX_CONCURRENT]


def record_result(
    state: dict[str, dict[str, Any]],
    name: str,
    success: bool,
    now: float | None = None,
) -> None:
    if name not in DEFAULT_BOTS:
        raise ValueError("unknown bot")
    if not isinstance(success, bool):
        raise ValueError("success must be boolean")
    now = time.time() if now is None else now
    if not math.isfinite(now) or now < 0.0:
        raise ValueError("now must be a finite non-negative timestamp")

    item = state.setdefault(name, asdict(BotHealth(name)))
    item.update(_normalise_item(name, item))
    item["last_run"] = now
    if success:
        item["failures"] = 0
        item["circuit_open"] = False
    else:
        item["failures"] = min(MAX_FAILURES, int(item["failures"]) + 1)
        if item["failures"] >= MAX_FAILURES:
            item["circuit_open"] = True


def main() -> int:
    state = load_state()
    due = select_base_due(state)
    specialists = select_specialists_due(state)
    print(
        json.dumps(
            {
                "due": due,
                "specialists_due": specialists,
                "bot_count": len(DEFAULT_BOTS),
                "specialist_count": len(SPECIALIST_BOTS),
                "max_concurrent": MAX_CONCURRENT,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
