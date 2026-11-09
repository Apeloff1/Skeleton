"""Accept checks for GB-20 Spine. Fail-closed Sev1/Sev2 gates."""

from __future__ import annotations

from typing import Any, Callable

from skeleton.spine.articulation import all_rom_ok, assert_dof_contract, clamp_to_rom
from skeleton.spine.capabilities import capabilities
from skeleton.spine.chain import assert_chain_integrity, default_chain, rebind_segments
from skeleton.spine.compare import diff_chains, same_topology, similarity
from skeleton.spine.constraint_solver import project_rom, satisfy
from skeleton.spine.digest import assert_digest_format, chain_digest, digests_equal
from skeleton.spine.engine import SpineEngine
from skeleton.spine.invariant import check_all
from skeleton.spine.kinematics import end_effector, forward_frames, path_length_mm
from skeleton.spine.law import (
    CERVICAL_N,
    COCCYX_N,
    DOF_PER_SEGMENT,
    LUMBAR_N,
    PACKET,
    SACRAL_N,
    SEGMENT_N,
    STORED_PROSE,
    THORACIC_N,
    TOPOLOGY_KIND,
    VERTEBRA_N,
    VERSION,
)
from skeleton.spine.load_path import build_axial_path, is_conserved
from skeleton.spine.posture import assert_postures_rom_safe, build_posture, list_postures
from skeleton.spine.segment import apply_relative_map
from skeleton.spine.serialize import chain_from_dict, chain_to_dict, roundtrip_ok
from skeleton.spine.taxonomy import REGION_COUNTS, Region, validate_catalog
from skeleton.spine.topology import has_cycle, is_connected, is_path_graph, validate_topology
from skeleton.spine.vertebra import Pose6


def check_law_counts() -> None:
    if VERTEBRA_N != 33:
        raise AssertionError("vertebra_n")
    if SEGMENT_N != 32:
        raise AssertionError("segment_n")
    if CERVICAL_N + THORACIC_N + LUMBAR_N + SACRAL_N + COCCYX_N != VERTEBRA_N:
        raise AssertionError("region-sum")
    if REGION_COUNTS[Region.CERVICAL] != CERVICAL_N:
        raise AssertionError("cervical")
    if REGION_COUNTS[Region.THORACIC] != THORACIC_N:
        raise AssertionError("thoracic")
    if REGION_COUNTS[Region.LUMBAR] != LUMBAR_N:
        raise AssertionError("lumbar")
    if REGION_COUNTS[Region.SACRAL] != SACRAL_N:
        raise AssertionError("sacral")
    if REGION_COUNTS[Region.COCCYX] != COCCYX_N:
        raise AssertionError("coccyx")
    if DOF_PER_SEGMENT != 6:
        raise AssertionError("dof")
    if TOPOLOGY_KIND != "path-33":
        raise AssertionError("topology-kind")
    if PACKET != "GB-20" or VERSION != "1.0":
        raise AssertionError("packet")
    if STORED_PROSE != 0:
        raise AssertionError("stored_prose")


def check_catalog() -> None:
    validate_catalog()


def check_chain_integrity() -> None:
    chain = default_chain()
    assert_chain_integrity(chain)
    if len(chain.vertebrae) != VERTEBRA_N or len(chain.segments) != SEGMENT_N:
        raise AssertionError("chain-counts")


def check_topology() -> None:
    topo = validate_topology()
    if topo.get("vertices") != VERTEBRA_N or topo.get("edges") != SEGMENT_N:
        raise AssertionError("topo-counts")
    if has_cycle() or not is_connected() or not is_path_graph():
        raise AssertionError("topo-shape")


def check_rom() -> None:
    chain = default_chain()
    if not all_rom_ok(chain.segments):
        raise AssertionError("rom-default")
    assert_dof_contract(chain.segments)
    # clamp extreme pose back into bounds
    seg = chain.segments[0]
    clamped = clamp_to_rom(seg, Pose6(rx=999.0, ry=-999.0, rz=50.0))
    if not all(
        abs(a) <= abs(b) + 1e-9
        for a, b in zip(clamped.as_tuple(), rom_hi_span(seg))
    ):
        # presence of finite clamp is enough; detailed check below
        pass
    b = __import__("skeleton.spine.articulation", fromlist=["rom_for_segment"]).rom_for_segment(seg)
    if not b.contains(clamped):
        raise AssertionError("rom-clamp")
    bad_postures = assert_postures_rom_safe()
    if bad_postures:
        raise AssertionError("posture-rom:" + ",".join(bad_postures))


def rom_hi_span(seg) -> tuple[float, ...]:
    from skeleton.spine.articulation import rom_for_segment

    b = rom_for_segment(seg)
    return tuple(max(abs(x), abs(y)) for x, y in zip(b.lo.as_tuple(), b.hi.as_tuple()))


def check_kinematics() -> None:
    chain = default_chain()
    frames_a = forward_frames(chain)
    frames_b = forward_frames(chain)
    if len(frames_a) != VERTEBRA_N:
        raise AssertionError("frame-n")
    if [(f.x, f.y, f.z, f.roll, f.pitch, f.yaw) for f in frames_a] != [
        (f.x, f.y, f.z, f.roll, f.pitch, f.yaw) for f in frames_b
    ]:
        raise AssertionError("kinematics-nondeterministic")
    tip = end_effector(chain)
    if path_length_mm(chain) <= 0 or tip.z <= 0:
        raise AssertionError("kinematics-degenerate")


def check_load_residual() -> None:
    chain = default_chain()
    path = build_axial_path(chain, cranial_fz=100.0, include_body_weights=False)
    if path.residual() > 1e-6:
        raise AssertionError("load-residual")
    if not is_conserved(path):
        raise AssertionError("load-not-conserved")
    # body-weight path must still have near-zero Kirchhoff residual
    path_bw = build_axial_path(chain, cranial_fz=100.0, include_body_weights=True)
    if path_bw.residual() > 1e-6:
        raise AssertionError("load-bw-residual")


def check_digests() -> None:
    a = default_chain()
    b = default_chain()
    da, db = chain_digest(a), chain_digest(b)
    assert_digest_format(da)
    assert_digest_format(db)
    if da != db:
        raise AssertionError("digest-unstable")
    if not digests_equal(a, b):
        raise AssertionError("digest-equal")


def check_postures() -> None:
    names = list_postures()
    if len(names) < 8:
        raise AssertionError("posture-count")
    base = default_chain()
    for name in names:
        p = build_posture(name, base)
        if not all_rom_ok(p.segments):
            raise AssertionError(f"posture-rom-{name}")
        if len(p.vertebrae) != VERTEBRA_N:
            raise AssertionError(f"posture-n-{name}")


def check_solver_projection() -> None:
    chain = default_chain()
    rel = {chain.segments[0].label: Pose6(rx=500.0, ry=-500.0)}
    bad = rebind_segments(chain, apply_relative_map(chain.segments, rel))
    if all_rom_ok(bad.segments):
        raise AssertionError("expected-violation")
    fixed = project_rom(bad)
    if not all_rom_ok(fixed.segments):
        raise AssertionError("project-rom")
    sat = satisfy(bad)
    if not all_rom_ok(sat.segments):
        raise AssertionError("satisfy")


def check_serialize_roundtrip() -> None:
    chain = default_chain()
    if not roundtrip_ok(chain):
        raise AssertionError("roundtrip")
    d = chain_to_dict(chain)
    restored = chain_from_dict(d)
    if not digests_equal(chain, restored):
        raise AssertionError("serialize-digest")
    if not same_topology(chain, restored):
        raise AssertionError("serialize-topo")


def check_compare_divergence() -> None:
    a = default_chain()
    b = build_posture("flexion_30", a)
    if similarity(a, b) >= 1.0:
        raise AssertionError("compare-identical")
    diff = diff_chains(a, b)
    if diff.pose_l2 <= 0 or not diff.changed_segments:
        raise AssertionError("compare-no-divergence")
    if not same_topology(a, b):
        raise AssertionError("compare-topo")


def check_capabilities() -> None:
    cap = capabilities()
    for key in ("owner", "contract", "failure_modes", "obs", "security"):
        if key not in cap:
            raise AssertionError("cap-" + key)
    if cap["owner"] != "spine":
        raise AssertionError("cap-owner")
    if cap["contract"]["vertebra_n"] != VERTEBRA_N:
        raise AssertionError("cap-n")
    if cap["contract"]["segment_n"] != SEGMENT_N:
        raise AssertionError("cap-seg")
    if cap["security"].get("network") != 0 or cap["security"].get("torch") != 0:
        raise AssertionError("cap-security")
    if cap["security"].get("ace") != "fail-closed":
        raise AssertionError("cap-ace")


def check_engine() -> None:
    card = SpineEngine().snapshot()
    if card["hit"] != 1:
        raise AssertionError("engine-hit")
    if card["stored_prose"] != 0:
        raise AssertionError("engine-prose")
    if card.get("vertebra_n") != VERTEBRA_N:
        raise AssertionError("engine-n")
    local = SpineEngine().verify_local()
    if local["ok"] != 1:
        raise AssertionError("engine-local:" + ",".join(local["failed"]))


def check_invariants() -> None:
    failed = check_all(default_chain())
    if failed:
        raise AssertionError("invariants:" + ",".join(failed))


# Sev1 = structural must-hold; Sev2 = behavioral contracts.
SEV1: tuple[Callable[[], None], ...] = (
    check_law_counts,
    check_catalog,
    check_chain_integrity,
    check_topology,
    check_rom,
    check_load_residual,
    check_digests,
    check_invariants,
)

SEV2: tuple[Callable[[], None], ...] = (
    check_kinematics,
    check_postures,
    check_solver_projection,
    check_serialize_roundtrip,
    check_compare_divergence,
    check_capabilities,
    check_engine,
)


def run_all() -> dict[str, Any]:
    """Fail-closed: any Sev1/Sev2 miss → ok=0. Never raises out."""
    failed: list[str] = []
    for fn in SEV1 + SEV2:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — gate must not escape
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {
        "ok": int(not failed),
        "failed": failed,
        "n": len(SEV1) + len(SEV2),
        "sev1": len(SEV1),
        "sev2": len(SEV2),
        "packet": PACKET,
    }
