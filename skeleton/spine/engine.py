"""Compose spine cards into SpineEngine facade (GB-20)."""

from __future__ import annotations

from typing import Any

from skeleton.spine.alignment import alignment_report
from skeleton.spine.articulation import all_rom_ok
from skeleton.spine.cards import spine_card
from skeleton.spine.chain import SpineChain, assert_chain_integrity, default_chain
from skeleton.spine.curvature import (
    apply_neutral_curves,
    cervical_lordosis,
    curvature_sign_ok,
    lumbar_lordosis,
    thoracic_kyphosis,
)
from skeleton.spine.digest import chain_digest, digest_pair
from skeleton.spine.invariant import check_all
from skeleton.spine.kinematics import end_effector, forward_frames, path_length_mm
from skeleton.spine.law import PACKET, SEGMENT_N, VERSION, VERTEBRA_N
from skeleton.spine.load_path import build_axial_path, is_conserved, peak_axial
from skeleton.spine.metrics import compute_metrics, metrics_hit
from skeleton.spine.posture import assert_postures_rom_safe, list_postures
from skeleton.spine.serialize import roundtrip_ok
from skeleton.spine.stability import stability_report
from skeleton.spine.taxonomy import REGION_COUNTS, validate_catalog
from skeleton.spine.topology import has_cycle, is_connected, is_path_graph, validate_topology


class SpineEngine:
    """Thin facade over the GB-20 spine stack. No network. No torch."""

    def __init__(self, chain: SpineChain | None = None) -> None:
        self._chain = chain if chain is not None else default_chain()

    @property
    def chain(self) -> SpineChain:
        return self._chain

    def with_chain(self, chain: SpineChain) -> "SpineEngine":
        return SpineEngine(chain)

    def snapshot(self) -> dict[str, Any]:
        chain = self._chain
        metrics = compute_metrics(chain)
        digests = digest_pair(chain)
        align = alignment_report(chain)
        stab = stability_report(chain)
        path = build_axial_path(chain, cranial_fz=100.0, include_body_weights=False)
        frames = forward_frames(chain)
        tip = end_effector(chain)
        inv_failed = check_all(chain)
        topo = validate_topology()
        hit = int(
            metrics_hit(metrics) == 1
            and not inv_failed
            and all_rom_ok(chain.segments)
            and is_path_graph()
            and not has_cycle()
            and is_connected()
            and is_conserved(path)
            and path.residual() <= 1e-6
            and roundtrip_ok(chain)
            and len(chain.vertebrae) == VERTEBRA_N
            and len(chain.segments) == SEGMENT_N
        )
        return spine_card(
            kind="spine",
            hit=hit,
            law=f"spine {VERSION}",
            extra={
                "packet": PACKET,
                "vertebra_n": len(chain.vertebrae),
                "segment_n": len(chain.segments),
                "region_counts": dict(REGION_COUNTS),
                "rom_ok": int(all_rom_ok(chain.segments)),
                "digest": digests["chain"],
                "digest_cranial": digests["cranial"],
                "digest_caudal": digests["caudal"],
                "load_residual": path.residual(),
                "load_peak_axial": peak_axial(path),
                "load_conserved": int(is_conserved(path)),
                "path_mm": path_length_mm(chain),
                "tip_z": tip.z,
                "frame_n": len(frames),
                "alignment_ok": int(align.ok),
                "sva_mm": align.sva_mm,
                "stability_ok": int(stab.ok),
                "stability_margin": stab.margin,
                "topology": topo,
                "invariants_failed": list(inv_failed),
                "posture_n": len(list_postures()),
                "metrics_hit": metrics_hit(metrics),
            },
        )

    def metrics(self) -> dict[str, Any]:
        return compute_metrics(self._chain)

    def digest(self) -> str:
        return chain_digest(self._chain)

    def verify_local(self) -> dict[str, Any]:
        """Local fail-closed probe used by SpineEngine callers."""
        failed: list[str] = []
        try:
            validate_catalog()
        except Exception:
            failed.append("catalog")
        try:
            assert_chain_integrity(self._chain)
        except Exception:
            failed.append("integrity")
        try:
            validate_topology()
            if has_cycle() or not is_connected() or not is_path_graph():
                failed.append("topology")
        except Exception:
            failed.append("topology")
        if not all_rom_ok(self._chain.segments):
            failed.append("rom")
        path = build_axial_path(self._chain, cranial_fz=100.0, include_body_weights=False)
        if not is_conserved(path) or path.residual() > 1e-6:
            failed.append("load")
        if check_all(self._chain):
            failed.append("invariants")
        if not roundtrip_ok(self._chain):
            failed.append("serialize")
        bad_postures = assert_postures_rom_safe()
        if bad_postures:
            failed.append("postures:" + ",".join(bad_postures))
        return {"ok": int(not failed), "failed": failed}

    def curved(self) -> "SpineEngine":
        """Return engine whose chain carries neutral lordosis/kyphosis."""
        return SpineEngine(apply_neutral_curves(self._chain))

    def curvature_ok(self) -> bool:
        curved = apply_neutral_curves(self._chain)
        return curvature_sign_ok(curved)

    def curvature_summary(self) -> dict[str, float]:
        curved = apply_neutral_curves(self._chain)
        c = cervical_lordosis(curved)
        t = thoracic_kyphosis(curved)
        l = lumbar_lordosis(curved)
        return {
            "cervical_cobb": c.cobb_deg,
            "thoracic_cobb": t.cobb_deg,
            "lumbar_cobb": l.cobb_deg,
            "cervical_arc": c.arc_mm,
            "thoracic_arc": t.arc_mm,
            "lumbar_arc": l.arc_mm,
        }
