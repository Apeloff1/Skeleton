"""Public API contracts for durable Merkle evidence surfaces."""

from __future__ import annotations

import inspect

import pytest

import skeleton.shells.ai as ai
from skeleton.shells.ai.durable_merkle import (
    MERKLE_ALGORITHM,
    MERKLE_CHECKPOINT_ARTIFACT,
    DurableMerkleAuthority,
    DurableMerkleChainKind,
    DurableMerkleCheckpoint,
    DurableMerkleError,
    DurableMerkleLeaf,
    DurableMerkleProof,
    DurableMerkleProofStep,
    DurableMerkleSide,
    DurableMerkleVerification,
    SignedDurableMerkleCheckpoint,
)
from skeleton.shells.ai.durable_merkle_health import (
    DurableMerkleHealthError,
    DurableMerkleHealthFinding,
    DurableMerkleHealthGuard,
    DurableMerkleHealthPolicy,
    DurableMerkleHealthReport,
    DurableMerkleHealthSeverity,
)
from skeleton.shells.ai.durable_merkle_operator import (
    DurableMerkleOperatorError,
    DurableMerkleOperatorResult,
    DurableMerkleOperatorStatus,
    DurableSessionMerkleOperator,
)
from skeleton.shells.ai.durable_merkle_session import (
    DurableSessionMerkleAuthority,
    DurableSessionMerkleError,
    DurableSessionMerkleProofBundle,
    DurableSessionMerkleVerification,
)
from skeleton.shells.ai.durable_merkle_store import (
    DurableMerkleBundleCommit,
    DurableMerkleBundleConflict,
    DurableMerkleBundleCorruption,
    DurableMerkleBundleIndex,
    DurableMerkleBundleStoreError,
    DurableSessionMerkleBundleStore,
    StoredDurableMerkleBundle,
    StoredDurableMerkleBundleIndex,
)


MERKLE_EXPORTS = {
    "MERKLE_ALGORITHM": MERKLE_ALGORITHM,
    "MERKLE_CHECKPOINT_ARTIFACT": MERKLE_CHECKPOINT_ARTIFACT,
    "DurableMerkleAuthority": DurableMerkleAuthority,
    "DurableMerkleChainKind": DurableMerkleChainKind,
    "DurableMerkleCheckpoint": DurableMerkleCheckpoint,
    "DurableMerkleError": DurableMerkleError,
    "DurableMerkleLeaf": DurableMerkleLeaf,
    "DurableMerkleProof": DurableMerkleProof,
    "DurableMerkleProofStep": DurableMerkleProofStep,
    "DurableMerkleSide": DurableMerkleSide,
    "DurableMerkleVerification": DurableMerkleVerification,
    "SignedDurableMerkleCheckpoint": SignedDurableMerkleCheckpoint,
    "DurableSessionMerkleAuthority": DurableSessionMerkleAuthority,
    "DurableSessionMerkleError": DurableSessionMerkleError,
    "DurableSessionMerkleProofBundle": DurableSessionMerkleProofBundle,
    "DurableSessionMerkleVerification": DurableSessionMerkleVerification,
    "DurableMerkleBundleCommit": DurableMerkleBundleCommit,
    "DurableMerkleBundleConflict": DurableMerkleBundleConflict,
    "DurableMerkleBundleCorruption": DurableMerkleBundleCorruption,
    "DurableMerkleBundleIndex": DurableMerkleBundleIndex,
    "DurableMerkleBundleStoreError": DurableMerkleBundleStoreError,
    "DurableSessionMerkleBundleStore": DurableSessionMerkleBundleStore,
    "StoredDurableMerkleBundle": StoredDurableMerkleBundle,
    "StoredDurableMerkleBundleIndex": StoredDurableMerkleBundleIndex,
    "DurableMerkleOperatorError": DurableMerkleOperatorError,
    "DurableMerkleOperatorResult": DurableMerkleOperatorResult,
    "DurableMerkleOperatorStatus": DurableMerkleOperatorStatus,
    "DurableSessionMerkleOperator": DurableSessionMerkleOperator,
    "DurableMerkleHealthError": DurableMerkleHealthError,
    "DurableMerkleHealthFinding": DurableMerkleHealthFinding,
    "DurableMerkleHealthGuard": DurableMerkleHealthGuard,
    "DurableMerkleHealthPolicy": DurableMerkleHealthPolicy,
    "DurableMerkleHealthReport": DurableMerkleHealthReport,
    "DurableMerkleHealthSeverity": DurableMerkleHealthSeverity,
}


@pytest.mark.parametrize(
    "name,value",
    sorted(MERKLE_EXPORTS.items()),
)
def test_ai_package_exports_merkle_surface(name, value):
    assert hasattr(ai, name)
    assert getattr(ai, name) is value
    assert name in ai.__all__


def test_no_duplicate_ai_exports_after_merkle_surface():
    assert len(ai.__all__) == len(set(ai.__all__))


def test_merkle_constants_are_wire_stable():
    assert MERKLE_ALGORITHM == "sha256-domain-separated-merkle-v1"
    assert (
        MERKLE_CHECKPOINT_ARTIFACT
        == "shell-ai-durable-merkle-checkpoint-v1"
    )


def test_merkle_chain_kind_values_are_wire_stable():
    assert {
        item.value
        for item in DurableMerkleChainKind
    } == {
        "journal",
        "receipts",
    }


def test_merkle_side_values_are_wire_stable():
    assert {
        item.value
        for item in DurableMerkleSide
    } == {
        "left",
        "right",
    }


def test_merkle_operator_status_values_are_wire_stable():
    assert {
        item.value
        for item in DurableMerkleOperatorStatus
    } == {
        "verified",
        "incomplete",
        "manual_review",
        "missing",
    }


@pytest.mark.parametrize(
    "method",
    [
        "build",
        "prove",
        "proofs_for_sequences",
        "inspect_proof",
        "require_proof",
        "verify_checkpoint_signature",
        "verify_checkpoint_against_chain",
        "merkle_root",
        "leaves_digest",
        "reconstruct_root",
    ],
)
def test_merkle_authority_method_surface(method):
    assert callable(
        getattr(
            DurableMerkleAuthority,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    [
        "build",
        "inspect",
        "require",
    ],
)
def test_session_merkle_authority_method_surface(method):
    assert callable(
        getattr(
            DurableSessionMerkleAuthority,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    [
        "put_once",
        "get_by_digest",
        "get_by_finalization",
        "index",
        "repair_index",
        "require_finalization",
        "verify_index",
    ],
)
def test_merkle_bundle_store_method_surface(method):
    assert callable(
        getattr(
            DurableSessionMerkleBundleStore,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    [
        "inspect",
        "prepare",
        "require",
        "verify_stored",
    ],
)
def test_merkle_operator_method_surface(method):
    assert callable(
        getattr(
            DurableSessionMerkleOperator,
            method,
            None,
        )
    )


def test_merkle_authority_constructor_contract():
    signature = inspect.signature(
        DurableMerkleAuthority
    )
    assert {
        "signer",
        "max_leaves",
    }.issubset(signature.parameters)


def test_session_merkle_authority_constructor_contract():
    signature = inspect.signature(
        DurableSessionMerkleAuthority
    )
    assert {
        "merkle",
        "journal_chain_id",
        "receipt_chain_id",
    }.issubset(signature.parameters)


def test_merkle_bundle_store_constructor_contract():
    signature = inspect.signature(
        DurableSessionMerkleBundleStore
    )
    assert {
        "backend",
        "namespace",
    }.issubset(signature.parameters)


def test_merkle_operator_constructor_contract():
    signature = inspect.signature(
        DurableSessionMerkleOperator
    )
    assert {
        "finalizations",
        "recovery_checkpoints",
        "session_evidence",
        "journal",
        "receipt_chain",
        "recovery_verifier",
        "merkle_authority",
        "bundle_store",
    }.issubset(signature.parameters)


def test_checkpoint_has_digest_property():
    assert isinstance(
        DurableMerkleCheckpoint.digest,
        property,
    )


def test_signed_checkpoint_has_digest_property():
    assert isinstance(
        SignedDurableMerkleCheckpoint.digest,
        property,
    )


def test_proof_has_digest_property():
    assert isinstance(
        DurableMerkleProof.digest,
        property,
    )


def test_session_bundle_has_digest_property():
    assert isinstance(
        DurableSessionMerkleProofBundle.digest,
        property,
    )


def test_session_bundle_exposes_journal_chain_root_property():
    assert isinstance(
        DurableSessionMerkleProofBundle.journal_chain_root,
        property,
    )


def test_operator_result_boolean_properties():
    assert isinstance(
        DurableMerkleOperatorResult.ok,
        property,
    )
    assert isinstance(
        DurableMerkleOperatorResult.safe_to_resume,
        property,
    )
    assert isinstance(
        DurableMerkleOperatorResult.requires_manual_review,
        property,
    )


def test_public_merkle_types_have_docstrings():
    for value in (
        DurableMerkleAuthority,
        DurableMerkleLeaf,
        DurableMerkleCheckpoint,
        DurableMerkleProof,
        DurableSessionMerkleAuthority,
        DurableSessionMerkleProofBundle,
        DurableSessionMerkleBundleStore,
        DurableSessionMerkleOperator,
    ):
        assert inspect.getdoc(value)


def test_direct_and_package_merkle_authority_are_same_class():
    from skeleton.shells.ai import (
        DurableMerkleAuthority as RootImport,
    )

    assert RootImport is DurableMerkleAuthority


def test_direct_and_package_merkle_operator_are_same_class():
    from skeleton.shells.ai import (
        DurableSessionMerkleOperator as RootImport,
    )

    assert RootImport is DurableSessionMerkleOperator


def test_direct_and_package_bundle_store_are_same_class():
    from skeleton.shells.ai import (
        DurableSessionMerkleBundleStore as RootImport,
    )

    assert RootImport is DurableSessionMerkleBundleStore


def test_direct_and_package_session_authority_are_same_class():
    from skeleton.shells.ai import (
        DurableSessionMerkleAuthority as RootImport,
    )

    assert RootImport is DurableSessionMerkleAuthority


@pytest.mark.parametrize(
    "value",
    [
        "journal",
        "receipts",
    ],
)
def test_chain_kind_round_trip(value):
    assert DurableMerkleChainKind(value).value == value


@pytest.mark.parametrize(
    "value",
    [
        "left",
        "right",
    ],
)
def test_side_round_trip(value):
    assert DurableMerkleSide(value).value == value


@pytest.mark.parametrize(
    "value",
    [
        "verified",
        "incomplete",
        "manual_review",
        "missing",
    ],
)
def test_operator_status_round_trip(value):
    assert DurableMerkleOperatorStatus(value).value == value

def test_merkle_health_severity_values_are_wire_stable():
    assert {
        item.value
        for item in DurableMerkleHealthSeverity
    } == {
        "warning",
        "error",
    }


def test_merkle_health_guard_constructor_contract():
    signature = inspect.signature(
        DurableMerkleHealthGuard
    )
    assert {
        "operator",
        "policy",
    }.issubset(signature.parameters)


@pytest.mark.parametrize(
    "method",
    ["inspect", "require"],
)
def test_merkle_health_guard_method_surface(method):
    assert callable(
        getattr(
            DurableMerkleHealthGuard,
            method,
            None,
        )
    )


def test_merkle_health_policy_digest_property():
    assert isinstance(
        DurableMerkleHealthPolicy.digest,
        property,
    )


def test_merkle_health_report_digest_property():
    assert isinstance(
        DurableMerkleHealthReport.digest,
        property,
    )


def test_package_merkle_health_guard_is_canonical_class():
    from skeleton.shells.ai import (
        DurableMerkleHealthGuard as RootImport,
    )

    assert RootImport is DurableMerkleHealthGuard
