"""Aggregate spine metrics for cards and observability."""

from __future__ import annotations

from typing import Any

from skeleton.spine.alignment import alignment_report
from skeleton.spine.articulation import all_rom_ok, aggregate_rom_volume
from skeleton.spine.balance import balance_score, chain_com
from skeleton.spine.chain import SpineChain, chain_height_mm
from skeleton.spine.curvature import curvature_card_payload
from skeleton.spine.digest import chain_digest
from skeleton.spine.kinematics import chord_length_mm, path_length_mm
from skeleton.spine.load_path import build_axial_path, load_card_payload
from skeleton.spine.range_of_motion import mean_utilization
from skeleton.spine.stability import stability_margin
from skeleton.spine.stiffness import chain_energy, condition_proxy
from skeleton.spine.taxonomy import Region


def compute_metrics(chain: SpineChain, cranial_load_n: float = 100.0) -> dict[str, Any]:
    path = build_axial_path(chain, cranial_fz=cranial_load_n, include_body_weights=True)
    align = alignment_report(chain)
    com = chain_com(chain)
    metrics: dict[str, Any] = {
        "vertebra_n": len(chain.vertebrae),
        "segment_n": len(chain.segments),
        "mobile_segments": chain.mobile_segment_count(),
        "height_mm": chain_height_mm(chain),
        "path_mm": path_length_mm(chain),
        "chord_mm": chord_length_mm(chain),
        "rom_ok": int(all_rom_ok(chain.segments)),
        "rom_volume": aggregate_rom_volume(chain.segments),
        "rom_utilization": mean_utilization(chain.segments),
        "energy": chain_energy(chain.segments),
        "condition": condition_proxy(chain.segments),
        "balance_mm": balance_score(chain),
        "sva_mm": align.sva_mm,
        "alignment_ok": int(align.ok),
        "stability_margin": stability_margin(chain, cranial_load_n),
        "digest": chain_digest(chain),
        "com_mass_g": com.mass_g,
        "load_residual": path.residual(),
    }
    metrics.update({f"curve_{k}": v for k, v in curvature_card_payload(chain).items()})
    metrics.update({f"load_{k}": v for k, v in load_card_payload(path).items()})
    for region in Region:
        metrics[f"region_{region.value}_n"] = len(chain.region(region))
    return metrics


def metrics_hit(metrics: dict[str, Any]) -> int:
    checks = [
        metrics.get("rom_ok") == 1,
        metrics.get("alignment_ok") == 1,
        metrics.get("vertebra_n") == 33,
        metrics.get("segment_n") == 32,
        isinstance(metrics.get("digest"), str) and len(metrics["digest"]) == 16,
    ]
    return int(all(checks))
