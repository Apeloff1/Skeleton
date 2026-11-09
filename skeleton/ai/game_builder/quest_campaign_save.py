"""Crash-safe, independently replayed original Director campaign saves.

These are authenticated-to-the-supplied-world *logic* checkpoints, not a
Godot or native game-save implementation. SHA-256 is not a creator signature.
Never load untrusted serialized DirectorState directly into live authority.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .quest_scene_engine import DirectorWorld, DirectorState
from .quest_playthrough_journal import replay_director_segments
from .quest_campaign_completion import CampaignWitness

SCHEMA = "skeleton.game_builder.director_campaign_save.v1"
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_SAVE_BYTES = 16 * 1024 * 1024


class CampaignSaveError(ValueError):
    """Untrusted, foreign, incomplete, overwritten, or modified save refused."""


def _hash(obj: object) -> str:
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise CampaignSaveError("ambiguous duplicate save field")
        obj[key] = value
    return obj


def _path(root: Path, name: str, *, create: bool) -> Path:
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise CampaignSaveError("invalid original save identity")
    base = root / "design"
    folder = base / "campaign_saves"
    if root.is_symlink() or base.is_symlink() or folder.is_symlink():
        raise CampaignSaveError("symlinked project or save directory refused")
    if not root.is_dir() or not base.is_dir():
        raise CampaignSaveError("existing original game project required")
    if create:
        folder.mkdir(mode=0o700, exist_ok=True)
    if not folder.is_dir() or folder.is_symlink():
        raise CampaignSaveError("campaign save directory is not a regular directory")
    return folder / (name + ".json")


def write_campaign_save(root: Path, name: str, world: DirectorWorld,
                        witness: CampaignWitness) -> dict[str, Any]:
    """Persist a complete action journal, never a forged privileged state."""
    if not isinstance(world, DirectorWorld) or not isinstance(witness, CampaignWitness):
        raise CampaignSaveError("original DirectorWorld and executed campaign required")
    packet = {
        "schema": SCHEMA,
        "project": world.project_id,
        "director_world_digest": world.digest,
        "replay": witness.replay,
        "final_state_sha256": witness.report["final_director_state_sha256"],
    }
    # Independently replay prior to persisting; a locally invented success
    # flag or final digest cannot bypass original Director transition checks.
    checked = replay_director_segments(world, packet["replay"]["segments"])
    if checked.final.digest != packet["final_state_sha256"]:
        raise CampaignSaveError("campaign final state is not backed by playable actions")
    packet["receipt_sha256"] = _hash(packet)
    encoded = (json.dumps(packet, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    if len(encoded) > MAX_SAVE_BYTES:
        raise CampaignSaveError("save exceeds per-file admission budget; split project journal")
    destination = _path(root, name, create=True)
    if destination.is_symlink() or destination.exists():
        raise CampaignSaveError("original campaign save already exists; no implicit overwrite")
    temp: str | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".campaign-", dir=destination.parent,
                                         delete=False) as file:
            temp = file.name
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        os.link(temp, destination)  # atomic create-only, never overwrite
    finally:
        if temp is not None and os.path.lexists(temp):
            os.unlink(temp)
    return {
        "ok": True, "path": str(destination),
        "receipt_sha256": packet["receipt_sha256"],
        "final_state_sha256": checked.final.digest,
        "native_or_godot_save_certified": False,
    }


def read_campaign_save(root: Path, name: str, world: DirectorWorld) -> DirectorState:
    """Restore exact legal state by replay from genesis, not by trusting a save."""
    if not isinstance(world, DirectorWorld):
        raise CampaignSaveError("typed original DirectorWorld required")
    path = _path(root, name, create=False)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SAVE_BYTES:
        raise CampaignSaveError("missing, unsafe or oversized original campaign save")
    with path.open("rb") as reader:
        raw = reader.read(MAX_SAVE_BYTES + 1)
    if len(raw) > MAX_SAVE_BYTES:
        raise CampaignSaveError("save changed size during admission")
    try:
        data = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              CampaignSaveError("non-finite save number rejected")))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise CampaignSaveError("malformed original save JSON") from exc
    if not isinstance(data, dict) or set(data) != {
        "schema", "project", "director_world_digest", "replay",
        "final_state_sha256", "receipt_sha256",
    } or data["schema"] != SCHEMA:
        raise CampaignSaveError("unrecognized game save contract")
    if data["project"] != world.project_id or data["director_world_digest"] != world.digest:
        raise CampaignSaveError("save was made for a different original game world")
    receipt = data.pop("receipt_sha256")
    if not isinstance(receipt, str) or receipt != _hash(data):
        raise CampaignSaveError("original campaign save receipt mismatch")
    replay = data["replay"]
    if not isinstance(replay, dict) or set(replay) != {"name", "segments"}:
        raise CampaignSaveError("save lacks typed original gameplay journal")
    checked = replay_director_segments(world, replay["segments"])
    if checked.final.digest != data["final_state_sha256"]:
        raise CampaignSaveError("restored original game state fails replay proof")
    return checked.final
