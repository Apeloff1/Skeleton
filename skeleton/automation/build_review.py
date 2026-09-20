"""Deterministic and model-assisted review helpers for feature builds."""
from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Sequence

from .build_contracts import (
    BuildBudget,
    BuildReview,
    CandidateFile,
    ReviewFinding,
    candidate_public_summary,
    extract_json_object,
)
from .build_validation import ValidationDiagnostic
from .free_model import FreeModelClient


@dataclass(frozen=True, slots=True)
class StaticFinding:
    severity: str
    category: str
    path: str
    message: str

    def to_review_finding(self) -> ReviewFinding:
        return ReviewFinding(
            severity=self.severity,
            category=self.category,
            path=self.path,
            message=self.message,
            required=self.severity in {"blocker", "high"},
        )


def static_review(
    files: Sequence[CandidateFile],
) -> tuple[StaticFinding, ...]:
    findings: list[StaticFinding] = []
    for item in files:
        path = item.path
        content = item.content

        if path.endswith((".py", ".pyi")):
            try:
                ast.parse(content, filename=path)
            except SyntaxError as exc:
                findings.append(
                    StaticFinding(
                        severity="blocker",
                        category="syntax",
                        path=path,
                        message=(
                            f"Python syntax invalid near line "
                            f"{exc.lineno or 0}"
                        ),
                    )
                )
        elif path.endswith(".json"):
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                findings.append(
                    StaticFinding(
                        severity="blocker",
                        category="syntax",
                        path=path,
                        message=f"JSON syntax invalid near line {exc.lineno}",
                    )
                )

        if content and not content.endswith("\n"):
            findings.append(
                StaticFinding(
                    severity="low",
                    category="format",
                    path=path,
                    message="text file should end with a newline",
                )
            )

        lowered = content.casefold()
        secret_markers = (
            "-----begin private key-----",
            "ghp_",
            "github_pat_",
            "sk-proj-",
        )
        if any(marker in lowered for marker in secret_markers):
            findings.append(
                StaticFinding(
                    severity="blocker",
                    category="secret",
                    path=path,
                    message="candidate resembles embedded credential material",
                )
            )

        suffix = PurePosixPath(path).suffix.casefold()
        if suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
            if "eval(" in content or "exec(" in content:
                findings.append(
                    StaticFinding(
                        severity="medium",
                        category="dynamic_execution",
                        path=path,
                        message=(
                            "candidate introduces dynamic execution; "
                            "requires explicit justification"
                        ),
                    )
                )
    return tuple(findings)


def _review_content(
    files: Sequence[CandidateFile],
    *,
    per_file_bytes: int = 8_000,
    total_bytes: int = 120_000,
) -> str:
    """Render bounded candidate excerpts so review sees implementation detail."""
    chunks: list[str] = []
    used = 0
    for item in sorted(files, key=lambda value: value.path):
        raw = item.content.encode("utf-8")
        clipped = raw[:per_file_bytes].decode("utf-8", errors="ignore")
        suffix = "\n[TRUNCATED]\n" if len(raw) > per_file_bytes else "\n"
        block = f"\n--- {item.path} sha256={item.digest} ---\n{clipped}{suffix}"
        size = len(block.encode("utf-8"))
        if used + size > total_bytes:
            break
        chunks.append(block)
        used += size
    return "".join(chunks)


def _validation_finding(
    item: ValidationDiagnostic,
) -> ReviewFinding:
    severity_map = {
        "blocker": "blocker",
        "error": "high",
        "warning": "medium",
        "info": "low",
    }
    return ReviewFinding(
        severity=severity_map[item.severity],
        category=item.code.replace("-", "_"),
        path=item.path,
        message=item.message,
        required=item.blocking,
    )


def _merge_deterministic_findings(
    static: Sequence[StaticFinding],
    validation: Sequence[ValidationDiagnostic],
    *,
    budget: BuildBudget,
) -> tuple[ReviewFinding, ...]:
    merged: list[ReviewFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in (
        [item.to_review_finding() for item in static]
        + [_validation_finding(item) for item in validation]
    ):
        key = (
            finding.category,
            finding.path,
            finding.message,
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(finding)
        if len(merged) >= budget.max_review_findings:
            break
    return tuple(merged)


def render_review_prompt(
    *,
    objective: str,
    acceptance: Sequence[str],
    files: Sequence[CandidateFile],
    static_findings: Sequence[StaticFinding],
    validation_findings: Sequence[ValidationDiagnostic] = (),
) -> str:
    manifest = candidate_public_summary(files)
    static_payload = [
        {
            "severity": item.severity,
            "category": item.category,
            "path": item.path,
            "message": item.message,
        }
        for item in static_findings
    ]
    validation_payload = [
        item.as_dict()
        for item in validation_findings
    ]
    candidate_content = _review_content(files)
    return f"""Review an autonomous repository build candidate.

Objective:
{objective}

Acceptance criteria:
{json.dumps(list(acceptance), ensure_ascii=True)}

Candidate manifest, content digests only:
{json.dumps(manifest, sort_keys=True)}

Deterministic static findings:
{json.dumps(static_payload, sort_keys=True)}

Deterministic candidate validation diagnostics:
{json.dumps(validation_payload, sort_keys=True)}

Bounded candidate content:
{candidate_content}

Review for missing acceptance coverage, cross-file integration, regressions,
unsafe assumptions, incomplete tests, public API drift, and obvious security
mistakes. Repository permissions, CI configuration, and security gates are not
modifiable by this builder.

Return JSON only with this shape:
{{
  "verdict": "accept",
  "summary": "review summary",
  "confidence": 80,
  "findings": [
    {{
      "severity": "medium",
      "category": "integration",
      "path": "optional/repo/path",
      "message": "finding",
      "required": false
    }}
  ]
}}
"""


def model_review(
    *,
    client: FreeModelClient,
    objective: str,
    acceptance: Sequence[str],
    files: Sequence[CandidateFile],
    budget: BuildBudget,
    validation_findings: Sequence[ValidationDiagnostic] = (),
) -> BuildReview:
    static = static_review(files)
    deterministic = _merge_deterministic_findings(
        static,
        validation_findings,
        budget=budget,
    )
    if any(item.required for item in deterministic):
        return BuildReview(
            verdict="repair",
            summary="Deterministic validation found blocking defects.",
            findings=deterministic,
            confidence=100,
        )

    raw = client.chat(
        (
            "You are a conservative code-review stage. "
            "Return bounded JSON only."
        ),
        render_review_prompt(
            objective=objective,
            acceptance=acceptance,
            files=files,
            static_findings=static,
            validation_findings=validation_findings,
        ),
        max_tokens=4_000,
    )
    review = BuildReview.from_payload(
        extract_json_object(raw),
        budget=budget,
    )

    if deterministic:
        merged = list(review.findings)
        known = {
            (item.category, item.path, item.message)
            for item in merged
        }
        for finding in deterministic:
            key = (
                finding.category,
                finding.path,
                finding.message,
            )
            if key not in known:
                merged.append(finding)
        merged = merged[: budget.max_review_findings]
        verdict = review.verdict
        if any(item.required for item in merged):
            verdict = "repair"
        review = BuildReview(
            verdict=verdict,
            summary=review.summary,
            findings=tuple(merged),
            confidence=review.confidence,
        )
    return review


def repair_prompt(
    *,
    objective: str,
    files: Sequence[CandidateFile],
    review: BuildReview,
) -> str:
    findings = [
        item.as_dict()
        for item in review.findings
        if item.required
    ]
    manifest = candidate_public_summary(files)
    return f"""Repair a bounded autonomous build candidate.

Objective:
{objective}

Required review findings:
{json.dumps(findings, sort_keys=True)}

Current file manifest:
{json.dumps(manifest, sort_keys=True)}

Return only paths that must change to satisfy required findings. For each path,
either return complete final content in files OR bounded exact-anchor operations
in edits. Do not add new paths. Exact anchors must be copied from the supplied
current content and must match uniquely.

Return JSON only:
{{
  "summary": "repair summary",
  "files": [
    {{"path": "existing/planned/path", "content": "complete content", "intent": "repair"}}
  ],
  "edits": [
    {{
      "path": "existing/planned/path",
      "intent": "repair one bounded defect",
      "edits": [
        {{
          "kind": "replace",
          "anchor": "exact unique current text",
          "replacement": "corrected text"
        }}
      ]
    }}
  ],
  "tests": ["regression intent"]
}}
"""
