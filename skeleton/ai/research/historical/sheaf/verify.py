"""Accept checks for GB-19."""

from __future__ import annotations

from typing import Any

from skeleton.sheaf.capabilities import capabilities
from skeleton.sheaf.cech import h0_constant, h1_constant
from skeleton.sheaf.cover import opens, sites
from skeleton.sheaf.engine import SheafEngine
from skeleton.sheaf.glue import glue
from skeleton.sheaf.restrict import exact_r_compose_r


def check_cover() -> None:
    if len(opens()) != 12:
        raise AssertionError("cover")


def check_exact() -> None:
    names = opens()
    section = frozenset(sites())
    if not exact_r_compose_r(section, (names[0], names[1], names[1])):
        raise AssertionError("exact")


def check_glue_skip() -> None:
    locals_ = {name: frozenset(("p://root",)) for name in opens()}
    if glue(locals_) is None:
        raise AssertionError("glue")
    if glue(locals_, tags=("feed",)) is not None:
        raise AssertionError("skip")


def check_cech() -> None:
    if h0_constant() != 1 or h1_constant() != 1:
        raise AssertionError("cech")


def check_capabilities() -> None:
    cap = capabilities()
    for key in ("owner", "contract", "failure_modes", "obs", "security"):
        if key not in cap:
            raise AssertionError("cap-" + key)


def check_engine() -> None:
    card = SheafEngine().snapshot()
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all() -> dict[str, Any]:
    failed: list[str] = []
    for fn in (
        check_cover,
        check_exact,
        check_glue_skip,
        check_cech,
        check_capabilities,
        check_engine,
    ):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 6}
