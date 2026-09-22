"""JSON/YAML materialise verification — CodeVerifier + optional bounded repair.

Sibling to ``verify_loop.py``: revise-until-green for structured text without
forking Godot ``ForgeVerifier`` project checks onto json/yaml artefacts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from skeleton.forge.materialisers import HAS_YAML, MaterialisationRegistry
from skeleton.intelligence.verification import VerificationLoop, VerificationVerdict
from skeleton.intelligence.verifier import CodeVerifier
from skeleton.organism.policy_enforcement import repair_enabled_for, threshold_for

if HAS_YAML:
    import yaml as _yaml


def _ext(target: str) -> str:
    return "yaml" if target == "yaml" else "json"


def encode_structured_files(
    artefact: Mapping[str, Any],
    *,
    target: str,
    name: str,
) -> dict[str, str]:
    """Encode blueprint/pack/plan artefact via MaterialisationRegistry → files dict."""
    if target not in {"json", "yaml"}:
        raise ValueError(f"structured verify target must be json or yaml, got {target!r}")
    registry = MaterialisationRegistry()
    materialiser = registry.get(target)
    payload = {k: artefact[k] for k in artefact}
    text = materialiser.encode(dict(payload)).decode("utf-8")
    path = f"{name}.{_ext(target)}"
    return {path: text}


def _parse_ok(text: str, target: str) -> tuple[bool, str]:
    try:
        if target == "json":
            json.loads(text)
        else:
            if not HAS_YAML:
                return False, "yaml-unavailable"
            _yaml.safe_load(text)
        return True, ""
    except Exception as exc:  # noqa: BLE001 — surface parse reason
        return False, f"parse_error: {exc}"


def _verification_dict(
    *,
    accepted: bool,
    score: float,
    reason: str,
    path: str,
    issues: tuple[str, ...] | list[str],
    code_report: dict[str, Any] | None,
    threshold: float,
    target: str,
) -> dict[str, Any]:
    issue_list = list(issues)
    return {
        "accepted": accepted,
        "score": round(float(score), 4),
        "reason": reason,
        "weakest_path": path if not accepted else "",
        "summary": {
            "files_checked": 1,
            "issue_count": len(issue_list),
        },
        "project_issues": [i for i in issue_list if i.startswith("parse_error") or i == "yaml-unavailable"],
        "blocking_issues": list(issue_list) if not accepted else [],
        "file_reports": [
            {
                "path": path,
                "score": round(float(score), 4),
                "issues": issue_list,
            }
        ],
        "code_verdict": code_report,
        "threshold": threshold,
        "quality": {
            "accepted": accepted,
            "reason": reason,
            "score": round(float(score), 4),
            "weakest_path": path if not accepted else "",
            "metadata": {"kind": "forge", "target": target},
        },
    }


def verify_structured(
    files: Mapping[str, str],
    *,
    target: str,
    request: str = "",
    root=None,
    accept_threshold: float | None = None,
) -> dict[str, Any]:
    """Parse-check + policy-aware ``CodeVerifier.verdict`` on encoded text."""
    threshold = (
        accept_threshold
        if accept_threshold is not None
        else threshold_for("forge", root=root, fallback=0.7)
    )
    if not files:
        return _verification_dict(
            accepted=False,
            score=0.0,
            reason="empty_files",
            path="",
            issues=("no structured artefact files",),
            code_report=None,
            threshold=threshold,
            target=target,
        )
    path = sorted(files)[0]
    text = files[path]
    parsed, parse_err = _parse_ok(text, target)
    code = CodeVerifier(accept_at=threshold, root=root, surface="forge")
    verdict = code.verdict(text, request=request or path)
    code_report = {
        "path": path,
        "confidence": round(verdict.confidence, 4),
        "issues": list(verdict.issues),
    }
    issues: list[str] = []
    if not parsed:
        issues.append(parse_err or "parse_error")
    issues.extend(list(verdict.issues))
    # Parse gate is hard; CodeVerifier confidence is the soft score.
    score = 0.0 if not parsed else float(verdict.confidence)
    accepted = bool(parsed and score >= threshold)
    reason = "accepted" if accepted else ("parse_error" if not parsed else "low_score")
    payload = _verification_dict(
        accepted=accepted,
        score=score,
        reason=reason,
        path=path,
        issues=tuple(issues),
        code_report=code_report,
        threshold=threshold,
        target=target,
    )
    payload["verification_stats"] = code.stats()
    return payload


def structured_verify_until_green(
    canonical: Mapping[str, Any],
    *,
    target: str,
    name: str,
    request: str = "",
    root=None,
    max_rounds: int = 3,
    min_gain: float = 0.05,
    accept_threshold: float | None = None,
) -> dict[str, Any]:
    """Bounded revise-until-green for json/yaml — re-encode from canonical on repair.

    Does **not** call Godot ``attempt_repair``. Repair is gated by
    ``policy_enforcement.repair_enabled_for("forge")``.
    """
    threshold = (
        accept_threshold
        if accept_threshold is not None
        else threshold_for("forge", root=root, fallback=0.7)
    )
    files = encode_structured_files(canonical, target=target, name=name)
    path = next(iter(files))
    loop = VerificationLoop(
        max_rounds=max(1, int(max_rounds)),
        min_gain=min_gain,
        accept_threshold=threshold,
        min_rounds=1,
    )
    state: dict[str, Any] = {
        "files": dict(files),
        "last_verification": None,
        "repairs": [],
        "rounds_detail": [],
    }

    def verifier_fn(claim: str, context: dict[str, Any] | None) -> VerificationVerdict:
        del context
        current_files = {path: claim}
        report = verify_structured(
            current_files,
            target=target,
            request=request,
            root=root,
            accept_threshold=threshold,
        )
        state["files"] = current_files
        state["last_verification"] = report
        confidence = float(report["score"])
        if report["accepted"]:
            state["rounds_detail"].append(
                {
                    "accepted": True,
                    "confidence": round(confidence, 4),
                    "verification": report,
                }
            )
            return VerificationVerdict(
                confidence=confidence,
                issues=tuple(report.get("blocking_issues") or []),
            )

        revised = None
        if repair_enabled_for("forge", root=root):
            rebuilt = encode_structured_files(canonical, target=target, name=name)
            new_text = rebuilt[path]
            changed = new_text != claim
            state["repairs"].append(
                {
                    "ok": 1 if changed or report["reason"] == "parse_error" else 0,
                    "changed": int(changed),
                    "reason": "re-encode" if changed else "re-encode-noop",
                    "targeted_path": path,
                }
            )
            if changed or report["reason"] == "parse_error":
                # Always offer canonical re-encode when parse failed (even if identical
                # after a prior fix) so the loop can re-check a known-good payload.
                revised = new_text
                state["files"] = rebuilt
        state["rounds_detail"].append(
            {
                "accepted": False,
                "confidence": round(confidence, 4),
                "verification": report,
                "revised": bool(revised),
            }
        )
        return VerificationVerdict(
            confidence=confidence,
            issues=tuple(report.get("blocking_issues") or []),
            revised=revised,
        )

    final_claim, trace = loop.run(files[path], verifier_fn)
    final_files = {path: final_claim}
    final_report = verify_structured(
        final_files,
        target=target,
        request=request,
        root=root,
        accept_threshold=threshold,
    )
    accepted = bool(final_report["accepted"])
    return {
        "kind": "structured-verify-loop",
        "ok": int(accepted),
        "accepted": accepted,
        "files": final_files,
        "verification": final_report,
        "verification_stats": final_report.get("verification_stats") or {},
        "code_verdict": final_report.get("code_verdict"),
        "trace": trace.to_dict(),
        "repairs": list(state["repairs"]),
        "rounds_detail": list(state["rounds_detail"]),
        "threshold": threshold,
        "stopped_reason": trace.stopped_reason,
        "stored_prose": 0,
    }
