"""Cockpit — operator console over tensor, lattice, helix, ledger, snowball.

Command language (one statement per apply):
  BIND ERA <id>
  BIND GENERATION <id>
  SET AXIS <name> <0..1>
  LERP ERA <id> <t>
  BLEND ERA <a> <b> [t]
  ROLL ORACLE
  NICK HELIX
  LIGATE HELIX
  DETECT <text>
  SNAPSHOT
  STATUS
Unknown verbs raise CockpitError. apply() is the only mutation path;
the pipeline reads the cockpit, never the other way around.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.context.dodeca import Dodecahedron
from skeleton.context.helix import DNAHelix
from skeleton.context.ledger import ContextLedger
from skeleton.context.oracle import Magic8Ball, OracleReading
from skeleton.context.snowball import Snowball
from skeleton.context.tensor import AXES, ContextTensor, detect_era
from skeleton.kernel.errors import SkeletonError


class CockpitError(SkeletonError):
    code = "CTX.COCKPIT"
    http_status = 400


@dataclass
class Cockpit:
    tensor: ContextTensor = field(default_factory=lambda: ContextTensor.from_era("extraction_now"))
    helix: DNAHelix = field(default_factory=DNAHelix)
    ledger: ContextLedger = field(default_factory=ContextLedger)
    snowball: Snowball = field(default_factory=Snowball)
    last_oracle: Optional[OracleReading] = None
    history: List[str] = field(default_factory=list)
    blend: Optional[Tuple[str, str, float]] = None
    generation: Optional[str] = None

    @property
    def lattice(self) -> Dodecahedron:
        return Dodecahedron.from_tensor(self.tensor)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "tensor": self.tensor.to_dict(),
            "lattice": self.lattice.to_dict(),
            "helix": self.helix.to_dict(),
            "ledger": {"height": self.ledger.height, "head": self.ledger.head.hash,
                       "valid": not self.ledger.verify()},
            "snowball": self.snowball.to_dict(),
            "oracle": self.last_oracle.to_dict() if self.last_oracle else None,
            "blend": list(self.blend) if self.blend else None,
            "generation": self.generation,
            "history": list(self.history[-20:]),
        }

    def apply(self, command: str) -> Dict[str, Any]:
        line = (command or "").strip()
        if not line:
            raise CockpitError("empty command")
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            raise CockpitError(str(exc)) from exc
        verb = tokens[0].upper()
        args = tokens[1:]
        if verb == "SNAPSHOT" or verb == "STATUS":
            result = self.snapshot()
        elif verb == "BIND" and args and args[0].upper() == "ERA":
            era = args[1] if len(args) > 1 else "extraction_now"
            self.tensor = ContextTensor.from_era(era)
            self.blend = None
            result = {"era": self.tensor.era, "tensor": self.tensor.as_dict()}
        elif verb == "BIND" and args and args[0].upper() in {"GENERATION", "GEN"}:
            from skeleton.forge.hardware import get_generation
            key = args[1] if len(args) > 1 else "modern"
            spec = get_generation(key)
            self.generation = spec["key"]
            result = {"generation": spec["key"], "label": spec["label"], "viewport": spec["viewport"]}
        elif verb == "SET" and args and args[0].upper() == "AXIS":
            if len(args) < 3:
                raise CockpitError("SET AXIS <name> <value>")
            axis, raw = args[1], args[2]
            if axis not in AXES:
                raise CockpitError("unknown axis", context={"axis": axis, "known": list(AXES)})
            self.tensor = self.tensor.with_axis(axis, float(raw))
            result = {"axis": axis, "value": self.tensor[axis]}
        elif verb == "LERP" and args and args[0].upper() == "ERA":
            if len(args) < 3:
                raise CockpitError("LERP ERA <id> <t>")
            other = ContextTensor.from_era(args[1])
            self.tensor = self.tensor.lerp(other, float(args[2]))
            result = {"era": self.tensor.era, "tensor": self.tensor.as_dict()}
        elif verb == "BLEND":
            if args and args[0].upper() == "ERA":
                args = args[1:]
            if len(args) < 2:
                raise CockpitError("BLEND ERA <a> <b> [t]")
            a, b = args[0], args[1]
            t = float(args[2]) if len(args) > 2 else 0.5
            t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
            self.blend = (a, b, t)
            self.tensor = ContextTensor.from_era(a).lerp(ContextTensor.from_era(b), t)
            object.__setattr__(self.tensor, "era", f"{a}~{b}@{t:.2f}")
            result = {"era": self.tensor.era, "blend": [a, b, t], "tensor": self.tensor.as_dict()}
        elif verb == "ROLL":
            ball = Magic8Ball(self.lattice)
            self.last_oracle = ball.roll(self.tensor, nonce=len(self.history))
            result = self.last_oracle.to_dict()
        elif verb == "NICK":
            self.helix.nick()
            result = {"nicked": self.helix.nicked, "sigma": self.helix.supercoiling}
        elif verb == "LIGATE":
            self.helix.ligate()
            result = {"nicked": self.helix.nicked, "sigma": self.helix.supercoiling}
        elif verb == "DETECT":
            text = " ".join(args)
            era, scores = detect_era(text)
            self.tensor = ContextTensor.from_era(era)
            self.blend = None
            result = {"era": era, "scores": scores}
        else:
            raise CockpitError("unknown command", context={"verb": verb, "line": line})
        self.history.append(line)
        self.ledger.append(
            "cockpit", {"cmd": line, "verb": verb},
            mass=self.snowball.mass, tensor_fp=self.tensor.fingerprint(),
            leaves=[line, verb],
        )
        return {"ok": True, "verb": verb, "result": result}

    def to_dict(self) -> Dict[str, Any]:
        return self.snapshot()
