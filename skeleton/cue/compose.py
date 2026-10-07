"""Round-robin cue. Closed vocab. Stimulus never lands."""

from __future__ import annotations

from skeleton.cue.law import AXES, VOCAB


class Cue:
    def __init__(self) -> None:
        self.i = 0
        self.axis = {name: 0 for name in AXES}
        self.last = ""

    def tick(self, stimulus: str = "") -> dict:
        name = AXES[self.i % len(AXES)]
        self.axis[name] += 1
        self.i += 1
        self.last = name
        dropped = 1 if str(stimulus or "").strip() else 0
        return self.card(dropped=dropped)

    def tokens(self) -> list[str]:
        out: list[str] = []
        for name in AXES:
            vocab = VOCAB[name]
            count = int(self.axis[name])
            idx = 0 if count <= 0 else (count - 1) % len(vocab)
            out.append(vocab[idx])
        return out

    def card(self, dropped: int = 0) -> dict:
        return {
            "kind": "cue",
            "i": self.i,
            "last": self.last,
            "axis": dict(self.axis),
            "tokens": self.tokens(),
            "dropped": dropped,
            "stored_prose": 0,
        }
