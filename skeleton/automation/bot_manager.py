"""Conservative scheduler and circuit breaker for repository bots."""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .advanced_bots import ADVANCED_BOTS

STATE = Path(".skeleton-bot-state.json")
MAX_CONCURRENT = 3
COOLDOWN_SECONDS = 6 * 60 * 60
FAILURE_THRESHOLD = 3
MAX_HISTORY = 32
MAX_HISTORY_AGE_SECONDS = 7 * 24 * 60 * 60


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


def _default_state() -> dict[str, dict]:
    return {
        name: asdict(BotHealth(name))
        for name in DEFAULT_BOTS
    }


def _normalize_item(name: str, value: object) -> dict:
    default = asdict(BotHealth(name))
    if not isinstance(value, dict):
        return default

    enabled = value.get("enabled", True)
    circuit_open = value.get("circuit_open", False)
    failures = value.get("failures", 0)
    last_run = value.get("last_run", 0.0)

    if not isinstance(enabled, bool):
        enabled = True
    if not isinstance(circuit_open, bool):
        circuit_open = False
    if (
        isinstance(failures, bool)
        or not isinstance(failures, int)
        or failures < 0
    ):
        failures = 0
    if (
        isinstance(last_run, bool)
        or not isinstance(last_run, (int, float))
        or not math.isfinite(float(last_run))
        or float(last_run) < 0
    ):
        last_run = 0.0

    return {
        "name": name,
        "enabled": enabled,
        "failures": failures,
        "last_run": float(last_run),
        "circuit_open": circuit_open,
    }


def normalize_state(value: object) -> dict[str, dict]:
    """Keep only registered bot state with bounded primitive fields."""
    source = value if isinstance(value, dict) else {}
    return {
        name: _normalize_item(name, source.get(name))
        for name in DEFAULT_BOTS
    }


def load_state() -> dict[str, dict]:
    if STATE.is_symlink():
        return _default_state()
    if not STATE.exists():
        return _default_state()
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _default_state()
    return normalize_state(data)


def save_state(state: dict[str, dict]) -> None:
    """Atomically publish normalized bot state without a predictable temp path."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    rendered = (
        json.dumps(
            normalize_state(state),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    fd, raw_tmp = tempfile.mkstemp(
        prefix=f".{STATE.name}.",
        suffix=".tmp",
        dir=STATE.parent,
        text=True,
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, STATE)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        finally:
            raise


def _due_from(
    names: list[str],
    state: dict[str, dict],
    now: float,
) -> list[str]:
    due: list[str] = []
    normalized = normalize_state(state)
    for name in names:
        item = normalized.get(
            name,
            asdict(BotHealth(name)),
        )
        if (
            item["enabled"]
            and not item["circuit_open"]
            and now - float(item["last_run"]) >= COOLDOWN_SECONDS
        ):
            due.append(name)
    return due


def select_due(
    state: dict[str, dict],
    now: float | None = None,
) -> list[str]:
    moment = time.time() if now is None else now
    return _due_from(
        list(DEFAULT_BOTS),
        state,
        moment,
    )[:MAX_CONCURRENT]


def authorized_builder_available(
    state: dict[str, dict],
) -> bool:
    """Allow approved build work to bypass cooldown, never circuit/disable state."""
    normalized = normalize_state(state)
    item = normalized.get(
        "feature-builder",
        asdict(BotHealth("feature-builder")),
    )
    return bool(
        item["enabled"]
        and not item["circuit_open"]
    )


def select_specialists_due(
    state: dict[str, dict],
    now: float | None = None,
) -> list[str]:
    """Return every due specialist; Secretary applies the assignment cap.

    Truncating this list before routing biases selection toward registry order and
    can starve a high-signal specialist such as security-auditor.  The Secretary
    is the correct layer for the final MAX_ASSIGNMENTS bound.
    """
    moment = time.time() if now is None else now
    return _due_from(
        list(SPECIALIST_BOTS),
        state,
        moment,
    )


def record_result(
    state: dict[str, dict],
    name: str,
    success: bool,
    now: float | None = None,
) -> None:
    if name not in DEFAULT_BOTS:
        raise ValueError("cannot record unregistered bot")
    moment = time.time() if now is None else now
    normalized = normalize_state(state)
    state.clear()
    state.update(normalized)
    item = state[name]
    item["last_run"] = float(moment)
    if success:
        item["failures"] = 0
        item["circuit_open"] = False
    else:
        item["failures"] = int(item["failures"]) + 1
        if item["failures"] >= FAILURE_THRESHOLD:
            item["circuit_open"] = True



SUCCESSFUL_WORKER_STATUSES = frozenset({
    "existing-pr",
    "no-change",
    "pull-request-created",
    "pull-request-updated",
})


def record_worker_outcome(
    state: dict[str, dict],
    result: object,
    now: float | None = None,
) -> None:
    """Account for one Secretary result using admitted semantic evidence.

    A zero process exit without admitted evidence is not success. Conversely,
    deduplication and a legitimate no-op are successful autonomous outcomes and
    must not poison the circuit breaker merely because no new commit was made.
    """
    if not isinstance(result, dict):
        raise ValueError("worker outcome must be an object")
    name = result.get("bot")
    if not isinstance(name, str) or name not in DEFAULT_BOTS:
        raise ValueError("worker outcome has unregistered bot")
    returncode = result.get("returncode")
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise ValueError("worker outcome has invalid return code")
    evidence = result.get("evidence")
    success = False
    if returncode == 0 and isinstance(evidence, dict):
        success = (
            evidence.get("bot") == name
            and evidence.get("status") in SUCCESSFUL_WORKER_STATUSES
        )
    record_result(state, name, success, now=now)



def bounded_health_summary(
    state: object,
    *,
    now: float | None = None,
) -> dict[str, object]:
    """Return non-authoritative health telemetry safe for planning context."""
    moment = time.time() if now is None else float(now)
    normalized = normalize_state(state)
    workers: list[dict[str, object]] = []
    for name in sorted(normalized):
        item = normalized[name]
        last_run = float(item["last_run"])
        age = None if last_run <= 0 else max(0, int(moment - last_run))
        workers.append({
            "name": name,
            "enabled": bool(item["enabled"]),
            "failures": int(item["failures"]),
            "circuit_open": bool(item["circuit_open"]),
            "seconds_since_last_run": age,
        })
    return {
        "version": 1,
        "non_authoritative": True,
        "worker_count": len(workers),
        "workers": workers,
    }


def main() -> int:
    state = load_state()
    due = select_due(state)
    specialists = select_specialists_due(state)
    save_state(state)
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
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
