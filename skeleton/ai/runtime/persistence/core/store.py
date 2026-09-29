"""One persist core. Unset SKELETON_OWN = process-local. Set = disk root."""

from __future__ import annotations

import json
import os
from pathlib import Path

from skeleton.persist.cards import persist_card
from skeleton.persist.law import OWN_ENV


class Persist:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = env if env is not None else dict(os.environ)
        raw = (self.env.get(OWN_ENV) or "").strip()
        self.own = Path(raw) if raw else None
        self.live_deck: dict[str, str] = {}
        self.live_jeeves: dict[str, str] = {}

    def gate(self) -> str:
        return "disk" if self.own is not None else "local"

    def put(self, slot: str, key: str, value: str) -> dict:
        if self.own is None:
            bag = self.live_deck if slot == "deck" else self.live_jeeves
            bag[key] = value
            return persist_card(
                kind="put",
                hit=1,
                law="process-local",
                extra={"gate": "local", "slot": slot, "key": key},
            )
        root = self.own
        root.mkdir(parents=True, exist_ok=True)
        if slot == "helix":
            path = root / "helix.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": key, "value": value}) + "\n")
        elif slot == "rotors":
            path = root / "rotors.json"
            data = {}
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
            data[key] = value
            path.write_text(json.dumps(data), encoding="utf-8")
        else:
            traces = root / "traces"
            traces.mkdir(parents=True, exist_ok=True)
            (traces / (key + ".txt")).write_text(value, encoding="utf-8")
        return persist_card(
            kind="put",
            hit=1,
            law="disk-own",
            extra={"gate": "disk", "slot": slot, "key": key},
        )

    def has_local(self, slot: str, key: str) -> bool:
        bag = self.live_deck if slot == "deck" else self.live_jeeves
        return key in bag

    def disk_paths(self) -> dict[str, bool]:
        if self.own is None:
            return {"helix": False, "rotors": False, "traces": False}
        return {
            "helix": (self.own / "helix.jsonl").exists(),
            "rotors": (self.own / "rotors.json").exists(),
            "traces": (self.own / "traces").is_dir(),
        }
