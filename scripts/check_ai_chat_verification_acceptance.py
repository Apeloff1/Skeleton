#!/usr/bin/env python3
"""Fail-closed structural validator for AI-chat Volume 9 verification acceptance."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_verification_acceptance.json"
SCHEMA = "ai-chat-verification-acceptance/v1"
FORBIDDEN_ACCEPTANCE_IMPORTS = {
    "openai",
    "anthropic",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "boto3",
}
REQUIRED_INVARIANTS = {
    "canonical risk action and external-effect verification policy is an acceptance floor and cannot be weakened by a caller profile",
    "verification checks have deterministic canonical digests",
    "future verification receipts fail closed and can quarantine",
    "independent verification requires identity-bound proof rather than an independent boolean alone",
    "independence proof binds the exact verification receipt and canonical independent check digest",
    "semantic repairs preserve lineage and cannot publish before citation rebinding",
    "acceptance and quarantine decisions are deterministic and non-executing",
}


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _defined(tree: ast.Module, kind: type[ast.AST]) -> set[str]:
    return {
        str(node.name)
        for node in ast.walk(tree)
        if isinstance(node, kind)
        and isinstance(getattr(node, "name", None), str)
    }


def _imports(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(
                alias.name.split(".", 1)[0]
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def validate() -> list[str]:
    errors: list[str] = []
    if not CONTRACT.is_file():
        return ["missing machine/ai_chat_verification_acceptance.json"]
    try:
        contract = _json(CONTRACT)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        return [f"cannot parse verification acceptance contract: {exc}"]

    if contract.get("schema_version") != SCHEMA:
        errors.append("verification acceptance schema drifted")
    if contract.get("status") != "implemented_candidate":
        errors.append(
            "verification acceptance must remain implemented_candidate"
        )

    authority = contract.get("authority")
    if not isinstance(authority, dict):
        errors.append("verification acceptance authority contract missing")
    else:
        if authority.get("execution") is not False:
            errors.append(
                "verification acceptance cannot gain execution authority"
            )
        if authority.get("publication") is not False:
            errors.append(
                "verification acceptance cannot directly publish"
            )

    promotion = contract.get("promotion")
    if not isinstance(promotion, dict):
        errors.append("verification acceptance promotion contract missing")
    else:
        if promotion.get("completion_checkbox") is not False:
            errors.append(
                "verification acceptance cannot self-attest completion"
            )
        if promotion.get("verification_signature") is not None:
            errors.append(
                "verification acceptance cannot fabricate signature"
            )

    invariants = contract.get("invariants")
    if not isinstance(invariants, list):
        errors.append("verification acceptance invariants must be a list")
    elif not REQUIRED_INVARIANTS <= set(map(str, invariants)):
        errors.append(
            "verification acceptance required invariants are incomplete"
        )

    files = contract.get("files")
    expected_roles = {
        "acceptance",
        "intelligence_exports",
        "verification_contract",
        "verification_policy",
        "verification_runtime",
        "acceptance_tests",
        "contract_tests",
        "runtime_tests",
        "validator",
        "independent_verifier",
        "workflow",
        "plan",
    }
    if not isinstance(files, dict):
        return errors + ["verification acceptance files must be an object"]
    if set(files) != expected_roles:
        errors.append("verification acceptance file roles drifted")

    resolved: dict[str, Path] = {}
    for role, raw in files.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"invalid file path for role {role}")
            continue
        path = ROOT / raw
        resolved[str(role)] = path
        if not path.is_file():
            errors.append(
                f"missing verification acceptance file: {role}: {raw}"
            )

    acceptance = resolved.get("acceptance")
    if acceptance and acceptance.is_file():
        try:
            source = acceptance.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(acceptance))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(
                f"verification acceptance module is invalid Python: {exc}"
            )
        else:
            required_classes = {
                "VerificationActorIdentity",
                "IndependentVerificationProof",
                "VerificationAcceptanceProfile",
                "VerificationAcceptanceDecision",
                "VerificationAcceptanceGate",
            }
            required_functions = {
                "build_independent_verification_proof",
                "default_acceptance_profile",
                "evaluate",
            }
            classes = _defined(tree, ast.ClassDef)
            functions = _defined(tree, ast.FunctionDef)
            if not required_classes <= classes:
                errors.append(
                    "verification acceptance classes are incomplete"
                )
            if not required_functions <= functions:
                errors.append(
                    "verification acceptance functions are incomplete"
                )
            forbidden = (
                _imports(tree)
                & FORBIDDEN_ACCEPTANCE_IMPORTS
            )
            if forbidden:
                errors.append(
                    "verification acceptance crossed execution/network boundary: "
                    + ", ".join(sorted(forbidden))
                )
            for token in (
                "verification_receipt_binding_mismatch",
                "verification_receipt_from_future",
                "verification_receipt_stale",
                "passed_receipt_contains_contradiction",
                "independent_identity_proof_missing",
                "independent_identity_proof_binding_mismatch",
                "independent_actor_identity_collides",
                "independent_authority_domain_collides",
                "independent_process_collides",
                "critical_independent_provider_collides",
                "independent_check_postdates_receipt",
                "independent_check_stale",
                'authority_scope: str = "verification-acceptance-only"',
                "production_authority: bool = False",
            ):
                if token not in source:
                    errors.append(
                        "verification acceptance lost invariant marker: "
                        + token
                    )

    contract_path = resolved.get("verification_contract")
    if contract_path and contract_path.is_file():
        source = contract_path.read_text(encoding="utf-8")
        check_start = source.find("class VerificationCheck:")
        receipt_start = source.find("class VerificationReceipt:")
        if check_start < 0 or receipt_start <= check_start:
            errors.append("VerificationCheck contract boundary missing")
        else:
            section = source[check_start:receipt_start]
            for token in (
                "def as_dict(self)",
                "def digest(self)",
                '"check_id": self.check_id',
                '"independent": self.independent',
            ):
                if token not in section:
                    errors.append(
                        "VerificationCheck canonical digest surface missing: "
                        + token
                    )

    policy = resolved.get("verification_policy")
    if policy and policy.is_file():
        source = policy.read_text(encoding="utf-8")
        for token in (
            "model_origin_requires_external_evidence",
            "action_outcome_requires_postcondition",
            "external_action_requires_postcondition",
            '"irreversible": VerificationLevel.POSTCONDITION',
        ):
            if token not in source:
                errors.append(
                    "verification policy floor lost marker: " + token
                )

    runtime = resolved.get("verification_runtime")
    if runtime and runtime.is_file():
        source = runtime.read_text(encoding="utf-8")
        for token in (
            "class SemanticVerificationRuntime",
            "max_rounds",
            "max_repairs",
            "max_output_tokens",
            'purpose="semantic-verification"',
            'tool_choice="none"',
            '"additionalProperties": False',
            "semantic_verifier_unavailable_or_invalid",
            "repaired_claim_requires_citation_rebinding",
            "semantic_repair_budget_exhausted",
            "independent_verification_required",
        ):
            if token not in source:
                errors.append(
                    "semantic verification runtime lost marker: " + token
                )

    tests = resolved.get("acceptance_tests")
    if tests and tests.is_file():
        try:
            tree = ast.parse(
                tests.read_text(encoding="utf-8"),
                filename=str(tests),
            )
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(
                f"verification acceptance tests are invalid Python: {exc}"
            )
        else:
            test_count = sum(
                1
                for node in ast.walk(tree)
                if isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                )
                and str(node.name).startswith("test_")
            )
            if test_count < 25:
                errors.append(
                    "verification acceptance adversarial suite too small: "
                    f"{test_count} < 25"
                )

    plan = resolved.get("plan")
    if plan and plan.is_file():
        text = plan.read_text(encoding="utf-8")
        if "### Volume 9 — verification plane" not in text:
            errors.append("masterplan Volume 9 section missing")
        if (
            "Status: **implemented candidate; finalization cutover and exact-head qualification pending**."
            not in text
        ):
            errors.append(
                "masterplan Volume 9 status is not synchronized"
            )

    workflow = resolved.get("workflow")
    if workflow and workflow.is_file():
        text = workflow.read_text(encoding="utf-8")
        for token in (
            "persist-credentials: false",
            "github.event.pull_request.head.sha || github.sha",
            "check_ai_chat_verification_acceptance.py",
            "verify_ai_chat_verification_acceptance.py",
            "test_verification_acceptance.py",
            "test_verification_contract.py",
            "test_verification_runtime.py",
            "check_ai_file_tree.py",
        ):
            if token not in text:
                errors.append(
                    "verification acceptance workflow missing control: "
                    + token
                )

    return errors


def evidence(head_sha: str) -> dict[str, object]:
    errors = validate()
    contract = _json(CONTRACT)
    files = contract.get("files") or {}
    digests = {
        str(role): _sha(ROOT / str(path))
        for role, path in sorted(files.items())
        if isinstance(path, str)
        and (ROOT / path).is_file()
    }
    payload: dict[str, object] = {
        "schema_version": SCHEMA,
        "verifier":
            "ai-chat-verification-acceptance-structural-v1",
        "head_sha": head_sha.strip(),
        "valid": not errors,
        "errors": errors,
        "contract_digest": _sha(CONTRACT),
        "digests": digests,
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args()

    if args.head_sha:
        result = evidence(args.head_sha)
        if args.evidence_out:
            Path(args.evidence_out).write_text(
                json.dumps(
                    result,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        if args.print_evidence:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1

    errors = validate()
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("AI chat verification acceptance contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
