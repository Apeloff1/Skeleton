"""Portable offline GameForge prototype runtime, bundled verbatim in each ZIP.

The deterministic campaign is intentionally a reference turn-based loop, not a
claim that a native engine or every genre-specific mechanic is implemented.
No external process, network, plugin, model, or generated code is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

MAX_LEVELS = 256
MAX_TURNS = 4096
MAX_CAMPAIGN_BYTES = 256 * 1024
ACTIONS = ("attack", "guard", "explore", "heal", "advance")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _text(value: Any, fallback: str, limit: int = 120) -> str:
    if not isinstance(value, str):
        return fallback
    value = "".join(ch for ch in value[:limit] if ch.isprintable()).strip()
    return value or fallback


def campaign_from_game_data(name: str, data: dict) -> dict:
    """Compile the existing workflow level/system data into a playable campaign."""
    if type(data) is not dict:
        raise ValueError("game data must be an object")
    raw_levels = data.get("levels", {})
    if type(raw_levels) is not dict or len(raw_levels) > MAX_LEVELS:
        raise ValueError("invalid level inventory")
    if not raw_levels:
        raw_levels = {
            f"level_{i+1}": {"name": title, "difficulty": difficulty}
            for i, (title, difficulty) in enumerate((
                ("Arrival", .2), ("Crossroads", .5), ("Final trial", .8)
            ))
        }
    levels = []
    for index, (key, meta) in enumerate(raw_levels.items()):
        if type(meta) is not dict:
            raise ValueError("invalid level descriptor")
        difficulty = meta.get("difficulty", .5)
        if type(difficulty) not in (int, float) or not math.isfinite(difficulty) or not 0 <= difficulty <= 1:
            raise ValueError("invalid level difficulty")
        levels.append({
            "id": f"stage_{index+1}",
            "name": _text(meta.get("name"), _text(key, f"Stage {index+1}")),
            "enemy_hp": 12 + round(difficulty * 12),
            "enemy_damage": 2 + round(difficulty * 4),
            "reward": 5 + round(difficulty * 10),
        })
    systems = data.get("systems", {})
    if type(systems) is not dict:
        raise ValueError("invalid systems inventory")
    if len(systems) > 128 or any(type(key) is not str for key in systems):
        raise ValueError("invalid system inventory")
    narrative = data.get("narrative", {})
    premise = narrative.get("premise") if isinstance(narrative, dict) else None
    campaign = {
        "format": "gameforge-portable-v1",
        "name": _text(name, "GameForge prototype"),
        "premise": _text(premise, "Explore, survive and complete the campaign.", 240),
        "declared_systems": sorted(_text(key, "unnamed") for key in systems),
        "implemented_mechanics": ["turn_combat", "guard", "exploration",
                                  "healing", "stage_progression", "replay"],
        "levels": levels,
    }
    validate_campaign(campaign)
    return campaign


def validate_campaign(campaign: dict) -> None:
    if type(campaign) is not dict or campaign.get("format") != "gameforge-portable-v1":
        raise ValueError("unsupported campaign")
    if len(canonical(campaign)) > MAX_CAMPAIGN_BYTES:
        raise ValueError("campaign exceeds byte budget")
    levels = campaign.get("levels")
    if type(levels) is not list or not 1 <= len(levels) <= MAX_LEVELS:
        raise ValueError("invalid campaign levels")
    for index, level in enumerate(levels):
        if type(level) is not dict or level.get("id") != f"stage_{index+1}":
            raise ValueError("invalid stage identity")
        if type(level.get("name")) is not str or not 1 <= len(level["name"]) <= 120:
            raise ValueError("invalid stage name")
        for field, maximum in (("enemy_hp", 24), ("enemy_damage", 6), ("reward", 15)):
            value = level.get(field)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid stage statistic")


@dataclass(frozen=True)
class State:
    stage: int = 0
    hp: int = 100
    enemy_hp: int = 0
    potions: int = 3
    gold: int = 0
    xp: int = 0
    explored: bool = False
    turn: int = 0
    outcome: str = "playing"


class Session:
    def __init__(self, campaign: dict):
        validate_campaign(campaign)
        # Detach references and bind the replay to the exact immutable input.
        self._campaign = json.loads(canonical(campaign))
        self.campaign_sha256 = digest(self._campaign)
        self.state = State(enemy_hp=self._campaign["levels"][0]["enemy_hp"])
        self.head = digest({"campaign": self.campaign_sha256, "state": asdict(self.state)})
        self._actions: list[str] = []

    def action(self, action: str) -> State:
        s = self.state
        if action not in ACTIONS or s.outcome != "playing":
            raise ValueError("action unavailable")
        if s.turn >= MAX_TURNS:
            raise ValueError("turn budget exhausted")
        level = self._campaign["levels"][s.stage]
        hp, enemy, potions, gold, xp = s.hp, s.enemy_hp, s.potions, s.gold, s.xp
        stage, explored, outcome = s.stage, s.explored, s.outcome
        if action == "attack":
            if enemy <= 0:
                raise ValueError("enemy already defeated")
            enemy = max(0, enemy - (8 + min(xp // 25, 6)))
            if enemy:
                hp -= level["enemy_damage"]
            else:
                gold += level["reward"]
                xp += 8
        elif action == "guard":
            if not enemy:
                raise ValueError("no enemy to guard against")
            # A tactical recovery option: mitigate incoming damage and trade
            # a turn for a small reprieve, never mint unlimited resources.
            hp -= max(1, level["enemy_damage"] // 3)
            enemy = max(0, enemy - 2)
            if not enemy:
                gold += level["reward"]
                xp += 8
        elif action == "explore":
            if explored or enemy:
                raise ValueError("exploration requires a cleared stage")
            explored = True
            gold += 3
            xp += 2
        elif action == "heal":
            if not potions or hp >= 100:
                raise ValueError("healing unavailable")
            potions -= 1
            hp = min(100, hp + 35)
            if enemy:
                hp -= level["enemy_damage"]
        elif action == "advance":
            if enemy or not explored:
                raise ValueError("stage objectives unfinished")
            if stage + 1 == len(self._campaign["levels"]):
                outcome = "victory"
            else:
                stage += 1
                enemy = self._campaign["levels"][stage]["enemy_hp"]
                explored = False
                hp = min(100, hp + 20)
                potions = min(3, potions + (1 if stage % 3 == 0 else 0))
        if hp <= 0:
            hp, outcome = 0, "defeat"
        turn = s.turn + 1
        if turn == MAX_TURNS and outcome == "playing":
            outcome = "turn_budget_exhausted"
        self.state = State(stage, hp, enemy, potions, gold, xp, explored, turn, outcome)
        self.head = digest({"prev": self.head, "action": action, "state": asdict(self.state)})
        self._actions.append(action)
        return self.state

    def receipt(self) -> dict:
        return {"campaign_sha256": self.campaign_sha256, "head": self.head,
                "state": asdict(self.state), "actions": list(self._actions)}

    @classmethod
    def replay(cls, campaign: dict, receipt: dict) -> Session:
        actions = receipt.get("actions")
        if type(actions) is not list or len(actions) > MAX_TURNS:
            raise ValueError("invalid replay action inventory")
        session = cls(campaign)
        for action in actions:
            session.action(action)
        if session.receipt() != receipt:
            raise ValueError("replay does not match receipt")
        return session


def smoke(campaign: dict) -> dict:
    """Execute every stage and independently replay the full action chain."""
    session = Session(campaign)
    while session.state.outcome == "playing":
        s = session.state
        if s.enemy_hp:
            session.action("heal" if s.hp <= 30 and s.potions else "attack")
        elif not s.explored:
            session.action("explore")
        else:
            session.action("advance")
    receipt = session.receipt()
    verified = Session.replay(campaign, receipt)
    if verified.state.outcome != "victory":
        raise ValueError("portable campaign smoke did not reach victory")
    return {"outcome": verified.state.outcome, "turns": verified.state.turn,
            "stages": verified.state.stage + 1, "campaign_sha256": verified.campaign_sha256,
            "replay_sha256": verified.head, "replay_verified": True}


def load_campaign(manifest_path: str | Path) -> dict:
    path = Path(manifest_path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_CAMPAIGN_BYTES + 1)
    if len(raw) > MAX_CAMPAIGN_BYTES:
        raise ValueError("manifest exceeds byte budget")
    manifest = json.loads(raw)
    if manifest.get("campaign_file") != "campaign.json":
        raise ValueError("unsupported campaign path")
    with path.with_name("campaign.json").open("rb") as stream:
        raw = stream.read(MAX_CAMPAIGN_BYTES + 1)
    if len(raw) > MAX_CAMPAIGN_BYTES:
        raise ValueError("campaign exceeds byte budget")
    campaign = json.loads(raw)
    validate_campaign(campaign)
    if manifest.get("campaign_sha256") != digest(campaign):
        raise ValueError("campaign digest mismatch")
    return campaign


def run(manifest_path: str = "game_manifest.json", *, play: bool = False) -> dict:
    campaign = load_campaign(manifest_path)
    if not play:
        result = smoke(campaign)
        print(json.dumps(result, indent=2))
        return result
    session = Session(campaign)
    print(campaign["name"], "-", campaign["premise"])
    while session.state.outcome == "playing":
        s = session.state
        print(campaign["levels"][s.stage]["name"], asdict(s))
        try:
            action = input("attack / guard / explore / heal / advance / quit: ").strip().lower()
        except EOFError:
            break
        if action == "quit":
            break
        try:
            session.action(action)
        except ValueError as exc:
            print(str(exc))
    result = session.receipt()
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", default="game_manifest.json")
    parser.add_argument("--play", action="store_true", help="interactive local campaign")
    args = parser.parse_args()
    run(args.manifest, play=args.play)
