"""Real save/quit/restart/ending/export acceptance on the canonical game engine."""
from __future__ import annotations

from pathlib import Path
import tempfile

from .acceptance import acceptance_actions
from .campaign_acceptance import LAST_SIGNAL
from .campaign import verify_export
from .consumer_store import SlotStore

CONTRACT = "ridge.rescue.consumer.acceptance.v1"



def _interactive_contract(root: Path, actions: list[dict]) -> dict:
    """Play the actual numbered terminal interface, quit, reopen and win."""
    from .consumer_cli import play
    slot = "interactive-acceptance"
    split = max(1, len(actions) // 2)
    positions = iter(actions)
    prompts = [0]
    frames = [0]

    def command(*, limit: int):
        def choose(_: str) -> str:
            if prompts[0] >= limit:
                return "q"
            state = SlotStore(root).load(slot)
            desired = next(positions)
            if desired not in state["actions"]:
                raise ValueError("terminal action not offered by canonical engine")
            prompts[0] += 1
            return str(state["actions"].index(desired))
        return choose

    def screen(message: str) -> None:
        if "Actions:" in message or "Campaign complete" in message:
            frames[0] += 1

    halfway = play(SlotStore(root), slot, read=command(limit=split), write=screen)
    if halfway["revision"] != split or halfway["status"] != "playing":
        raise ValueError("interactive quit failed to persist last turn")
    completed = play(SlotStore(root), slot, read=command(limit=len(actions)), write=screen)
    if completed["status"] != "completed" or completed["revision"] != len(actions):
        raise ValueError("interactive restart did not reach earned ending")
    if frames[0] < len(actions):
        raise ValueError("terminal did not render playable action frames")
    return {"commands": prompts[0], "frames": frames[0], "head": completed["head"]}


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
    # A consumer backup must preserve the transactional action ledger, not
    # merely the last rendered scene. Cold-restore and independently replay.
    backup_path = SlotStore(root).backup("consumer-acceptance")
    backup_bytes = backup_path.read_bytes()
    from .consumer_backup import verify_backup
    from .consumer_store import _source
    backed_up, history = verify_backup(backup_bytes, _source())
    if backed_up["head"] != final["head"] or len(history) != total:
        raise ValueError("full backup did not replay the completed campaign")
    recovered = SlotStore(root).restore_backup("consumer-recovered", backup_bytes)
    recovered_audit = SlotStore(root).audit("consumer-recovered")
    if (recovered["head"] != final["head"] or recovered["status"] != "completed"
            or recovered_audit["audit_entries"] != total
            or not recovered_audit["verified"]):
        raise ValueError("cold-reopened backup restore lost ending or history")
    if SlotStore(root).load("consumer-acceptance")["head"] != final["head"]:
        raise ValueError("backup restore mutated the original save")
    terminal = _interactive_contract(root, acceptance_actions("protect") + LAST_SIGNAL)
    if terminal["head"] != final["head"]:
        raise ValueError("interactive and API game outcomes diverged")
    return {"schema": CONTRACT, "status": "verified-in-process",
            "chapters": final["index"], "actions": total,
            "restart_count": total, "saved_revision": final["revision"],
            "head": final["head"], "portable_export_verified": True,
            "terminal_commands": terminal["commands"], "terminal_frames": terminal["frames"],
            "interactive_quit_restart_verified": True,
            "backup_restore_replay_verified": True,
            "release_certified": False, "windows_device_certified": False,
            "exact_head_ci_certified": False}
