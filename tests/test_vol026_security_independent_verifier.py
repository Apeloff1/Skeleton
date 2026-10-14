from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_vol026_security_closure import (
    CAPABILITY,
    CAPABILITY_CONTRACTS,
    CAPABILITY_MIRROR,
    CAPABILITY_TEST,
    EXPECTED_GAP,
    OUTBOUND_HTTP_TEST,
    REQUIRED_ASSETS,
    ROOTED_FS_TEST,
    SAST_SCRIPT,
    SECURITY_CONTRACTS,
    THREAT_MODEL,
    THREAT_MODEL_MIRROR,
    THREAT_TEST,
    TOOL_AUTH,
    TOOL_AUTH_MIRROR,
    TOOL_AUTH_TEST,
    WORKFLOW,
    WORKFLOW_REQUIRED_PATHS,
    verify_repository,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _behavior() -> dict[str, object]:
    validations = [
        CAPABILITY_TEST,
        CAPABILITY_TEST,
        THREAT_TEST,
        TOOL_AUTH_TEST,
        THREAT_TEST,
    ]
    return {
        "capability": {
            "scope": "tool-request-only",
            "grant_digest": "1" * 64,
            "expected_grant_digest": "1" * 64,
            "mismatch_denied": True,
            "duplicate_denied": True,
            "foreign_denied": True,
        },
        "tool_authorization": {
            "scope": "single-tool-request",
            "grant_digest": "2" * 64,
            "expected_grant_digest": "2" * 64,
            "mismatch_denied": True,
            "duplicate_denied": True,
            "foreign_denied": True,
        },
        "secrets": {
            "security_secret_has_value": False,
            "capability_secret_has_value": False,
        },
        "threat_model": {
            "digest": "3" * 64,
            "expected_digest": "3" * 64,
            "assets": list(REQUIRED_ASSETS),
            "ids": [
                "T-FS-001",
                "T-NET-001",
                "T-SECRET-001",
                "T-SUPPLY-001",
                "T-AUTH-001",
            ],
            "validation_paths": validations,
            "model_version": "vol026-v1",
        },
    }


def _valid_root(tmp_path: Path) -> Path:
    capability = "\n".join(
        (
            "from skeleton.contracts.canonical import canonical_json_bytes",
            "class CapabilityGrant: pass",
            "class SecurityContext: pass",
            "class ToolRequest: pass",
            'class AuthorizationReceipt: authority_scope:str="tool-request-only"',
            "def authorize_tool_request(): pass",
        )
    ) + "\n"
    threat = "\n".join(
        (
            "from skeleton.contracts.canonical import canonical_json_bytes",
            "class Threat: pass",
            "class ThreatModel: pass",
            "def canonical_vol026_threat_model(): pass",
            '# "tool-authority"',
            '# "network-egress"',
            '# "supply-chain"',
        )
    ) + "\n"
    tool_auth = "\n".join(
        (
            "from skeleton.contracts.canonical import canonical_json_bytes",
            "class SecurityContext: pass",
            "class ToolRequest: pass",
            'class AuthorizationReceipt: scope:str="single-tool-request"',
            "def authorize_tool_request(): pass",
        )
    ) + "\n"

    for canonical, mirror, data in (
        (CAPABILITY, CAPABILITY_MIRROR, capability),
        (THREAT_MODEL, THREAT_MODEL_MIRROR, threat),
        (TOOL_AUTH, TOOL_AUTH_MIRROR, tool_auth),
    ):
        _write(tmp_path / canonical, data)
        _write(tmp_path / mirror, data)

    _write(tmp_path / SECURITY_CONTRACTS, "class SecretRef: pass\n")
    _write(tmp_path / CAPABILITY_CONTRACTS, "class SecretRef: pass\n")
    for relative in (
        CAPABILITY_TEST,
        THREAT_TEST,
        TOOL_AUTH_TEST,
        ROOTED_FS_TEST,
        OUTBOUND_HTTP_TEST,
        SAST_SCRIPT,
    ):
        _write(tmp_path / relative, "# focused security validation\n")

    _write(
        tmp_path / WORKFLOW,
        "\n".join(WORKFLOW_REQUIRED_PATHS) + "\n",
    )
    _write(
        tmp_path / "machine/ai_master_plan.json",
        json.dumps(
            {
                "volumes": [
                    {
                        "key": "VOL-026",
                        "requirements": [
                            "Enforce least privilege across model and tool boundaries.",
                            "Authorize resources at the last responsible moment.",
                            "Keep secrets referenced rather than copied into prompts.",
                        ],
                        "capabilities": [
                            "identity/access security",
                            "sandbox/egress controls",
                            "supply-chain security",
                        ],
                        "gaps": [EXPECTED_GAP],
                    }
                ]
            }
        ),
    )
    return tmp_path


def test_independent_security_verifier_accepts_exact_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_root(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "security-head")

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "security-head"
    assert len(receipt["mirror_digests"]) == 3


def test_verifier_rejects_capability_scope_widening(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    behavior = _behavior()
    behavior["capability"]["scope"] = "session"

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any("capability authorization scope widened" in e for e in receipt["errors"])


def test_verifier_rejects_tool_authorization_scope_widening(
    tmp_path: Path,
) -> None:
    root = _valid_root(tmp_path)
    behavior = _behavior()
    behavior["tool_authorization"]["scope"] = "multi-tool-session"

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any("tool authorization scope widened" in e for e in receipt["errors"])


def test_verifier_rejects_exact_match_failure(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    behavior = _behavior()
    behavior["capability"]["mismatch_denied"] = False
    behavior["tool_authorization"]["duplicate_denied"] = False

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any(
        "capability authorization failed closed: mismatch_denied" in e
        for e in receipt["errors"]
    )
    assert any(
        "tool authorization failed closed: duplicate_denied" in e
        for e in receipt["errors"]
    )


def test_verifier_rejects_secret_value_surface(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    behavior = _behavior()
    behavior["secrets"]["security_secret_has_value"] = True

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any("SecretRef exposes a value field" in e for e in receipt["errors"])


def test_verifier_rejects_missing_threat_boundary(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    behavior = _behavior()
    behavior["threat_model"]["assets"] = list(REQUIRED_ASSETS[:-1])

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any("threat-model coverage mismatch" in e for e in receipt["errors"])


def test_verifier_rejects_missing_threat_validation_target(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    behavior = _behavior()
    behavior["threat_model"]["validation_paths"][0] = "tests/missing-security-check.py"

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any("validation target is missing" in e for e in receipt["errors"])


def test_verifier_rejects_noncanonical_identity_receipts(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    behavior = _behavior()
    behavior["capability"]["grant_digest"] = "4" * 64
    behavior["threat_model"]["digest"] = "5" * 64

    receipt = verify_repository(root, behavior=behavior)

    assert receipt["valid"] is False
    assert any("grant identity is not shared-canonical" in e for e in receipt["errors"])
    assert any("threat-model identity is not shared-canonical" in e for e in receipt["errors"])


def test_verifier_rejects_security_mirror_drift(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    _write(root / CAPABILITY_MIRROR, "# mirror drift\n")

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is False
    assert any("canonical AI mirror drift" in e for e in receipt["errors"])


def test_verifier_rejects_private_serializer_regression(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    text = (root / THREAT_MODEL).read_text(encoding="utf-8")
    text += "x = json.dumps({})\n"
    _write(root / THREAT_MODEL, text)
    _write(root / THREAT_MODEL_MIRROR, text)

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is False
    assert any("private JSON identity serializer" in e for e in receipt["errors"])


def test_verifier_rejects_workflow_coverage_loss(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    workflow = root / WORKFLOW
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            TOOL_AUTH_TEST + "\n",
            "",
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is False
    assert any(
        "lost VOL-026 verification coverage" in e and TOOL_AUTH_TEST in e
        for e in receipt["errors"]
    )


def test_verifier_rejects_masterplan_security_contract_drift(tmp_path: Path) -> None:
    root = _valid_root(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["capabilities"] = ["identity/access security"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root, behavior=_behavior())

    assert receipt["valid"] is False
    assert any("VOL-026 capability drift" in e for e in receipt["errors"])
