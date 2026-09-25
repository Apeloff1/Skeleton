"""Forge revise-until-green — Godot verification + bounded repair.

F-5 glue: materialise already had a single ForgeVerifier gate and an optional
one-shot ``attempt_repair``. This module composes the existing bounded
``VerificationLoop`` with that Godot-aware verifier so projects can revise
until accepted (or rounds/gain flatten), without letting a generic Python-style
code rubric veto valid GDScript. ``CodeVerifier`` remains advisory telemetry.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping
from typing import Any

from skeleton.forge.repair import attempt_repair
from skeleton.intelligence.forge_verifier import ForgeVerifier
from skeleton.intelligence.verification import VerificationLoop, VerificationVerdict
from skeleton.intelligence.verifier import CodeVerifier
from skeleton.organism.policy_enforcement import repair_enabled_for, threshold_for


def _encode_claim(files: Mapping[str, str]) -> str:
    return json.dumps(dict(sorted(files.items())), separators=(",", ":"), ensure_ascii=False)


def _decode_claim(claim: str) -> dict[str, str]:
    raw = json.loads(claim)
    if not isinstance(raw, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in raw.items()):
        raise TypeError("forge verify claim must be a JSON object of path→source")
    return dict(raw)


def _primary_script(files: Mapping[str, str], weakest_path: str = "") -> tuple[str, str]:
    if not isinstance(weakest_path, str) or not weakest_path.endswith(".gd"):
        return "", ""
    source = files.get(weakest_path)
    if not isinstance(source, str) or not source.strip():
        return "", ""
    return weakest_path, source


def forge_verify_until_green(
    files: Mapping[str, str],
    *,
    request: str = "",
    root=None,
    max_rounds: int = 3,
    min_gain: float = 0.05,
    accept_threshold: float | None = None,
) -> dict[str, Any]:
    """Run revise-until-green over emitted project files.

    Each round:
    1. ``ForgeVerifier.verify`` for project-level accept/reject.
    2. ``CodeVerifier.verdict`` on the weakest / primary script (F-5 adapter).
    3. If not accepted and repair is enabled, ``attempt_repair`` revises files.

    Returns a dict with final files, verification report, loop trace, and
    whether the loop accepted. Does not raise — callers decide hard-fail.
    """
    if not isinstance(files, Mapping) or not files:
        raise ValueError("files are required")
    if any(not isinstance(path, str) or not isinstance(source, str) for path, source in files.items()):
        raise ValueError("files must map paths to source")
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request is required")
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
        raise ValueError("max_rounds must be an integer >= 1")
    if isinstance(min_gain, bool) or not isinstance(min_gain, (int, float)) or min_gain < 0 or min_gain != min_gain:
        raise ValueError("min_gain must be a finite number >= 0")
    if accept_threshold is None:
        accept_threshold = threshold_for("forge", root=root, fallback=0.7)
    if isinstance(accept_threshold, bool) or not isinstance(accept_threshold, (int, float)) or not 0 < float(accept_threshold) <= 1:
        raise ValueError("accept_threshold must be in (0, 1]")
    threshold = float(accept_threshold)
    loop = VerificationLoop(
        max_rounds=max_rounds,
        min_gain=float(min_gain),
        accept_threshold=threshold,
        min_rounds=1,
    )
    code = CodeVerifier(accept_at=threshold)
    forge_verifier = ForgeVerifier(accept_at=threshold, gd_accept_at=threshold, root=root)
    state: MutableMapping[str, Any] = {
        "files": dict(files),
        "last_forge": None,
        "last_code": None,
        "repairs": [],
        "rounds_detail": [],
    }

    def verifier_fn(claim: str, context: dict[str, Any] | None) -> VerificationVerdict:
        del context  # forge loop carries mutable state locally
        current = _decode_claim(claim)
        report = forge_verifier.verify(current, request=request)
        state["files"] = current
        state["last_forge"] = report
        path, src = _primary_script(current, report.weakest_path if isinstance(report.weakest_path, str) else "")
        if not path or not src.strip():
            code_confidence = 0.0
            code_issues: tuple[str, ...] = ("no script",)
        else:
            code_verdict = code.verdict(src, request=request or path)
            code_confidence = float(code_verdict.confidence)
            code_issues = tuple(code_verdict.issues)
        state["last_code"] = {
            "path": path,
            "confidence": round(code_confidence, 4),
            "issues": list(code_issues),
        }
        # ForgeVerifier is the authoritative Godot/GDScript gate. The generic
        # CodeVerifier is intentionally advisory here: it looks for Python-like
        # "def"/"class" structure and therefore reports false negatives for
        # valid GDScript using "func"/"class_name".
        confidence = float(report.score)
        if report.accepted is True:
            state["rounds_detail"].append(
                {
                    "accepted": True,
                    "forge": report.to_dict(),
                    "code": dict(state["last_code"]),
                    "confidence": round(confidence, 4),
                }
            )
            return VerificationVerdict(confidence=confidence, issues=())

        revised_claim = None
        if repair_enabled_for("forge", root=root):
            evidence = {
                "project_issues": list(report.project_issues),
                "blocking_issues": list(report.blocking_issues),
                "top_file_reports": [r.to_dict() for r in report.file_reports[:3]],
            }
            repaired = attempt_repair(
                current, request=request, root=root, evidence=evidence
            )
            state["repairs"].append({k: v for k, v in repaired.items() if k != "files"})
            revised_files = repaired.get("files")
            if repaired.get("changed") == 1 and isinstance(revised_files, dict) and revised_files != current:
                state["files"] = dict(revised_files)
                revised_claim = _encode_claim(state["files"])

        issues = tuple(report.blocking_issues) or ("not accepted",)
        state["rounds_detail"].append(
            {
                "accepted": False,
                "forge": report.to_dict(),
                "code": dict(state["last_code"]),
                "confidence": round(confidence, 4),
                "revised": bool(revised_claim),
            }
        )
        return VerificationVerdict(
            confidence=confidence,
            issues=issues,
            revised=revised_claim,
        )

    final_claim, trace = loop.run(_encode_claim(files), verifier_fn)
    final_files = _decode_claim(final_claim)
    # Re-verify final tree so the returned report matches files on disk of the loop.
    final_report = forge_verifier.verify(final_files, request=request)
    final_path, final_src = _primary_script(
        final_files,
        final_report.weakest_path if isinstance(final_report.weakest_path, str) else "",
    )
    if final_path and final_src.strip():
        final_code = code.verify(final_src, request=request or final_path)
        state["last_code"] = {
            "path": final_path,
            "confidence": round(final_code.score, 4),
            "accepted_as_code": final_code.accepted,
            "issues": list(final_code.issues),
            "advisory": True,
        }
    accepted = bool(final_report.accepted)
    return {
        "kind": "forge-verify-loop",
        "ok": int(accepted),
        "accepted": accepted,
        "files": final_files,
        "verification": final_report.to_dict(),
        "verification_stats": forge_verifier.stats(),
        "code_verdict": state.get("last_code"),
        "trace": trace.to_dict(),
        "repairs": list(state["repairs"]),
        "rounds_detail": list(state["rounds_detail"]),
        "threshold": threshold,
        "stopped_reason": trace.stopped_reason,
        "stored_prose": 0,
    }
