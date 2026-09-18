"""Conservative scheduler and circuit breaker for repository bots."""
from __future__ import annotations

import json
import os
import time
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .advanced_bots import ADVANCED_BOTS

STATE = Path(".skeleton-bot-state.json")
MAX_CONCURRENT = 3
COOLDOWN_SECONDS = 6 * 60 * 60


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


def load_state() -> dict[str, dict]:
    if not STATE.exists():
        return {name: asdict(BotHealth(name)) for name in DEFAULT_BOTS}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, dict]) -> None:
    """Atomically publish bot state without a predictable temporary path."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(state, indent=2, sort_keys=True) + "\n"
    fd, raw_tmp = tempfile.mkstemp(
        prefix=f".{STATE.name}.",
        suffix=".tmp",
        dir=STATE.parent,
        text=True,
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, STATE)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        finally:
            raise


def _due_from(names: list[str], state: dict[str, dict], now: float) -> list[str]:
    due = []
    for name in names:
        item = state.get(name, asdict(BotHealth(name)))
        if item.get("enabled", True) and not item.get("circuit_open", False):
            if now - float(item.get("last_run", 0)) >= COOLDOWN_SECONDS:
                due.append(name)
    return due


def select_due(state: dict[str, dict], now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    return _due_from(list(DEFAULT_BOTS), state, now)[:MAX_CONCURRENT]


def select_specialists_due(state: dict[str, dict], now: float | None = None) -> list[str]:
    """Return an independent specialist lane for the secretary."""
    now = time.time() if now is None else now
    return _due_from(list(SPECIALIST_BOTS), state, now)[:MAX_CONCURRENT]


def record_result(state: dict[str, dict], name: str, success: bool, now: float | None = None) -> None:
    now = time.time() if now is None else now
    item = state.setdefault(name, asdict(BotHealth(name)))
    item["last_run"] = now
    if success:
        item["failures"] = 0
        item["circuit_open"] = False
    else:
        item["failures"] = int(item.get("failures", 0)) + 1
        if item["failures"] >= 3:
            item["circuit_open"] = True


def main() -> int:
    state = load_state()
    due = select_due(state)
    specialists = select_specialists_due(state)
    save_state(state)
    print(json.dumps({"due": due, "specialists_due": specialists, "bot_count": len(DEFAULT_BOTS), "specialist_count": len(SPECIALIST_BOTS), "max_concurrent": MAX_CONCURRENT}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
