"""Accept checks for GB-17. Used by tests and scripts/check_primitives.py."""

from __future__ import annotations

from typing import Any

from skeleton.primitives.activations import apply
from skeleton.primitives.capabilities import capabilities
from skeleton.primitives.engine import PrimitiveEngine
from skeleton.primitives.kinds import kind_count
from skeleton.primitives.law import KIND_COUNT, KINDS, RING_CAP
from skeleton.primitives.merkle import proof, root_of, verify
from skeleton.primitives.ops import bond, compact, fork, gossip, house, quench, witness
from skeleton.primitives.ring import Ring
from skeleton.primitives.viscera_bridge import assert_no_viscera_import, viscera_card


def check_kind_count() -> None:
    if kind_count() != KIND_COUNT:
        raise AssertionError("kinds")
    if len(KINDS) != 12:
        raise AssertionError("kinds-tuple")


def check_ring_cap() -> None:
    ring = Ring()
    for i in range(RING_CAP + 6):
        ring.push("t" + str(i))
    if len(ring) != RING_CAP:
        raise AssertionError("ring-cap")


def check_merkle() -> None:
    leaves = ["a", "b", "c", "d"]
    root = root_of(leaves)
    trail = proof(leaves, 2)
    if not verify("c", trail, root):
        raise AssertionError("merkle")


def check_activations() -> None:
    for name in ("silu", "gelu", "rms_norm"):
        out = apply(name, [0.0, 1.0, -1.0, 2.0])
        if len(out) != 4:
            raise AssertionError(name)


def check_ops() -> None:
    bond("x", "y")
    quench("x", 0.91)
    witness(["p1", "p2"])
    gossip("aa", "aa")
    fork("x", 2)
    house(["h0"])
    compact(Ring())


def check_bridge() -> None:
    assert_no_viscera_import()
    card = viscera_card(G=0.0, law="thin", root="00")
    if "G" not in card or "root" not in card:
        raise AssertionError("bridge-fields")
    if card.get("stored_prose") != 0:
        raise AssertionError("prose")


def check_capabilities() -> None:
    cap = capabilities()
    for key in ("owner", "contract", "failure_modes", "obs", "security"):
        if key not in cap:
            raise AssertionError("cap-" + key)


def check_engine() -> None:
    eng = PrimitiveEngine()
    eng.push("p://house/1")
    eng.push("p://house/2")
    eng.apply_op("bond", left="p://house/1", right="p://house/2")
    eng.compact()
    eng.bridge(G=0.0)
    health = eng.health()
    if health["hit"] != 1:
        raise AssertionError("health")


def run_all() -> dict[str, Any]:
    checks = (
        check_kind_count,
        check_ring_cap,
        check_merkle,
        check_activations,
        check_ops,
        check_bridge,
        check_capabilities,
        check_engine,
    )
    failed: list[str] = []
    for fn in checks:
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": len(checks)}
