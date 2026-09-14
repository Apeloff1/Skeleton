from core.product_control_plane import ProductControlPlane


def test_control_plane_checkpoints_epistemic_state_into_system_root(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    assurance = plane.assurance_report()
    assert assurance["hard_failures"] == 0
    invariant_ids = {row["id"] for row in assurance["invariants"]}
    assert "truth.transparency-prefix-aligned" in invariant_ids
    assert "truth.gossip-no-equivocation" in invariant_ids
    assert "truth.witness-ledger-coherent" in invariant_ids
    assert "truth.finality-ledger-coherent" in invariant_ids

    status = plane.status()
    trust = status["epistemic_trust"]
    assert trust["transparency"]["verified"] is True
    assert trust["transparency"]["prefix_aligned"] is True
    assert trust["transparency"]["transparency_entries"] >= 1
    assert trust["gossip"]["healthy"] is True
    assert trust["integrity_healthy"] is True

    components = {row["name"] for row in status["system_root"]["components"]}
    assert "epistemic_trust" in components
    assert "epistemic_root" in components


def test_split_view_blocks_assurance_and_rotates_system_root(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    before = plane.system_root()["root_sha256"]
    descriptor = plane.epistemic_transparency.log.descriptor()
    conflicting_root = "f" * 64
    if descriptor["root_sha256"] == conflicting_root:
        conflicting_root = "e" * 64

    result = plane.epistemic_gossip.observe(
        log_id=descriptor["log_id"],
        tree_size=descriptor["tree_size"],
        root_sha256=conflicting_root,
        source="external-observer",
    )
    assert result["disposition"] == "split_view"

    assurance = plane.assurance_report()
    assert assurance["posture"] == "blocked"
    assert any(row["id"] == "truth.gossip-no-equivocation" and not row["passed"] for row in assurance["invariants"])
    assert any(row["id"] == "truth.trust-runtime-integrity" and not row["passed"] for row in assurance["invariants"])
    after = plane.system_root()["root_sha256"]
    assert after != before


def test_transparency_state_is_idempotent_when_epistemic_state_is_unchanged(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    plane.assurance_report()
    first = plane.epistemic_transparency.log.descriptor()
    observations = plane.epistemic_gossip.status()["observations"]

    plane.assurance_report()
    second = plane.epistemic_transparency.log.descriptor()
    assert second == first
    assert plane.epistemic_gossip.status()["observations"] == observations
