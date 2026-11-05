"""B021 deterministic economy command log and replay contract.

Every economy mutation can be expressed as an :class:`EconomyCommand`. A
:class:`CommandLog` keeps commands in tick order with a rolling hash chain,
so a log cannot be reordered or edited without changing its fingerprint.
:func:`replay` rebuilds an economy from a factory and the log; refusals are
part of the outcome (an insufficient-funds refusal must replay as the same
refusal), so two replays of one log always agree on outcomes *and* digest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.simulation.economy.sim import EconomySimError, _req_int

GENESIS = "0" * 64

# op -> (method name, ordered argument names). Only these ops can be replayed.
OPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "open_account": ("open_account", ("owner",)),
    "grant": ("grant", ("faucet_id", "owner", "tick")),
    "charge": ("charge", ("sink_id", "owner", "base")),
    "charge_amount": ("charge_amount", ("sink_id", "owner", "amount")),
    "vendor_buy": ("vendor_buy", ("owner", "item_id", "qty")),
    "vendor_sell": ("vendor_sell", ("owner", "item_id", "qty")),
    "trade": ("trade", ("seller", "buyer", "item_id", "qty", "price")),
    "grant_items": ("grant_items", ("source", "owner", "item_id", "qty")),
    "consume_items": ("consume_items", ("sink", "owner", "item_id", "qty")),
    "move_items": ("move_items", ("src", "dst", "item_id", "qty")),
    "bind": ("bind", ("owner", "item_id", "qty")),
}


class ReplayError(EconomySimError):
    code = "ECO.REPLAY"


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class EconomyCommand:
    tick: int
    op: str
    args: Mapping[str, Any]

    def __post_init__(self) -> None:
        _req_int(self.tick, "tick")
        if self.op not in OPS:
            raise ReplayError(f"unknown op {self.op!r}")
        names = OPS[self.op][1]
        extra = set(self.args) - set(names)
        if extra:
            raise ReplayError(f"unexpected args for {self.op}: {sorted(extra)}")
        for value in self.args.values():
            if not isinstance(value, (str, int)) or isinstance(value, bool):
                raise ReplayError("command args must be str or int")
        object.__setattr__(self, "args", dict(sorted(self.args.items())))

    def to_dict(self) -> dict[str, Any]:
        return {"tick": self.tick, "op": self.op, "args": dict(self.args)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EconomyCommand":
        if set(data) != {"tick", "op", "args"} or not isinstance(data["args"], Mapping):
            raise ReplayError("malformed command record")
        return cls(tick=data["tick"], op=data["op"], args=data["args"])


@dataclass
class CommandLog:
    """Append-only, tick-ordered, hash-chained command log."""

    commands: list[EconomyCommand] = field(default_factory=list)
    head: str = GENESIS

    def append(self, command: EconomyCommand) -> str:
        if self.commands and command.tick < self.commands[-1].tick:
            raise ReplayError("command tick went backwards")
        self.head = hashlib.sha256((self.head + _canon(command.to_dict())).encode()).hexdigest()
        self.commands.append(command)
        return self.head

    def extend(self, commands: Iterable[EconomyCommand]) -> str:
        for command in commands:
            self.append(command)
        return self.head

    def to_jsonl(self) -> str:
        return "".join(_canon(c.to_dict()) + "\n" for c in self.commands)

    @classmethod
    def from_jsonl(cls, text: str, *, expected_head: str | None = None) -> "CommandLog":
        log = cls()
        for line in text.splitlines():
            if line.strip():
                log.append(EconomyCommand.from_dict(json.loads(line)))
        if expected_head is not None and log.head != expected_head:
            raise ReplayError("log head mismatch: log was edited or reordered")
        return log


def apply(econ: GameplayEconomy, command: EconomyCommand) -> dict[str, Any]:
    """Apply one command; refusals are returned, never raised."""
    method, names = OPS[command.op]
    kwargs = dict(command.args)
    missing = [n for n in names if n not in kwargs and not _has_default(command.op, n)]
    if missing:
        return {"ok": False, "error": f"missing args {missing}"}
    try:
        result = getattr(econ, method)(**kwargs)
    except EconomySimError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "result": result}


def _has_default(op: str, name: str) -> bool:
    return (op, name) in {
        ("charge", "base"),
        ("vendor_buy", "qty"),
        ("vendor_sell", "qty"),
        ("grant_items", "qty"),
        ("consume_items", "qty"),
        ("move_items", "qty"),
        ("bind", "qty"),
    }


@dataclass(frozen=True)
class ReplayResult:
    log_head: str
    digest: str
    outcomes: tuple[dict[str, Any], ...]

    @property
    def refusals(self) -> int:
        return sum(1 for o in self.outcomes if not o["ok"])

    def fingerprint(self) -> str:
        """Hash of log head, final digest and every outcome."""
        payload = _canon({"log": self.log_head, "digest": self.digest, "outcomes": list(self.outcomes)})
        return hashlib.sha256(payload.encode()).hexdigest()


def replay(factory: Callable[[], GameplayEconomy], log: CommandLog) -> ReplayResult:
    econ = factory()
    outcomes = tuple(apply(econ, c) for c in log.commands)
    audit = econ.audit()
    items = econ.item_audit()
    if not audit["ok"] or not items["ok"]:
        raise ReplayError("replay produced unbalanced books")
    return ReplayResult(log_head=log.head, digest=econ.digest(), outcomes=outcomes)


def verify(factory: Callable[[], GameplayEconomy], log: CommandLog, expected_fingerprint: str) -> bool:
    return replay(factory, log).fingerprint() == expected_fingerprint


__all__ = ["OPS", "CommandLog", "EconomyCommand", "ReplayError", "ReplayResult", "apply", "replay", "verify"]
