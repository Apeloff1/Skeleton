"""Structural stability margins and buckling proxies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.chain import SpineChain
from skeleton.spine.load_path import LoadPath, build_axial_path, peak_axial, safety_factor
from skeleton.spine.stiffness import assemble_diagonal, condition_proxy, segment_stiffness
from skeleton.spine.balance import balance_score, support_polygon_ok


@dataclass(frozen=True, slots=True)
class StabilityReport:
    euler_load_n: float
    applied_n: float
    margin: float
    balance_mm: float
    condition: float
    support_ok: bool
    ok: bool


def euler_buckling_load(chain: SpineChain) -> float:
    """Very rough Euler load Pcr = pi^2 EI / L^2 using mean disc stiffness."""
    import math

    from skeleton.spine.chain import chain_height_mm

    L = max(chain_height_mm(chain), 1.0)
    # representative EI from lumbar-ish disc
    mob = [s for s in chain.segments if not s.locked]
    if not mob:
        return float("inf")
    # use rotational stiffness * conversion as EI proxy
    eis = []
    for s in mob:
        st = segment_stiffness(s)
        eis.append(st[0] * 57.3)  # back toward N·mm^2
    EI = sum(eis) / len(eis)
    return (math.pi ** 2 * EI) / (L * L)


def stability_margin(chain: SpineChain, applied_n: float = 500.0) -> float:
    pcr = euler_buckling_load(chain)
    if pcr <= 0:
        return 0.0
    return (pcr - applied_n) / pcr


def stability_report(chain: SpineChain, applied_n: float = 500.0) -> StabilityReport:
    path = build_axial_path(chain, cranial_fz=applied_n, include_body_weights=False)
    pcr = euler_buckling_load(chain)
    margin = stability_margin(chain, applied_n)
    bal = balance_score(chain)
    cond = condition_proxy(chain.segments)
    support = support_polygon_ok(chain)
    ok = margin > 0.1 and support and safety_factor(path) > 1.2
    return StabilityReport(pcr, applied_n, margin, bal, cond, support, ok)


def critical_segments(chain: SpineChain, path: LoadPath, top_k: int = 5) -> list[str]:
    """Segments with highest load/stiffness ratio."""
    scored: list[tuple[float, str]] = []
    for s, load in zip(chain.segments, path.segment_loads):
        if s.locked:
            continue
        k = segment_stiffness(s)[5]  # axial
        ratio = load.fz / max(k, 1e-9)
        scored.append((ratio, s.label))
    scored.sort(reverse=True)
    return [lab for _, lab in scored[:top_k]]


def is_stable(chain: SpineChain, applied_n: float = 500.0) -> bool:
    return stability_report(chain, applied_n).ok
