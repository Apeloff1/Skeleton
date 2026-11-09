from __future__ import annotations

import hashlib

import pytest

from skeleton.supply_chain.model_bom import MBOM, MBOMError, ModelComponent, ModelLineage


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def lineage() -> ModelLineage:
    return ModelLineage(
        "RUN.TRAIN.1",
        sha("train-evidence"),
        sha("opaque-dataset-ref"),
        "RUN.POST.1",
        sha("post-evidence"),
    )


def bom() -> MBOM:
    return MBOM(
        "MODEL.1",
        sha("model"),
        (
            ModelComponent("COMP.BASE", "base_model", sha("base")),
            ModelComponent("COMP.TOK", "tokenizer", sha("tok")),
        ),
        lineage(),
    )


def test_mbom_binds_exact_model_components_and_lineage() -> None:
    assert len(bom().digest) == 64


def test_model_artifact_change_changes_mbom_identity() -> None:
    original = bom()
    changed = MBOM(
        original.model_id,
        sha("different"),
        original.components,
        original.lineage,
    )
    assert original.digest != changed.digest


def test_dataset_is_recorded_as_opaque_digest_not_payload() -> None:
    assert bom().lineage.dataset_ref_digest == sha("opaque-dataset-ref")


def test_incomplete_post_training_lineage_rejected() -> None:
    with pytest.raises(MBOMError, match="incomplete"):
        ModelLineage(
            "RUN.TRAIN.1",
            sha("e"),
            sha("d"),
            "RUN.POST.1",
            None,
        )


def test_duplicate_component_identity_rejected() -> None:
    component = ModelComponent("COMP.BASE", "base_model", sha("base"))
    with pytest.raises(MBOMError, match="duplicate"):
        MBOM("MODEL.1", sha("m"), (component, component), lineage())


def test_component_collection_is_bounded_and_typed() -> None:
    component = ModelComponent("COMP.BASE", "base_model", sha("base"))
    with pytest.raises(MBOMError, match="non-empty tuple"):
        MBOM("MODEL.1", sha("m"), [component], lineage())  # type: ignore[arg-type]
    with pytest.raises(MBOMError, match="contain ModelComponent"):
        MBOM("MODEL.1", sha("m"), (object(),), lineage())  # type: ignore[arg-type]
    with pytest.raises(MBOMError, match="safety bound"):
        MBOM("MODEL.1", sha("m"), (component,) * 10_001, lineage())


def test_component_order_is_authoritative_and_canonical() -> None:
    base = ModelComponent("COMP.BASE", "base_model", sha("base"))
    tokenizer = ModelComponent("COMP.TOK", "tokenizer", sha("tok"))
    with pytest.raises(MBOMError, match="canonical order"):
        MBOM("MODEL.1", sha("m"), (tokenizer, base), lineage())


def test_lineage_and_identifiers_fail_closed() -> None:
    component = ModelComponent("COMP.BASE", "base_model", sha("base"))
    with pytest.raises(MBOMError, match="lineage must be"):
        MBOM("MODEL.1", sha("m"), (component,), object())  # type: ignore[arg-type]
    with pytest.raises(MBOMError, match="component_id must be stable"):
        ModelComponent("", "base_model", sha("base"))
    with pytest.raises(MBOMError, match="artifact_digest must be lowercase"):
        ModelComponent("COMP.BASE", "base_model", "A" * 64)


def test_exact_lineage_revision_changes_mbom_identity() -> None:
    original = bom()
    changed_lineage = ModelLineage(
        original.lineage.training_run_id,
        sha("different-training-evidence"),
        original.lineage.dataset_ref_digest,
        original.lineage.post_training_run_id,
        original.lineage.post_training_evidence_digest,
    )
    changed = MBOM(
        original.model_id,
        original.model_artifact_digest,
        original.components,
        changed_lineage,
    )
    assert original.digest != changed.digest


def test_mbom_replay_round_trips_exact_identity() -> None:
    original = bom()
    replayed = MBOM.from_dict(original.to_dict())
    assert replayed == original
    assert replayed.digest == original.digest


def test_mbom_replay_rejects_identity_tampering() -> None:
    payload = bom().to_dict()
    payload["model"] = sha("tampered-model")
    with pytest.raises(MBOMError, match="digest mismatch"):
        MBOM.from_dict(payload)


def test_mbom_replay_rejects_unknown_fields_and_schema() -> None:
    payload = bom().to_dict()
    payload["unexpected"] = "authority-confusion"
    with pytest.raises(MBOMError, match="fields must be exact"):
        MBOM.from_dict(payload)
    payload = bom().to_dict()
    payload["schema"] = "skeleton.model_bom.v2"
    with pytest.raises(MBOMError, match="unsupported"):
        MBOM.from_dict(payload)


def test_mbom_replay_rejects_noncanonical_component_order() -> None:
    payload = bom().to_dict()
    components = payload["components"]
    assert isinstance(components, list)
    payload["components"] = list(reversed(components))
    with pytest.raises(MBOMError, match="canonical order"):
        MBOM.from_dict(payload)


def test_mbom_replay_rejects_malformed_nested_shapes() -> None:
    payload = bom().to_dict()
    payload["components"] = [["COMP.BASE", "base_model"]]
    with pytest.raises(MBOMError, match="malformed MBOM component"):
        MBOM.from_dict(payload)
    payload = bom().to_dict()
    payload["lineage"] = ["RUN.TRAIN.1"]
    with pytest.raises(MBOMError, match="malformed MBOM lineage"):
        MBOM.from_dict(payload)
