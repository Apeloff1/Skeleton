"""Accept checks for GB-28."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.chronicle.capabilities import capabilities
from skeleton.chronicle.engine import ChronicleEngine
from skeleton.chronicle.helix import Helix


def check_three(path: Path) -> None:
    h = Helix(path)
    h.append("observe", "a")
    h.append("forge", "b")
    h.append("gossip", "c")
    if len(h.records()) != 3 or not h.verify():
        raise AssertionError("three")


def check_tamper(path: Path) -> None:
    h = Helix(path)
    if len(h.records()) < 3:
        h.append("observe", "a")
        h.append("forge", "b")
        h.append("gossip", "c")
    h.tamper(1, "mutated")
    if h.verify():
        raise AssertionError("tamper")


def check_caps() -> None:
    cap = capabilities()
    if cap["contract"]["coin"] != 0 or cap["contract"]["network"] != 0:
        raise AssertionError("cap")


def check_engine(path: Path) -> None:
    card = ChronicleEngine().snapshot(path)
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all(root: Path) -> dict[str, Any]:
    failed: list[str] = []
    try:
        check_three(root / "helix.jsonl")
    except Exception as exc:
        failed.append("check_three:" + type(exc).__name__)
    try:
        check_tamper(root / "helix_tamper.jsonl")
    except Exception as exc:
        failed.append("check_tamper:" + type(exc).__name__)
    try:
        check_caps()
    except Exception as exc:
        failed.append("check_caps:" + type(exc).__name__)
    try:
        check_engine(root / "helix_engine.jsonl")
    except Exception as exc:
        failed.append("check_engine:" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 4}
