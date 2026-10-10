#!/usr/bin/env python3
"""Fail-closed structural validator for AI-chat evidence/citation Volume 8."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_evidence_citations.json"
SCHEMA = "ai-chat-evidence-citations/v1"
FORBIDDEN_EXECUTION_IMPORTS = {
    "openai",
    "anthropic",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "boto3",
}
REQUIRED_INVARIANTS = {
    "citation proximity never establishes evidence authority",
    "citation binding must match source identity locator and content digest",
    "model-produced or generated-source evidence is never authoritative",
    "current-evidence requirements reject stale or future observations",
    "correlated copies cannot satisfy independent-origin requirements",
    "authoritative contradiction yields a contested publication disposition",
    "publication eligibility receipts are deterministic and non-executing",
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
        if isinstance(node, kind) and isinstance(getattr(node, "name", None), str)
    }


def _imports(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _facade_only(path: Path, canonical_fragment: str) -> bool:
    source = path.read_text(encoding="utf-8")
    if canonical_fragment not in source:
        return False
    tree = ast.parse(source, filename=str(path))
    forbidden = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    return not any(isinstance(node, forbidden) for node in ast.walk(tree))


def validate() -> list[str]:
    errors: list[str] = []
    if not CONTRACT.is_file():
        return ["missing machine/ai_chat_evidence_citations.json"]
    try:
        contract = _json(CONTRACT)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse evidence/citation contract: {exc}"]

    if contract.get("schema_version") != SCHEMA:
        errors.append("evidence/citation schema drifted")
    if contract.get("status") != "implemented_candidate":
        errors.append("evidence/citation status must remain implemented_candidate")

    authority = contract.get("authority")
    if not isinstance(authority, dict):
        errors.append("evidence/citation authority contract missing")
    else:
        if authority.get("execution") is not False:
            errors.append("evidence plane cannot gain execution authority")
        if authority.get("publication") is not False:
            errors.append("evidence plane cannot directly publish")

    promotion = contract.get("promotion")
    if not isinstance(promotion, dict):
        errors.append("evidence/citation promotion contract missing")
    else:
        if promotion.get("completion_checkbox") is not False:
            errors.append("evidence/citation contract cannot self-attest completion")
        if promotion.get("verification_signature") is not None:
            errors.append("evidence/citation contract cannot fabricate signature")

    invariants = contract.get("invariants")
    if not isinstance(invariants, list):
        errors.append("evidence/citation invariants must be a list")
    elif not REQUIRED_INVARIANTS <= set(map(str, invariants)):
        errors.append("required evidence/citation invariants are incomplete")

    files = contract.get("files")
    expected_roles = {
        "claim_identity",
        "citation_integrity",
        "verification_package",
        "claim_identity_facade",
        "citation_integrity_facade",
        "chat_gate",
        "assistant_exports",
        "tests",
        "backend_citation_tests",
        "backend_laundering_tests",
        "backend_gate_tests",
        "facade_parity_tests",
        "response_acceptance",
        "response_acceptance_tests",
        "validator",
        "independent_verifier",
        "workflow",
        "plan",
    }
    if not isinstance(files, dict):
        return errors + ["evidence/citation files must be an object"]
    if set(files) != expected_roles:
        errors.append("evidence/citation file roles drifted")

    resolved: dict[str, Path] = {}
    for role, raw in files.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"invalid file path for role {role}")
            continue
        path = ROOT / raw
        resolved[str(role)] = path
        if not path.is_file():
            errors.append(f"missing evidence/citation file: {role}: {raw}")

    claim_facade = resolved.get("claim_identity_facade")
    if claim_facade and claim_facade.is_file():
        if not _facade_only(
            claim_facade,
            "skeleton.verification.claim_identity",
        ):
            errors.append("backend claim identity is no longer a thin canonical facade")

    citation_facade = resolved.get("citation_integrity_facade")
    if citation_facade and citation_facade.is_file():
        if not _facade_only(
            citation_facade,
            "skeleton.verification.citation_integrity",
        ):
            errors.append("backend citation integrity is no longer a thin canonical facade")

    gate = resolved.get("chat_gate")
    if gate and gate.is_file():
        try:
            source = gate.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(gate))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"chat evidence gate is invalid Python: {exc}")
        else:
            required_classes = {
                "SourceQualityProfile",
                "ClaimPublicationPolicy",
                "ClaimEvidenceBundle",
                "EvidenceAssessment",
                "ClaimEvidenceReceipt",
                "EvidenceCitationPlane",
            }
            required_functions = {"evaluate", "_assess"}
            classes = _defined(tree, ast.ClassDef)
            functions = _defined(tree, ast.FunctionDef)
            if not required_classes <= classes:
                errors.append("chat evidence gate classes are incomplete")
            if not required_functions <= functions:
                errors.append("chat evidence gate evaluation boundary missing")
            forbidden = _imports(tree) & FORBIDDEN_EXECUTION_IMPORTS
            if forbidden:
                errors.append(
                    "chat evidence gate crossed execution/network boundary: "
                    + ", ".join(sorted(forbidden))
                )
            for token in (
                "citation_content_digest_mismatch",
                "citation_claim_identity_mismatch",
                "evidence_stale_for_current_claim",
                "evidence_observed_in_future",
                "evidence_non_authoritative",
                "independent_origin_requirement_not_met",
                "authoritative_contradiction_present",
                "high_risk_claim_requires_primary_source",
                'authority_scope: str = "evidence-publication-eligibility-only"',
                "production_authority: bool = False",
            ):
                if token not in source:
                    errors.append(f"chat evidence gate lost invariant marker: {token}")

    claim_impl = resolved.get("claim_identity")
    citation_impl = resolved.get("citation_integrity")
    if claim_impl and claim_impl.is_file():
        text = claim_impl.read_text(encoding="utf-8")
        for token in (
            "polarity",
            "relation",
            "quantities",
            "units",
            "identity_sha256",
        ):
            if token not in text:
                errors.append(f"canonical claim identity lost marker: {token}")
    if citation_impl and citation_impl.is_file():
        text = citation_impl.read_text(encoding="utf-8")
        for token in (
            "claim_quantity_not_present_in_evidence_span",
            "claim_unit_not_present_in_evidence_span",
            "evidence_polarity_conflict",
            "evidence_relation_conflict",
            "insufficient_claim_anchor_overlap",
        ):
            if token not in text:
                errors.append(f"canonical citation integrity lost marker: {token}")

    response_acceptance = resolved.get("response_acceptance")
    if response_acceptance and response_acceptance.is_file():
        text = response_acceptance.read_text(encoding="utf-8")
        for token in (
            "missing_receipt_claim_ids",
            "claim_receipt_digest_mismatch",
            "claim_receipt_from_future",
            "claim_receipt_stale",
            "required_claim_contested",
            "required_claim_abstained",
            'authority_scope: str = "response-acceptance-decision-only"',
            "production_authority: bool = False",
        ):
            if token not in text:
                errors.append(
                    f"response acceptance lost invariant marker: {token}"
                )

    tests = resolved.get("tests")
    if tests and tests.is_file():
        try:
            tree = ast.parse(tests.read_text(encoding="utf-8"), filename=str(tests))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"evidence/citation tests are invalid Python: {exc}")
        else:
            test_count = sum(
                1
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and str(node.name).startswith("test_")
            )
            if test_count < 35:
                errors.append(f"evidence/citation adversarial suite too small: {test_count} < 35")

    plan = resolved.get("plan")
    if plan and plan.is_file():
        text = plan.read_text(encoding="utf-8")
        if "### Volume 8 — evidence and citation plane" not in text:
            errors.append("masterplan Volume 8 section missing")
        if (
            "Status: **implemented candidate; product-response cutover and exact-head qualification pending**."
            not in text
        ):
            errors.append("masterplan Volume 8 status is not synchronized")

    workflow = resolved.get("workflow")
    if workflow and workflow.is_file():
        text = workflow.read_text(encoding="utf-8")
        for token in (
            "persist-credentials: false",
            "github.event.pull_request.head.sha || github.sha",
            "check_ai_chat_evidence_citations.py",
            "verify_ai_chat_evidence_citations.py",
            "test_ai_chat_evidence_citations.py",
            "test_citation_structural_laundering.py",
            "test_claim_identity_citation_calibration.py",
            "test_verification_facade_parity.py",
            "test_ai_chat_response_acceptance.py",
            "check_ai_file_tree.py",
        ):
            if token not in text:
                errors.append(f"evidence/citation workflow missing control: {token}")

    return errors


def evidence(head_sha: str) -> dict[str, object]:
    errors = validate()
    contract = _json(CONTRACT)
    files = contract.get("files") or {}
    digests = {
        str(role): _sha(ROOT / str(path))
        for role, path in sorted(files.items())
        if isinstance(path, str) and (ROOT / path).is_file()
    }
    payload: dict[str, object] = {
        "schema_version": SCHEMA,
        "verifier": "ai-chat-evidence-citations-structural-v1",
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
                json.dumps(result, indent=2, sort_keys=True) + "\n",
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
    print("AI chat evidence/citation contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
