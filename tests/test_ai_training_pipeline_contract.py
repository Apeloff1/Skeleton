"""Pipeline declarations conserve local candidate scope and executable APIs."""

import json

import pytest

from scripts.check_ai_training_pipeline import (
    APIS,
    ASSEMBLY,
    CONTRACTS,
    ROOT,
    TrainingPipelineContractError,
    validate,
)


@pytest.fixture
def candidate(tmp_path):
    paths = {ASSEMBLY, *CONTRACTS, *APIS, "machine/ai_app_construction.json"}
    assembly = json.loads((ROOT / ASSEMBLY).read_text())
    paths.update(
        (assembly["restart_acceptance"], assembly["operator_acceptance"], assembly["engine_acceptance"])
    )
    for path, (_, _, _, test_field) in CONTRACTS.items():
        paths.update(json.loads((ROOT / path).read_text())[test_field])
    for path in paths:
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / path).read_bytes())
    return tmp_path


def _change(root, path, modify):
    destination = root / path
    value = json.loads(destination.read_text())
    modify(value)
    destination.write_text(json.dumps(value))


def test_actual_pipeline_declares_executable_local_candidate_contracts():
    result = validate()
    assert result["contract_count"] == 9
    assert result["api_owner_count"] == 8
    assert result["production_model_promotion_authorized"] is False


@pytest.mark.parametrize(
    "field",
    [
        "production_model_promotion_authorized",
        "masterplan_completion_authorized",
        "distributed_execution_supported",
    ],
)
def test_pipeline_rejects_unsupported_authority(candidate, field):
    _change(candidate, ASSEMBLY, lambda value: value.update({field: True}))
    with pytest.raises(TrainingPipelineContractError, match="authority"):
        validate(candidate)


def test_nested_contract_cannot_grant_completion(candidate):
    _change(
        candidate,
        next(iter(CONTRACTS)),
        lambda value: value.update({"new_claim": {"completion_checkbox": True}}),
    )
    with pytest.raises(TrainingPipelineContractError, match="authority"):
        validate(candidate)


def test_contract_cannot_reassign_canonical_dataset_owner(candidate):
    _change(
        candidate, next(iter(CONTRACTS)), lambda value: value.update({"canonical_owner": "other/data.py"})
    )
    with pytest.raises(TrainingPipelineContractError, match="owner"):
        validate(candidate)


def test_pipeline_requires_restart_acceptance_executable(candidate):
    assembly = json.loads((candidate / ASSEMBLY).read_text())
    (candidate / assembly["restart_acceptance"]).write_text("# no executable acceptance\n")
    with pytest.raises(TrainingPipelineContractError, match="executable test"):
        validate(candidate)


def test_pipeline_requires_canonical_resume_api(candidate):
    path = candidate / "skeleton/ai/runtime/training/neural_trainer.py"
    path.write_text(path.read_text().replace("def load_artifact(", "def missing_artifact("))
    with pytest.raises(TrainingPipelineContractError, match="API drift"):
        validate(candidate)


def test_contract_json_duplicate_authority_cannot_shadow(candidate):
    path = candidate / ASSEMBLY
    text = path.read_text().replace(
        '"production_model_promotion_authorized": false',
        '"production_model_promotion_authorized": true, "production_model_promotion_authorized": false',
    )
    path.write_text(text)
    with pytest.raises(TrainingPipelineContractError, match="duplicate"):
        validate(candidate)


def test_pipeline_rejects_test_path_outside_owner(candidate):
    _change(candidate, ASSEMBLY, lambda value: value.update({"restart_acceptance": "../../other.py"}))
    with pytest.raises(TrainingPipelineContractError, match="canonical testing"):
        validate(candidate)


def test_exact_head_binding_rejects_other_revision():
    with pytest.raises(TrainingPipelineContractError, match="head mismatch"):
        validate(head="0" * 40)


def test_boolean_cannot_substitute_for_numeric_schema(candidate):
    _change(
        candidate,
        "machine/ai_model_lifecycle_persistence.json",
        lambda value: value.update({"schema_version": True}),
    )
    with pytest.raises(TrainingPipelineContractError, match="schema"):
        validate(candidate)


@pytest.mark.parametrize("field", ["restart_acceptance", "operator_acceptance", "engine_acceptance"])
def test_missing_assembly_acceptance_raises_typed_failure(candidate, field):
    _change(candidate, ASSEMBLY, lambda value: value.pop(field))
    with pytest.raises(TrainingPipelineContractError, match="acceptance"):
        validate(candidate)


def test_owner_mapping_type_raises_typed_failure(candidate):
    _change(
        candidate,
        "machine/ai_neural_training_resume_contract.json",
        lambda value: value.update({"canonical_owners": []}),
    )
    with pytest.raises(TrainingPipelineContractError, match="owner"):
        validate(candidate)


@pytest.mark.parametrize(
    "field",
    ["architecture_read_required", "construction_manual_read_required", "activation_receipt_required"],
)
def test_local_provider_cannot_bypass_mandatory_receipt(candidate, field):
    def remove_ack(value):
        provider = next(item for item in value["runtime_model_providers"] if item["id"] == "local")
        provider[field] = False

    _change(candidate, "machine/ai_app_construction.json", remove_ack)
    with pytest.raises(TrainingPipelineContractError, match="mandatory"):
        validate(candidate)


def test_local_provider_contract_cannot_gain_credentials(candidate):
    _change(
        candidate,
        "machine/ai_local_provider_activation.json",
        lambda value: value.update({"credentials": ["REMOTE_KEY"]}),
    )
    with pytest.raises(TrainingPipelineContractError, match="external authority"):
        validate(candidate)
