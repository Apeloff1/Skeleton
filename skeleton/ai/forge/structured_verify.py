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


def _threshold(accept_threshold: float | None, root) -> float:
    value = accept_threshold if accept_threshold is not None else threshold_for("forge", root=root, fallback=0.7)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1:
        raise ValueError("accept_threshold must be in (0, 1]")
    return float(value)


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
            parsed = json.loads(text)
            if not isinstance(parsed, (dict, list)):
                return False, "json root must be an object or array"
        else:
            if not HAS_YAML:
                return False, "yaml-unavailable"
            parsed = _yaml.safe_load(text)
            if not isinstance(parsed, (dict, list)):
                return False, "yaml root must be an object or array"
        return True, ""
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return False, f"parse_error: {type(exc).__name__}"
    except Exception as exc:
        if HAS_YAML and isinstance(exc, _yaml.YAMLError):
            return False, "parse_error: YAMLError"
        return False, f"parse_error: {type(exc).__name__}"


def _semantic_issues(text: str, target: str) -> tuple[str, ...]:
    """Validate the canonical structured Forge artefact contract.

    JSON/YAML output is data, not executable source code.  Parseability and the
    Forge envelope are hard gates; generic CodeVerifier heuristics remain
    advisory evidence because code-likeness is not a meaningful acceptance
    criterion for a serialized blueprint.
    """

    try:
        payload = json.loads(text) if target == "json" else _yaml.safe_load(text)
    except Exception:
        return ()

    if not isinstance(payload, dict):
        return ("forge structured artefact root must be an object",)

    required = {
        "blueprint_id": str,
        "name": str,
        "era": str,
        "topology": dict,
        "execution_order": list,
        "plan": dict,
    }
    issues: list[str] = []
    for key, expected_type in required.items():
        value = payload.get(key)
        if not isinstance(value, expected_type):
            issues.append(f"forge structured artefact {key} has invalid type")
            continue
        if isinstance(value, str) and not value.strip():
            issues.append(f"forge structured artefact {key} is empty")

    order = payload.get("execution_order")
    if isinstance(order, list) and (
        not order
        or any(not isinstance(item, str) or not item.strip() for item in order)
        or len(order) != len(set(order))
    ):
        issues.append("forge structured artefact execution_order is invalid")

    topology = payload.get("topology")
    if isinstance(topology, dict):
        components = topology.get("components")
        if not isinstance(components, (dict, list)) or not components:
            issues.append("forge structured artefact topology has no components")

    return tuple(issues)


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
    threshold = _threshold(accept_threshold, root)
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
    semantic_issues = () if not parsed else _semantic_issues(text, target)
    issues.extend(semantic_issues)

    # Structured Forge output is data, not source code. Parseability plus the
    # canonical Forge envelope are the hard acceptance boundary. CodeVerifier
    # remains attached above as advisory evidence, but its code-likeness score
    # cannot reject valid JSON/YAML serialization.
    accepted = bool(parsed and not semantic_issues)
    score = 1.0 if accepted else 0.0
    reason = (
        "accepted"
        if accepted
        else ("parse_error" if not parsed else "semantic_invalid")
    )
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
    threshold = _threshold(accept_threshold, root)
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
        raise ValueError("max_rounds must be an integer >= 1")
    files = encode_structured_files(canonical, target=target, name=name)
    path = next(iter(files))
    loop = VerificationLoop(
        max_rounds=max_rounds,
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
