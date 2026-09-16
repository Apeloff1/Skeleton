"""Conservative scheduler and circuit breaker for repository bots."""
from __future__ import annotations

import json
import os
import time
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
DEFAULT_BOTS = {**BASE_BOTS, **{bot.name: bot.trigger for bot in ADVANCED_BOTS}}


def load_state() -> dict[str, dict]:
    if not STATE.exists():
        return {name: asdict(BotHealth(name)) for name in DEFAULT_BOTS}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, dict]) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, STATE)


def select_due(state: dict[str, dict], now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    due = []
    for name in DEFAULT_BOTS:
        item = state.get(name, asdict(BotHealth(name)))
        if item.get("enabled", True) and not item.get("circuit_open", False):
            if now - float(item.get("last_run", 0)) >= COOLDOWN_SECONDS:
                due.append(name)
    return due[:MAX_CONCURRENT]


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
    save_state(state)
    print(json.dumps({"due": due, "bot_count": len(DEFAULT_BOTS), "max_concurrent": MAX_CONCURRENT}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
