"""Real save/quit/restart/ending/export acceptance on the canonical game engine."""
from __future__ import annotations

from pathlib import Path
import tempfile

from .acceptance import acceptance_actions
from .campaign_acceptance import LAST_SIGNAL
from .campaign import verify_export
from .consumer_store import SlotStore

CONTRACT = "ridge.rescue.consumer.acceptance.v1"


def run_acceptance(root: Path | None = None) -> dict:
    if root is None:
        with tempfile.TemporaryDirectory(prefix="cinder-ridge-acceptance-") as temp:
            return run_acceptance(Path(temp) / "save")
    store = SlotStore(root)
    session = store.new("consumer-acceptance")
    if session["status"] != "playing" or session["revision"] != 0:
        raise ValueError("new consumer session did not start")
    total = 0
    for index, sequence in enumerate((acceptance_actions("protect"), LAST_SIGNAL)):
        for action in sequence:
            # Every move crosses a real database commit, close, and reopen.
            current = SlotStore(root).load("consumer-acceptance")
            if current["head"] != session["head"] or current["index"] != index:
                raise ValueError("restart lost chapter or revision")
            session = SlotStore(root).step("consumer-acceptance", action, expected_head=current["head"])
            total += 1
        if session["index"] != index + 1:
            raise ValueError("chapter ending was not earned")
    final = SlotStore(root).load("consumer-acceptance")
    if final["status"] != "completed" or final["index"] != 2:
        raise ValueError("campaign did not complete")
    audit = SlotStore(root).audit("consumer-acceptance")
    if audit["revision"] != total or audit["audit_entries"] != total:
        raise ValueError("transactional save history mismatch")
    exported = SlotStore(root).export("consumer-acceptance")
    restored = verify_export(exported.read_bytes())
    if restored["head"] != final["head"] or restored["status"] != "completed":
        raise ValueError("portable campaign export failed replay")
    return {"schema": CONTRACT, "status": "verified-in-process",
            "chapters": final["index"], "actions": total,
            "restart_count": total, "saved_revision": final["revision"],
            "head": final["head"], "portable_export_verified": True,
            "release_certified": False, "windows_device_certified": False,
            "exact_head_ci_certified": False}
