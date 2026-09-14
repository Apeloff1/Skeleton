import pytest

from core.epistemic_trust_runtime import EpistemicTrustRuntime
from core.transparency_witness import TrustedWitness
from core.transparency_witness_config import WitnessPolicyConfig, load_witness_policy


def _policy(required=False):
    return WitnessPolicyConfig(
        witnesses=(
            TrustedWitness("a", "group-a"),
            TrustedWitness("b", "group-b"),
            TrustedWitness("c", "group-c"),
        ),
        required_groups=3,
        finality_required=required,
    )


def test_publication_is_provisional_until_independent_witness_quorum(tmp_path):
    runtime = EpistemicTrustRuntime(tmp_path, policy=_policy())
    published = runtime.publish(authority_root_sha256="1" * 64, epistemic_root_sha256="2" * 64,
                                observed_at="2026-09-14T16:40:00+00:00")
    descriptor = published["transparency"]
    assert runtime.finality_for_current_head()["finalized"] is False
    assert runtime.maybe_finalize()["finalized"] is False

    for witness_id in ("a", "b", "c"):
        runtime.observe_witness(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"],
                                root_sha256=descriptor["root_sha256"], witness_id=witness_id,
                                transport_authenticated=True)
    result = runtime.maybe_finalize()
    assert result["finalized"] is True
    assert runtime.finality_for_current_head()["finalized"] is True
    assert runtime.status()["healthy"] is True


def test_finality_required_changes_health_without_changing_truth_semantics(tmp_path):
    runtime = EpistemicTrustRuntime(tmp_path, policy=_policy(required=True))
    published = runtime.publish(authority_root_sha256="3" * 64, epistemic_root_sha256="4" * 64)
    assert runtime.status()["healthy"] is False
    descriptor = published["transparency"]
    for witness_id in ("a", "b", "c"):
        runtime.observe_witness(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"],
                                root_sha256=descriptor["root_sha256"], witness_id=witness_id,
                                transport_authenticated=True)
    runtime.finalize()
    assert runtime.status()["healthy"] is True


def test_split_view_degrades_runtime_even_after_finality(tmp_path):
    runtime = EpistemicTrustRuntime(tmp_path, policy=_policy())
    published = runtime.publish(authority_root_sha256="5" * 64, epistemic_root_sha256="6" * 64)
    descriptor = published["transparency"]
    for witness_id in ("a", "b", "c"):
        runtime.observe_witness(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"],
                                root_sha256=descriptor["root_sha256"], witness_id=witness_id,
                                transport_authenticated=True)
    runtime.finalize()
    runtime.observe_peer_head(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"],
                              root_sha256="f" * 64, source="hostile-observer")
    status = runtime.status()
    assert status["gossip"]["split_views"] == 1
    assert status["healthy"] is False


def test_required_finality_policy_rejects_unsatisfiable_registry():
    with pytest.raises(ValueError, match="cannot satisfy quorum"):
        load_witness_policy(raw_json='[{"id":"a","independence_group":"one"}]', required_groups=2,
                            finality_required=True)
