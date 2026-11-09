"""Accept checks for GB-22. Torch must stay out."""

from __future__ import annotations

import sys
from typing import Any

from skeleton.viscera.capabilities import capabilities
from skeleton.viscera.engine import VisceraEngine
from skeleton.viscera.quant import quant_snr
from skeleton.viscera.remat import remat
from skeleton.viscera.specdec import verify


def check_specdec() -> None:
    if verify([1, 2, 9], [1, 2, 3]) != 2:
        raise AssertionError("specdec")


def check_snr() -> None:
    snr = quant_snr([0.2, -0.4, 0.6])
    if snr != snr:
        raise AssertionError("snr")


def check_remat() -> None:
    _, _, same = remat(lambda x: list(x), [1.0, 2.0])
    if not same:
        raise AssertionError("remat")


def check_no_torch() -> None:
    if "torch" in sys.modules:
        raise AssertionError("torch")


def check_capabilities() -> None:
    cap = capabilities()
    for key in ("owner", "contract", "failure_modes", "obs", "security"):
        if key not in cap:
            raise AssertionError("cap-" + key)


def check_engine() -> None:
    card = VisceraEngine().snapshot()
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all() -> dict[str, Any]:
    failed: list[str] = []
    for fn in (check_specdec, check_snr, check_remat, check_no_torch, check_capabilities, check_engine):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 6}
