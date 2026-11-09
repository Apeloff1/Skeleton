from __future__ import annotations

from hashlib import sha256
import math

import pytest

from skeleton.ai.research.model_internals.reverse_engineering import (
    ArtifactProvenance,
    AuthorizationScope,
    Observation,
    ProbeCase,
    ProbeKind,
    ReverseEngineeringError,
    ReverseEngineeringSession,
)
from skeleton.ai.research.model_internals.reverse_engineering.provenance import RightsBasis


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_probe_payload_rejects_noncanonical_values_early():
    with pytest.raises(ReverseEngineeringError, match="canonical JSON"):
        ProbeCase("bad", ProbeKind.CUSTOM, {"value": math.nan})


def test_observation_rejects_non_hex_sha256_length_strings():
    with pytest.raises(ReverseEngineeringError, match="sha256 hex"):
        Observation(
            target_id="t",
            probe_id="p",
            kind=ProbeKind.CUSTOM,
            input_digest="z" * 64,
            output_digest=d("ok"),
            output_shape="text",
            success=True,
        )


def test_provenance_rejects_non_hex_content_digest():
    with pytest.raises(ReverseEngineeringError, match="sha256 hex"):
        ArtifactProvenance(
            artifact_id="a",
            source_uri="file:///owned/a",
            rights_basis=RightsBasis.OWNED,
            content_sha256="x" * 64,
        )


def test_mapping_keys_with_same_string_form_do_not_collide():
    session = ReverseEngineeringSession(
        authorization=AuthorizationScope(target_ids=("t",), purpose="normalization"),
    )
    probe = ProbeCase("p", ProbeKind.CUSTOM, {"x": 1})
    left = session.inspect(
        target_id="t",
        target=lambda _: {1: "integer", "1": "string"},
        probes=(probe,),
    )
    right = session.inspect(
        target_id="t",
        target=lambda _: {"1": "string", 1: "integer"},
        probes=(probe,),
    )
    assert left.evidence.digest == right.evidence.digest


def test_unsupported_runtime_objects_fail_closed_instead_of_hashing_repr_address():
    class RuntimeObject:
        pass

    session = ReverseEngineeringSession(
        authorization=AuthorizationScope(target_ids=("t",), purpose="normalization"),
    )
    with pytest.raises(ReverseEngineeringError, match="unsupported output type"):
        session.inspect(
            target_id="t",
            target=lambda _: RuntimeObject(),
            probes=(ProbeCase("p", ProbeKind.CUSTOM, {"x": 1}),),
        )
