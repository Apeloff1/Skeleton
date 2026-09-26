from __future__ import annotations

import json
from pathlib import Path

from scripts.check_provider_capability_matrix import (
    CONFLICT_DOMAIN,
    KNOWN_CAPABILITIES,
    ROUTING_FIELDS,
    SCHEMA_VERSION,
    STATUSES,
    TASK_ID,
    VENDOR_ALIASES,
    capability_status,
    main,
    validate_provider_capability_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _cap(name: str, status: str, evidence_refs=None):
    if evidence_refs is None:
        evidence_refs = [] if status == "unknown" else [f"evidence:{name}"]
    return {"name": name, "status": status, "evidence_refs": evidence_refs}


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "providers": [
            {
                "provider_id": "adapter.local",
                "capabilities": [
                    _cap("chat", "supported"),
                    _cap("tools", "unsupported", ["probe:tools-absent"]),
                    _cap("vision", "unknown"),
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_schema_contract_is_capability_matrix_not_model_routing() -> None:
    assert SCHEMA_VERSION == 1
    assert TASK_ID == "reserve-S051-provider-capability-matrix"
    assert CONFLICT_DOMAIN == "ai.spec.provider_capabilities"
    assert STATUSES == ("supported", "unsupported", "unknown")
    assert "unknown" in STATUSES
    assert KNOWN_CAPABILITIES == (
        "chat",
        "tools",
        "streaming",
        "embeddings",
        "structured_output",
        "vision",
        "audio",
    )
    source = (REPO_ROOT / "scripts" / "check_provider_capability_matrix.py").read_text(
        encoding="utf-8"
    )
    assert "import model_routing" not in source
    assert "from skeleton.frontier" not in source
    assert "selected_model" in source
    for field in ("selected_model", "fallback_model", "routing_score"):
        assert field in ROUTING_FIELDS
    errors = validate_provider_capability_matrix(["bad"])
    assert errors and errors[0].startswith("provider-capability ")


def test_valid_document_has_no_violations() -> None:
    assert validate_provider_capability_matrix(_doc()) == []


def test_unknown_capability_status_is_accepted() -> None:
    document = _doc(
        providers=[
            {
                "provider_id": "adapter.local",
                "capabilities": [_cap("audio", "unknown")],
            }
        ]
    )
    assert validate_provider_capability_matrix(document) == []
    assert capability_status(document, "adapter.local", "audio") == "unknown"


def test_missing_capability_row_remains_unknown_never_unsupported() -> None:
    document = _doc()
    assert capability_status(document, "adapter.local", "streaming") == "unknown"
    assert capability_status(document, "adapter.local", "embeddings") == "unknown"
    assert capability_status(document, "adapter.local", "structured_output") == "unknown"
    assert capability_status(document, "missing-provider", "chat") == "unknown"


def test_vendor_alias_is_never_guessed_as_known_capability() -> None:
    document = _doc()
    assert "function_calling" in VENDOR_ALIASES
    assert capability_status(document, "adapter.local", "function_calling") == "unknown"
    assert capability_status(document, "adapter.local", "json_mode") == "unknown"
    guessed = _doc(
        providers=[
            {
                "provider_id": "adapter.local",
                "capabilities": [_cap("function_calling", "supported", ["sdk:openai"])],
            }
        ]
    )
    errors = validate_provider_capability_matrix(guessed)
    assert any("provider-capability unknown guessed_capability" in item for item in errors)
    assert any("function_calling" in item for item in errors)
    assert capability_status(guessed, "adapter.local", "tools") == "unknown"


def test_unknown_name_with_unknown_status_remains_unknown() -> None:
    document = _doc(
        providers=[
            {
                "provider_id": "adapter.local",
                "capabilities": [_cap("function_calling", "unknown")],
            }
        ]
    )
    assert validate_provider_capability_matrix(document) == []
    assert capability_status(document, "adapter.local", "function_calling") == "unknown"
    assert capability_status(document, "adapter.local", "tools") == "unknown"


def test_sibling_capabilities_are_not_inferred() -> None:
    document = _doc(
        providers=[
            {
                "provider_id": "adapter.local",
                "capabilities": [_cap("chat", "supported"), _cap("tools", "supported")],
            }
        ]
    )
    assert validate_provider_capability_matrix(document) == []
    assert capability_status(document, "adapter.local", "structured_output") == "unknown"
    assert capability_status(document, "adapter.local", "streaming") == "unknown"


def test_guessed_status_fails_closed() -> None:
    for guessed in ("likely", "assumed", "inferred", "probably", True, False):
        errors = validate_provider_capability_matrix(
            _doc(
                providers=[
                    {
                        "provider_id": "adapter.local",
                        "capabilities": [_cap("chat", guessed, ["note:guess"])],
                    }
                ]
            )
        )
        assert any("provider-capability unknown guessed_status" in item for item in errors), guessed


def test_supported_without_evidence_fails_closed() -> None:
    errors = validate_provider_capability_matrix(
        _doc(
            providers=[
                {
                    "provider_id": "adapter.local",
                    "capabilities": [_cap("chat", "supported", [])],
                }
            ]
        )
    )
    assert any("provider-capability missing_value evidence_refs" in item for item in errors)


def test_unknown_fields_fail_closed() -> None:
    errors = validate_provider_capability_matrix(_doc(severity="high", selected_model="gpt"))
    assert any("provider-capability unknown field" in item for item in errors)
    assert any("severity" in item for item in errors)
    assert any("provider-capability unknown routing_field" in item for item in errors)


def test_routing_fields_on_provider_fail_closed() -> None:
    errors = validate_provider_capability_matrix(
        _doc(
            providers=[
                {
                    "provider_id": "adapter.local",
                    "fallback_model": "other",
                    "capabilities": [_cap("chat", "supported")],
                }
            ]
        )
    )
    assert any("provider-capability unknown routing_field" in item for item in errors)
    assert any("fallback_model" in item for item in errors)


def test_missing_fields_fail_closed() -> None:
    document = _doc()
    del document["providers"]
    errors = validate_provider_capability_matrix(document)
    assert any("provider-capability missing_value field" in item for item in errors)
    assert any("providers" in item for item in errors)


def test_wrong_schema_version_fails_closed() -> None:
    errors = validate_provider_capability_matrix(_doc(schema_version=2))
    assert any("provider-capability unknown schema_version" in item for item in errors)
    bool_version = validate_provider_capability_matrix(_doc(schema_version=True))
    assert any("provider-capability unknown schema_version" in item for item in bool_version)


def test_duplicate_provider_and_capability_fail_closed() -> None:
    dup_provider = validate_provider_capability_matrix(
        _doc(
            providers=[
                {"provider_id": "adapter.local", "capabilities": [_cap("chat", "supported")]},
                {"provider_id": "adapter.local", "capabilities": [_cap("tools", "unsupported")]},
            ]
        )
    )
    assert any("provider-capability unknown duplicate_provider" in item for item in dup_provider)
    dup_cap = validate_provider_capability_matrix(
        _doc(
            providers=[
                {
                    "provider_id": "adapter.local",
                    "capabilities": [_cap("chat", "supported"), _cap("chat", "unknown")],
                }
            ]
        )
    )
    assert any("provider-capability unknown duplicate_capability" in item for item in dup_cap)


def test_non_object_root_fails_closed() -> None:
    errors = validate_provider_capability_matrix(["not", "an", "object"])
    assert errors == [
        "provider-capability unknown root_type: provider capability matrix must be an object"
    ]


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "provider-capability-matrix.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Provider-capability matrix schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_guessed_capability(tmp_path: Path, capsys) -> None:
    path = tmp_path / "provider-capability-matrix.json"
    path.write_text(
        json.dumps(
            _doc(
                providers=[
                    {
                        "provider_id": "adapter.local",
                        "capabilities": [_cap("json_mode", "supported", ["guess"])],
                    }
                ]
            )
        ),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Provider-capability matrix validation failed:" in stderr
    assert "provider-capability unknown guessed_capability" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "provider-capability unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_provider_matrix_is_wired_into_quality_gates_and_routing() -> None:
    quality_gates = (
        REPO_ROOT / "scripts" / "quality-gates.sh"
    ).read_text(encoding="utf-8")
    assert "check_provider_capability_matrix.py" in quality_gates
    assert "test_provider_capability_matrix.py" in quality_gates
    routing = REPO_ROOT / "skeleton" / "frontier" / "model_routing.py"
    assert routing.exists()
