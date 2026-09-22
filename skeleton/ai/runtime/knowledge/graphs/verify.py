"""Accept checks for GB-18."""

from __future__ import annotations

from typing import Any

from skeleton.graphs.capabilities import capabilities
from skeleton.graphs.engine import GraphEngine
from skeleton.graphs.export import mermaid, dot
from skeleton.graphs.flow import conserved, unit_path_flow
from skeleton.graphs.house import HOUSE_N, vertex_ids
from skeleton.graphs.spectral import fiedler, lambda_max


def check_house() -> None:
    if len(vertex_ids()) != 27 or HOUSE_N != 27:
        raise AssertionError("house-n")


def check_spectral() -> None:
    lmax, _ = lambda_max()
    fval, _ = fiedler()
    if lmax <= 0.0:
        raise AssertionError("lambda_max")
    if fval < -1e-3:
        raise AssertionError("fiedler")


def check_flow() -> None:
    if not conserved(unit_path_flow()):
        raise AssertionError("flow")


def check_export() -> None:
    if not mermaid() or not dot():
        raise AssertionError("export")


def check_capabilities() -> None:
    cap = capabilities()
    for key in ("owner", "contract", "failure_modes", "obs", "security"):
        if key not in cap:
            raise AssertionError("cap-" + key)
    if cap["contract"]["house_n"] != 27:
        raise AssertionError("cap-n")


def check_engine() -> None:
    card = GraphEngine().snapshot()
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all() -> dict[str, Any]:
    failed: list[str] = []
    for fn in (
        check_house,
        check_spectral,
        check_flow,
        check_export,
        check_capabilities,
        check_engine,
    ):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 6}
