#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-026 cybersecurity closure.

The verifier does not import the security implementation modules into its own
process. It inspects repository boundaries as files and executes a fixed
least-privilege/threat-model fixture in a fresh Python subprocess. The returned
receipt is then judged independently for exact-match authorization, ambiguity
rejection, secret-reference isolation, threat coverage, canonical identities,
and non-escalating authorization scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

from skeleton.contracts.canonical import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]

CAPABILITY = "skeleton/security/capability_security.py"
CAPABILITY_MIRROR = "skeleton/ai/runtime/security/capability_security.py"
THREAT_MODEL = "skeleton/security/threat_model.py"
THREAT_MODEL_MIRROR = "skeleton/ai/runtime/security/threat_model.py"
TOOL_AUTH = "skeleton/security/tool_authorization.py"
TOOL_AUTH_MIRROR = "skeleton/ai/runtime/security/tool_authorization.py"
SECURITY_CONTRACTS = "skeleton/security/contracts.py"
CAPABILITY_CONTRACTS = "skeleton/security/capability_contracts.py"
CAPABILITY_TEST = "skeleton/testing/test_vol026_capability_security.py"
THREAT_TEST = "skeleton/testing/test_vol026_threat_model.py"
TOOL_AUTH_TEST = "skeleton/testing/test_vol026_tool_authorization.py"
ROOTED_FS_TEST = "skeleton/testing/test_security_rooted_fs.py"
OUTBOUND_HTTP_TEST = "skeleton/testing/test_security_outbound_http.py"
SAST_SCRIPT = "scripts/check_repository_python_sast.py"
WORKFLOW = ".github/workflows/vol026-security-closure.yml"

REQUIRED_ASSETS = (
    "filesystem",
    "network-egress",
    "secrets",
    "supply-chain",
    "tool-authority",
)
EXPECTED_SCOPE_A = "tool-request-only"
EXPECTED_SCOPE_B = "single-tool-request"
EXPECTED_GAP = (
    "independent capability-security, threat-model, and tool-authorization "
    "verification remains pending"
)

FORBIDDEN_RUNTIME_TOKENS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "requests.",
    "httpx.",
    "os.system",
    "subprocess.",
)
REQUIRED_PATHS = (
    CAPABILITY,
    CAPABILITY_MIRROR,
    THREAT_MODEL,
    THREAT_MODEL_MIRROR,
    TOOL_AUTH,
    TOOL_AUTH_MIRROR,
    SECURITY_CONTRACTS,
    CAPABILITY_CONTRACTS,
    CAPABILITY_TEST,
    THREAT_TEST,
    TOOL_AUTH_TEST,
    ROOTED_FS_TEST,
    OUTBOUND_HTTP_TEST,
    SAST_SCRIPT,
    "machine/ai_master_plan.json",
)
WORKFLOW_REQUIRED_PATHS = (
    CAPABILITY,
    CAPABILITY_MIRROR,
    THREAT_MODEL,
    THREAT_MODEL_MIRROR,
    TOOL_AUTH,
    TOOL_AUTH_MIRROR,
    CAPABILITY_TEST,
    THREAT_TEST,
    TOOL_AUTH_TEST,
    ROOTED_FS_TEST,
    OUTBOUND_HTTP_TEST,
    SAST_SCRIPT,
    "scripts/verify_vol026_security_closure.py",
    "tests/test_vol026_security_independent_verifier.py",
)

_FIXTURE = r"""
import hashlib
import json

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.security.capability_contracts import (
    CapabilityGrant as ContractGrant,
    SecretRef as ContractSecretRef,
    SecurityContractError as ContractError,
)
from skeleton.security.capability_security import (
    CapabilityGrant,
    SecurityContext,
    ToolRequest,
    authorize_tool_request,
)
from skeleton.security.contracts import (
    SecretRef,
    SecurityContractError,
    SecurityIdentity,
)
from skeleton.security.threat_model import canonical_vol026_threat_model
from skeleton.security.tool_authorization import (
    SecurityContext as RuntimeSecurityContext,
    ToolRequest as RuntimeToolRequest,
    authorize_tool_request as authorize_runtime_tool_request,
)


def denied(call):
    try:
        call()
    except (SecurityContractError, ContractError):
        return True
    return False


grant = CapabilityGrant("worker-1", "repo.read", "repo:a", "read")
context = SecurityContext(
    SecurityIdentity("worker-1", "ctx-1"),
    (grant,),
)
request = ToolRequest(
    "git",
    "repo.read",
    "repo:a",
    "read",
    "0" * 64,
)
receipt = authorize_tool_request(context, request)
cap_expected = hashlib.sha256(
    canonical_json_bytes(
        {
            "principal_id": "worker-1",
            "capability": "repo.read",
            "resource": "repo:a",
            "operation": "read",
        }
    )
).hexdigest()

capability_mismatch_denied = all(
    denied(
        lambda cap=cap, res=res, op=op: authorize_tool_request(
            context,
            ToolRequest("git", cap, res, op, "0" * 64),
        )
    )
    for cap, res, op in (
        ("repo.write", "repo:a", "read"),
        ("repo.read", "repo:b", "read"),
        ("repo.read", "repo:a", "write"),
    )
)
capability_duplicate_denied = denied(
    lambda: authorize_tool_request(
        SecurityContext(
            SecurityIdentity("worker-1", "ctx-1"),
            (grant, grant),
        ),
        request,
    )
)
capability_foreign_denied = denied(
    lambda: SecurityContext(
        SecurityIdentity("worker-1", "ctx-1"),
        (CapabilityGrant("worker-2", "repo.read", "repo:a", "read"),),
    )
)

runtime_grant = ContractGrant(
    principal_id="worker-1",
    capability="repo.read",
    resource="repo:a",
    operation="read",
)
runtime_context = RuntimeSecurityContext(
    principal_id="worker-1",
    context_id="ctx-1",
    grants=(runtime_grant,),
)
runtime_request = RuntimeToolRequest(
    tool_id="git",
    capability="repo.read",
    resource="repo:a",
    operation="read",
    request_digest="0" * 64,
)
runtime_receipt = authorize_runtime_tool_request(
    runtime_context,
    runtime_request,
)
runtime_expected = hashlib.sha256(
    canonical_json_bytes(
        {
            "principal_id": runtime_grant.principal_id,
            "capability": runtime_grant.capability,
            "resource": runtime_grant.resource,
            "operation": runtime_grant.operation,
        }
    )
).hexdigest()

runtime_mismatch_denied = all(
    denied(
        lambda cap=cap, res=res, op=op: authorize_runtime_tool_request(
            runtime_context,
            RuntimeToolRequest(
                "git",
                cap,
                res,
                op,
                "0" * 64,
            ),
        )
    )
    for cap, res, op in (
        ("repo.write", "repo:a", "read"),
        ("repo.read", "repo:b", "read"),
        ("repo.read", "repo:a", "write"),
    )
)
runtime_duplicate_denied = denied(
    lambda: authorize_runtime_tool_request(
        RuntimeSecurityContext(
            principal_id="worker-1",
            context_id="ctx-1",
            grants=(runtime_grant, runtime_grant),
        ),
        runtime_request,
    )
)
runtime_foreign_denied = denied(
    lambda: RuntimeSecurityContext(
        principal_id="worker-1",
        context_id="ctx-1",
        grants=(
            ContractGrant(
                "worker-2",
                "repo.read",
                "repo:a",
                "read",
            ),
        ),
    )
)

model = canonical_vol026_threat_model()
threat_payload = {
    "version": model.model_version,
    "threats": [
        {
            "id": item.threat_id,
            "asset": item.asset,
            "boundary": item.boundary,
            "mitigation": item.mitigation,
            "validation": item.validation,
        }
        for item in model.threats
    ],
}
threat_expected = hashlib.sha256(
    canonical_json_bytes(threat_payload)
).hexdigest()

print(
    json.dumps(
        {
            "capability": {
                "scope": receipt.authority_scope,
                "grant_digest": receipt.grant_digest,
                "expected_grant_digest": cap_expected,
                "mismatch_denied": capability_mismatch_denied,
                "duplicate_denied": capability_duplicate_denied,
                "foreign_denied": capability_foreign_denied,
            },
            "tool_authorization": {
                "scope": runtime_receipt.scope,
                "grant_digest": runtime_receipt.grant_digest,
                "expected_grant_digest": runtime_expected,
                "mismatch_denied": runtime_mismatch_denied,
                "duplicate_denied": runtime_duplicate_denied,
                "foreign_denied": runtime_foreign_denied,
            },
            "secrets": {
                "security_secret_has_value": hasattr(
                    SecretRef("vault", "prod/api"),
                    "value",
                ),
                "capability_secret_has_value": hasattr(
                    ContractSecretRef("vault", "prod/api"),
                    "value",
                ),
            },
            "threat_model": {
                "digest": model.digest,
                "expected_digest": threat_expected,
                "assets": sorted(item.asset for item in model.threats),
                "ids": [item.threat_id for item in model.threats],
                "validation_paths": [
                    item.validation for item in model.threats
                ],
                "model_version": model.model_version,
            },
        },
        sort_keys=True,
    )
)
"""


class SecurityVerificationError(RuntimeError):
    """The independent verifier could not safely inspect repository state."""


def _read(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SecurityVerificationError(f"cannot read {relative}") from exc


def _load_json(root: Path, relative: str) -> dict[str, Any]:
    try:
        payload = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityVerificationError(f"cannot parse {relative}") from exc
    if not isinstance(payload, dict):
        raise SecurityVerificationError(f"{relative} must contain an object")
    return payload


def _find_volume(value: object, key: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("key") == key:
            return value
        for child in value.values():
            match = _find_volume(child, key)
            if match is not None:
                return match
    elif isinstance(value, list):
        for child in value:
            match = _find_volume(child, key)
            if match is not None:
                return match
    return None


def _run_fixture(root: Path) -> dict[str, Any]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (
        os.pathsep + existing if existing else ""
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _FIXTURE],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SecurityVerificationError(
            "cannot execute VOL-026 security fixture"
        ) from exc
    if proc.returncode != 0:
        raise SecurityVerificationError(
            "VOL-026 security fixture failed: "
            + proc.stderr.strip()[:1600]
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SecurityVerificationError(
            "VOL-026 security fixture emitted invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise SecurityVerificationError(
            "VOL-026 security fixture receipt must be an object"
        )
    return payload


def _validate_behavior(
    root: Path,
    behavior: Mapping[str, Any],
    errors: list[str],
) -> None:
    capability = behavior.get("capability")
    if not isinstance(capability, Mapping):
        errors.append("capability receipt missing")
    else:
        if capability.get("scope") != EXPECTED_SCOPE_A:
            errors.append("capability authorization scope widened")
        if capability.get("grant_digest") != capability.get(
            "expected_grant_digest"
        ):
            errors.append("capability grant identity is not shared-canonical")
        for field in ("mismatch_denied", "duplicate_denied", "foreign_denied"):
            if capability.get(field) is not True:
                errors.append(f"capability authorization failed closed: {field}")

    runtime = behavior.get("tool_authorization")
    if not isinstance(runtime, Mapping):
        errors.append("tool-authorization receipt missing")
    else:
        if runtime.get("scope") != EXPECTED_SCOPE_B:
            errors.append("tool authorization scope widened")
        if runtime.get("grant_digest") != runtime.get(
            "expected_grant_digest"
        ):
            errors.append("tool-authorization grant identity is not shared-canonical")
        for field in ("mismatch_denied", "duplicate_denied", "foreign_denied"):
            if runtime.get(field) is not True:
                errors.append(f"tool authorization failed closed: {field}")

    secrets = behavior.get("secrets")
    if not isinstance(secrets, Mapping):
        errors.append("secret-reference receipt missing")
    else:
        if secrets.get("security_secret_has_value") is not False:
            errors.append("security SecretRef exposes a value field")
        if secrets.get("capability_secret_has_value") is not False:
            errors.append("capability SecretRef exposes a value field")

    threat = behavior.get("threat_model")
    if not isinstance(threat, Mapping):
        errors.append("threat-model receipt missing")
        return
    assets = threat.get("assets")
    if assets != list(REQUIRED_ASSETS):
        errors.append(
            f"threat-model coverage mismatch: expected {REQUIRED_ASSETS!r}, "
            f"got {assets!r}"
        )
    ids = threat.get("ids")
    if (
        not isinstance(ids, list)
        or len(ids) != len(set(ids))
        or any(not isinstance(item, str) or not item for item in ids)
    ):
        errors.append("threat identities are not unique canonical strings")
    if threat.get("digest") != threat.get("expected_digest"):
        errors.append("threat-model identity is not shared-canonical")
    if threat.get("model_version") != "vol026-v1":
        errors.append("unexpected VOL-026 threat-model version")

    validations = threat.get("validation_paths")
    if (
        not isinstance(validations, list)
        or not validations
        or any(not isinstance(item, str) or not item for item in validations)
    ):
        errors.append("threat-model validation paths are malformed")
    else:
        for relative in validations:
            if relative.startswith("/") or ".." in Path(relative).parts:
                errors.append(
                    f"threat-model validation path is unsafe: {relative}"
                )
            elif not (root / relative).is_file():
                errors.append(
                    f"threat-model validation target is missing: {relative}"
                )


def verify_repository(
    root: Path = ROOT,
    *,
    behavior: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            errors.append(f"VOL-026 required file missing: {relative}")

    canonical_modules = (CAPABILITY, THREAT_MODEL, TOOL_AUTH)
    module_texts: dict[str, str] = {}
    for relative in canonical_modules:
        if (root / relative).is_file():
            module_texts[relative] = _read(root, relative)

    required_tokens = {
        CAPABILITY: (
            "class CapabilityGrant",
            "class SecurityContext",
            "class ToolRequest",
            "class AuthorizationReceipt",
            "authorize_tool_request",
            "canonical_json_bytes",
            'authority_scope:str="tool-request-only"',
        ),
        THREAT_MODEL: (
            "class Threat",
            "class ThreatModel",
            "canonical_vol026_threat_model",
            "canonical_json_bytes",
            "tool-authority",
            "network-egress",
            "supply-chain",
        ),
        TOOL_AUTH: (
            "class SecurityContext",
            "class ToolRequest",
            "class AuthorizationReceipt",
            "authorize_tool_request",
            "canonical_json_bytes",
            'scope:str="single-tool-request"',
        ),
    }
    for relative, tokens in required_tokens.items():
        text = module_texts.get(relative, "")
        for token in tokens:
            if token not in text:
                errors.append(f"{relative} lost required token: {token}")
        if "json.dumps" in text:
            errors.append(
                f"{relative} regressed to a private JSON identity serializer"
            )
        for token in FORBIDDEN_RUNTIME_TOKENS:
            if token in text:
                errors.append(
                    f"{relative} owns forbidden provider/execution token: {token}"
                )

    mirror_pairs = (
        (CAPABILITY, CAPABILITY_MIRROR),
        (THREAT_MODEL, THREAT_MODEL_MIRROR),
        (TOOL_AUTH, TOOL_AUTH_MIRROR),
    )
    mirror_digests: dict[str, dict[str, str]] = {}
    for canonical, mirror in mirror_pairs:
        if not (root / canonical).is_file() or not (root / mirror).is_file():
            continue
        left = (root / canonical).read_bytes()
        right = (root / mirror).read_bytes()
        left_digest = hashlib.sha256(left).hexdigest()
        right_digest = hashlib.sha256(right).hexdigest()
        mirror_digests[canonical] = {
            "canonical": left_digest,
            "mirror": right_digest,
        }
        if left != right:
            errors.append(f"canonical AI mirror drift: {canonical} != {mirror}")

    if (root / WORKFLOW).is_file():
        workflow = _read(root, WORKFLOW)
        for required in WORKFLOW_REQUIRED_PATHS:
            if required not in workflow:
                errors.append(
                    f"{WORKFLOW} lost VOL-026 verification coverage: {required}"
                )

    try:
        plan = _load_json(root, "machine/ai_master_plan.json")
        volume = _find_volume(plan, "VOL-026")
    except SecurityVerificationError as exc:
        errors.append(str(exc))
        volume = None
    if volume is None:
        errors.append("VOL-026 is missing from canonical masterplan")
    else:
        joined = " ".join(
            str(item) for item in volume.get("requirements", ())
        ).lower()
        for phrase in (
            "least privilege",
            "last responsible moment",
            "secrets referenced",
        ):
            if phrase not in joined:
                errors.append(
                    f"VOL-026 requirement drift: missing phrase {phrase!r}"
                )
        capabilities = set(
            str(item) for item in volume.get("capabilities", ())
        )
        for capability in (
            "identity/access security",
            "sandbox/egress controls",
            "supply-chain security",
        ):
            if capability not in capabilities:
                errors.append(f"VOL-026 capability drift: {capability}")
        gaps = tuple(str(item) for item in volume.get("gaps", ()))
        if gaps not in ((), (EXPECTED_GAP,)):
            errors.append(
                "VOL-026 contains unexpected implementation gaps: "
                + ", ".join(gaps)
            )

    if behavior is None:
        try:
            observed = _run_fixture(root)
        except SecurityVerificationError as exc:
            errors.append(str(exc))
            observed = {}
    else:
        observed = dict(behavior)
    _validate_behavior(root, observed, errors)

    boundary_digests: dict[str, str] = {}
    for relative in REQUIRED_PATHS + (WORKFLOW, _self_relative()):
        path = root / relative
        if path.is_file():
            boundary_digests[relative] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()

    return {
        "schema_version": 1,
        "verifier": "independent-vol026-security-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "mirror_digests": mirror_digests,
        "behavior": observed,
        "boundary_digests": boundary_digests,
        "errors": errors,
        "valid": not errors,
    }


def _self_relative() -> str:
    try:
        return Path(__file__).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "scripts/verify_vol026_security_closure.py"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except SecurityVerificationError as exc:
        print(f"independent-vol026-security: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("independent-vol026-security: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "independent-vol026-security: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_digests'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
