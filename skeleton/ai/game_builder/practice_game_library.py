"""Original, offline-playable Dragon practice games under the canonical game-builder owner.

Each shipped puzzle has concrete tile geometry and a replayable proof. Packs
contain no third-party game assets, scraped text, network links, executable
scripts or unverified console binaries. Research/memory promotion and native
release qualification remain separate authorities.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat

from .contracts import canonical_digest, canonical_json
from .playable_world import (
    GameBuildIntent, PlayableWorld, PlayableWorldError, TileLevel,
)
from .playable_simulation import GameReplay, demonstrate_solvable
from .playable_export import PlayableHTML, render_playable_world

PACK_ROOT = Path(__file__).with_name("practice_games")
PACK_SCHEMA = "skeleton.dragon.original_practice_game.v1"
MAX_PRACTICE_GAME_BYTES = 16 * 1024
_GAME_ID = re.compile(r"dragon-practice-[0-9]{3}\Z")


class PracticeGameError(ValueError):
    """Invalid bounded original practice game or its verified witness."""


@dataclass(frozen=True, slots=True)
class OriginalPracticeGame:
    game_id: str
    world: PlayableWorld
    proof: GameReplay
    source_digest: str
    originality_status: str = "original_algorithmic_no_external_media"
    release_state: str = "practice_only_not_hardware_verified"

    @property
    def world_digest(self) -> str:
        return self.world.digest

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "skeleton.dragon.original_practice_receipt.v1",
            "game_id": self.game_id,
            "source_digest": self.source_digest,
            "world_digest": self.world.digest,
            "proof_digest": self.proof.digest,
            "proof_actions": len(self.proof.action_receipts),
            "gameplay_verified": self.proof.final_state.status == "won",
            "independent_device_verified": False,
            "release_authorized": False,
            "training_authorized": False,
            "memory_promotion_authorized": False,
        }


def list_practice_games(*, authorized: bool) -> tuple[str, ...]:
    if authorized is not True:
        raise PermissionError("practice game inventory requires authorization")
    if not PACK_ROOT.is_dir() or PACK_ROOT.is_symlink():
        raise PracticeGameError("practice game library unavailable")
    ids = sorted(
        path.stem for path in PACK_ROOT.iterdir()
        if path.name.endswith(".json") and
        _GAME_ID.fullmatch(path.stem)
    )
    if len(ids) > 100 or len(set(ids)) != len(ids):
        raise PracticeGameError("practice game inventory exceeds declared budget")
    return tuple(ids)


def _pairs_unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise PracticeGameError("duplicate practice pack key")
        obj[key] = value
    return obj


def _reject_float_constant(value: str) -> None:
    raise PracticeGameError("nonfinite practice game number")


def load_practice_game(game_id: str, *, authorized: bool) -> OriginalPracticeGame:
    if authorized is not True:
        raise PermissionError("practice game loading requires authorization")
    if type(game_id) is not str or _GAME_ID.fullmatch(game_id) is None:
        raise PracticeGameError("invalid original practice game id")
    if game_id not in list_practice_games(authorized=True):
        raise PracticeGameError("unknown original practice game")
    path = PACK_ROOT / (game_id + ".json")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_PRACTICE_GAME_BYTES:
            raise PracticeGameError("practice game must be bounded regular source")
        flags = (
            os.O_RDONLY | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as source:
            opened = os.fstat(source.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or (before.st_dev, before.st_ino) !=
                    (opened.st_dev, opened.st_ino)):
                raise PracticeGameError("practice game replaced during admission")
            raw = source.read(MAX_PRACTICE_GAME_BYTES + 1)
            after = os.fstat(source.fileno())
        current = path.lstat()
        if (not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)):
            raise PracticeGameError("practice game path changed during read")
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise PracticeGameError("practice game modified during source admission")
    except OSError as exc:
        raise PracticeGameError("practice game file unavailable") from exc
    if not 0 < len(raw) <= MAX_PRACTICE_GAME_BYTES or len(raw) != before.st_size:
        raise PracticeGameError("practice game changed or exceeded byte budget")
    try:
        body = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=_pairs_unique,
            parse_constant=_reject_float_constant,
        )
        if type(body) is not dict or canonical_json(body).encode("ascii") + b"\n" != raw:
            raise PracticeGameError("practice game source not canonical")
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise PracticeGameError("practice game JSON integrity invalid") from exc
    if set(body) != {
        "schema", "intent", "rows", "safe_solution",
        "originality_status", "release_state",
    } or body["schema"] != PACK_SCHEMA:
        raise PracticeGameError("unknown practice game schema")
    if body["originality_status"] != "original_algorithmic_no_external_media" or (
        body["release_state"] != "practice_only_not_hardware_verified"
    ):
        raise PracticeGameError("practice game claims unauthorized provenance or release")
    fields = body["intent"]
    if type(fields) is not dict or set(fields) != {
        "project_id", "title", "subtitle", "seed", "width", "height",
        "levels", "collectibles_per_level", "hazards_per_level",
        "theme", "starting_health",
    } or fields["project_id"] != game_id or fields["levels"] != 1:
        raise PracticeGameError("practice game intent contract invalid")
    try:
        intent = GameBuildIntent(**fields)
        rows = body["rows"]
        actions = body["safe_solution"]
        if (type(rows) is not list or type(actions) is not list
                or any(type(item) is not str for item in rows + actions)
                or len(rows) != intent.height
                or any(len(item) != intent.width for item in rows)):
            raise PracticeGameError("practice game map/solution invalid")
        marks: dict[str, list[tuple[int, int]]] = {}
        for y, row in enumerate(rows):
            for x, cell in enumerate(row):
                marks.setdefault(cell, []).append((x, y))
        if (len(marks.get("S", ())) != 1 or len(marks.get("G", ())) != 1
                or len(marks.get("C", ())) != intent.collectibles_per_level
                or len(marks.get("H", ())) != intent.hazards_per_level):
            raise PracticeGameError("practice game geometry/intent mismatch")
        level = TileLevel(
            0, tuple(rows), marks["S"][0], marks["G"][0],
            tuple(sorted(marks.get("C", ()))),
            tuple(sorted(marks.get("H", ()))), tuple(actions),
        )
        world = PlayableWorld(intent, (level,))
        proof = demonstrate_solvable(world, authorized=True)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise PracticeGameError("original practice level did not verify") from exc
    return OriginalPracticeGame(
        game_id, world, proof, canonical_digest(body),
    )


def render_practice_game(game_id: str, *, authorized: bool) -> PlayableHTML:
    """Create a self-contained, CSP-locked original game, without a network call."""
    pack = load_practice_game(game_id, authorized=authorized)
    return render_playable_world(pack.world, authorized=True)
