"""Global alignment metrics: SVA, pelvic proxies, coronal balance."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.spine.balance import chain_com, plumb_offset_mm, sagittal_vertical_axis
from skeleton.spine.chain import SpineChain
from skeleton.spine.kinematics import forward_frames


@dataclass(frozen=True, slots=True)
class AlignmentReport:
    sva_mm: float
    coronal_offset_mm: float
    com_x: float
    com_y: float
    com_z: float
    height_mm: float
    ok: bool


def pelvic_incidence_proxy(chain: SpineChain) -> float:
    """Without pelvis, use L5-S1 relative rx as PI proxy seed."""
    # Find L5-S1 segment
    for s in chain.segments:
        if s.sid.cranial == "L5" and s.sid.caudal == "S1":
            return 50.0 + s.relative.rx  # population mean PI ~50°
    return 50.0


def lumbar_pelvic_match(chain: SpineChain) -> float:
    """PI − LL mismatch proxy (degrees). Ideal ~0-10."""
    from skeleton.spine.curvature import lumbar_lordosis

    pi = pelvic_incidence_proxy(chain)
    ll = abs(lumbar_lordosis(chain).cobb_deg)
    return pi - ll


def alignment_report(chain: SpineChain) -> AlignmentReport:
    dx, dy = plumb_offset_mm(chain)
    com = chain_com(chain)
    frames = forward_frames(chain)
    height = frames[-1].z - frames[0].z if frames else 0.0
    sva = sagittal_vertical_axis(chain)
    ok = abs(sva) < 50.0 and abs(dy) < 30.0
    return AlignmentReport(sva, dy, com.x, com.y, com.z, height, ok)


def coronal_balance_ok(chain: SpineChain, tol_mm: float = 20.0) -> bool:
    _, dy = plumb_offset_mm(chain)
    return abs(dy) <= tol_mm


def sagittal_balance_ok(chain: SpineChain, tol_mm: float = 50.0) -> bool:
    return abs(sagittal_vertical_axis(chain)) <= tol_mm


def dual_plane_ok(chain: SpineChain) -> bool:
    return coronal_balance_ok(chain) and sagittal_balance_ok(chain)


def shoulder_pelvis_proxy(chain: SpineChain) -> tuple[float, float]:
    """Use C7 vs S1 lateral (y) and axial (x) offsets."""
    return plumb_offset_mm(chain)
