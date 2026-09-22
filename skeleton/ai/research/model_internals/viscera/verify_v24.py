"""Accept checks for GB-23 Viscera 2.4 extend."""

from __future__ import annotations

import sys
from typing import Any

from skeleton.viscera.capabilities import capabilities
from skeleton.viscera.checkgrad import checkgrad
from skeleton.viscera.gqa import gqa_scores
from skeleton.viscera.logit_lens import lens
from skeleton.viscera.muon import near_orthogonal, newton_schulz
from skeleton.viscera.tape import Tape


def check_tape() -> None:
    t = Tape()
    a = t.leaf(2.0)
    b = t.leaf(3.0)
    y = t.mul(a, b)
    t.backward(y)
    if abs(a.grad - 3.0) > 1e-9 or abs(b.grad - 2.0) > 1e-9:
        raise AssertionError("tape")


def check_muon() -> None:
    out = newton_schulz([[1.0, 0.2], [0.1, 0.8]])
    if not near_orthogonal(out):
        raise AssertionError("muon")


def check_lens() -> None:
    idx, p = lens([1.0, 0.0], [[2.0, 0.0], [0.0, 1.0]])
    if idx != 0 or abs(sum(p) - 1.0) > 1e-6:
        raise AssertionError("lens")


def check_gqa() -> None:
    scores = gqa_scores([[1.0, 0.0], [0.0, 1.0]], [[1.0, 0.0]], n_kv=1)
    if len(scores) != 2:
        raise AssertionError("gqa")


def check_grad() -> None:
    if not checkgrad():
        raise AssertionError("checkgrad")


def check_no_torch() -> None:
    if "torch" in sys.modules:
        raise AssertionError("torch")


def check_capabilities() -> None:
    cap = capabilities()
    if cap["contract"].get("tape") != "rev-mode":
        raise AssertionError("cap-tape")


def run_all() -> dict[str, Any]:
    failed: list[str] = []
    for fn in (check_tape, check_muon, check_lens, check_gqa, check_grad, check_no_torch, check_capabilities):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 7}
