"""Accept checks for GB-27. Both gates."""

from __future__ import annotations

from typing import Any

from skeleton.persist.capabilities import capabilities
from skeleton.persist.engine import PersistEngine
from skeleton.persist.store import Persist


def check_local() -> None:
    p = Persist(env={})
    p.put("deck", "a", "1")
    if p.gate() != "local" or not p.has_local("deck", "a"):
        raise AssertionError("local")
    if any(p.disk_paths().values()):
        raise AssertionError("local-disk")


def check_disk(root: str) -> None:
    p = Persist(env={"SKELETON_OWN": root})
    p.put("helix", "k", "v")
    p.put("rotors", "r", "1")
    p.put("traces", "t", "x")
    paths = p.disk_paths()
    if p.gate() != "disk" or not all(paths.values()):
        raise AssertionError("disk")


def check_one_core() -> None:
    if capabilities()["contract"]["cores"] != 1:
        raise AssertionError("core")


def check_engine() -> None:
    card = PersistEngine().snapshot()
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all(disk_root: str | None = None) -> dict[str, Any]:
    failed: list[str] = []
    try:
        check_local()
    except Exception as exc:
        failed.append("check_local:" + type(exc).__name__)
    if disk_root:
        try:
            check_disk(disk_root)
        except Exception as exc:
            failed.append("check_disk:" + type(exc).__name__)
    for fn in (check_one_core, check_engine):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 4}
