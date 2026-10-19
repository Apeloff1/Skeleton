"""Mandatory source-quality release contract for Jeeves code and game delivery.

The quality gate is a host boundary, not a quality score synthesized by a model.
Every domain needs independently executed checker callbacks, complete file
coverage and two stable clean passes. A failing or missing checker blocks release.
Benchmarks/gameplay need real host adapters; no static scan can certify speed or
playthrough by itself. Runtime callers bind actual reviewed sources and callbacks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable, Mapping, Sequence

from .code_scrutiny_loop import (
    Checker, CodeFinding, CodeScrutinyLoop, Discovery, Repair, ScrutinyOutcome,
    ScrutinyPolicy, verify_scrutiny_receipts,
)
from .types import Goal, stable_fingerprint

QUALITY_TENETS: tuple[str, ...] = (
    "modularity", "efficiency", "performance", "cleanliness",
    "maintainability", "machine_friendly",
)
CODE_CHECKS = ("lint", "code_review", "error_search", "tests") + QUALITY_TENETS
GAME_CHECKS = ("game_logic", "asset_integrity", "playthrough", "game_performance")
_GAME_NOUNS = re.compile(
    r"\b(?:game|gaming|world|scene|sprite|asset|engine|emulator|rom|"
    r"character|npc|level|quest|cutscene)\b", re.IGNORECASE,
)
_CODE_NOUNS = re.compile(
    r"\b(?:code|coding|program|app|software|source|script|function|module|"
    r"repository|repo|pull request|prs|typescript|python|rust|git|pipeline|"
    r"build|compiler|interface|api|algorithm)\b", re.IGNORECASE,
)
_ACTION = re.compile(
    r"\b(?:build|implement|code|write|generate|develop|fix|correct|repair|"
    r"refactor|modify|upgrade|deliver|create|ship|release|compile|"
    r"integrate|extend|merge|produce)\b", re.IGNORECASE,
)


def required_delivery_kind(goal: Goal) -> str | None:
    """Classify explicitly flagged builds and clearly executable coding tasks."""
    kind = goal.metadata.get("delivery_kind")
    if kind is not None:
        if kind not in {"code", "game", "non_code"}:
            raise ValueError("delivery_kind must be code, game, or non_code")
        return None if kind == "non_code" else str(kind)
    objective = goal.objective
    if not _ACTION.search(objective):
        return None
    if _GAME_NOUNS.search(objective):
        return "game"
    if _CODE_NOUNS.search(objective):
        return "code"
    return None


@dataclass(frozen=True, slots=True)
class CodeDeliveryQualityPolicy:
    """Core tenets cannot be disabled; project constraints are additive."""
    max_passes: int = 24
    stability_passes: int = 2
    max_files: int = 512
    max_file_chars: int = 250_000

    def __post_init__(self) -> None:
        values = (self.max_passes, self.stability_passes, self.max_files, self.max_file_chars)
        if any(type(x) is not int or x < 2 for x in values):
            raise ValueError("quality budgets must be positive and support two clean passes")
        if self.max_passes < self.stability_passes:
            raise ValueError("quality passes cannot establish stability")


@dataclass(frozen=True, slots=True)
class QualityReleaseReceipt:
    kind: str
    source_digest: str
    standards: tuple[str, ...]
    executed_checkers: tuple[str, ...]
    scrutiny: ScrutinyOutcome
    status: str
    failures: tuple[str, ...]

    @property
    def digest(self) -> str:
        return stable_fingerprint({
            "kind": self.kind,
            "source": self.source_digest,
            "standards": self.standards,
            "executed_checkers": self.executed_checkers,
            "scrutiny": self.scrutiny.fingerprint,
            "status": self.status,
            "failures": self.failures,
        })

    @property
    def releasable(self) -> bool:
        return self.status == "verified_clean" and not self.failures


class QualityReleaseError(ValueError):
    """Mandatory code standards or hostile verifier probes failed."""


def required_checker_names(kind: str, extras: Sequence[str] = ()) -> tuple[str, ...]:
    if kind not in {"code", "game"}:
        raise ValueError("unsupported delivery kind")
    names = CODE_CHECKS + (GAME_CHECKS if kind == "game" else ())
    for extra in extras:
        if not isinstance(extra, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", extra):
            raise ValueError("invalid additional quality requirement")
        if extra not in names:
            names += (extra,)
    return names


def _validate_obligations(
    kind: str, checkers: Mapping[str, Checker],
    additional: Sequence[str],
) -> tuple[str, ...]:
    required = required_checker_names(kind, additional)
    missing = tuple(name for name in required if not callable(checkers.get(name)))
    if missing:
        raise QualityReleaseError(
            "mandatory code-quality checkers not registered: " + ", ".join(missing)
        )
    if any(not isinstance(name, str) or not callable(callback)
           for name, callback in checkers.items()):
        raise QualityReleaseError("invalid registered quality checker")
    return required


def verify_quality_receipt(
    receipt: QualityReleaseReceipt,
    *,
    files: Mapping[str, str],
    kind: str,
    required: Sequence[str],
) -> None:
    """Independently reconstruct release authorization, not a reported score."""
    expected = required_checker_names(kind, required)
    if receipt.kind != kind or receipt.standards != expected:
        raise QualityReleaseError("core or additional quality tenets were removed")
    if tuple(x for x in expected if x not in receipt.executed_checkers):
        raise QualityReleaseError("quality checker coverage missing")
    if receipt.source_digest != stable_fingerprint(dict(files)):
        raise QualityReleaseError("quality verification is stale for these sources")
    verify_scrutiny_receipts(receipt.scrutiny)
    if dict(receipt.scrutiny.files) != dict(files):
        raise QualityReleaseError("quality source differs from reviewed source")
    if receipt.releasable and not receipt.scrutiny.success:
        raise QualityReleaseError("clean release claimed for failed scrutiny")
    if receipt.releasable and receipt.scrutiny.stable_passes < 2:
        raise QualityReleaseError("clean release lacks two stable independent passes")


class CodeDeliveryQualityReviewer:
    """Iteratively discover, inspect, repair (if authorized), and verify code."""

    def __init__(self, policy: CodeDeliveryQualityPolicy | None = None) -> None:
        self.policy = policy or CodeDeliveryQualityPolicy()

    def inspect(
        self,
        kind: str,
        files: Mapping[str, str],
        *,
        checkers: Mapping[str, Checker],
        additional_requirements: Sequence[str] = (),
        discover: Discovery | None = None,
        repair: Repair | None = None,
        authorize_repairs: bool = False,
    ) -> QualityReleaseReceipt:
        required = _validate_obligations(kind, checkers, additional_requirements)
        seen: set[str] = set()

        def check_all(sources: Mapping[str, str]) -> Sequence[CodeFinding]:
            gathered: list[CodeFinding] = []
            for name in required:
                # On each pass every domain must execute against identical source bytes.
                outcomes = checkers[name](dict(sources))
                if outcomes is None:
                    raise QualityReleaseError(f"{name} checker returned no evidence")
                findings = tuple(outcomes)
                if any(not isinstance(item, CodeFinding) for item in findings):
                    raise QualityReleaseError(f"{name} checker produced an invalid finding")
                if any(item.path not in sources for item in findings):
                    raise QualityReleaseError(f"{name} checker reported a file outside review scope")
                gathered.extend(findings)
                seen.add(name)
            return tuple(gathered)

        scrutiny = CodeScrutinyLoop(ScrutinyPolicy(
            maximum_passes=self.policy.max_passes,
            stability_passes=self.policy.stability_passes,
            maximum_files=self.policy.max_files,
            maximum_chars_per_file=self.policy.max_file_chars,
        )).run(
            files,
            lint=check_all,
            discover=discover,
            repair=repair,
            authorized=authorize_repairs,
            seed_terms=("syntax", "lint", "exception", "error", "complexity",
                        "import", "performance", "asset", "playthrough"),
        )
        outcome = QualityReleaseReceipt(
            kind=kind,
            source_digest=stable_fingerprint(dict(scrutiny.files)),
            standards=required,
            executed_checkers=tuple(name for name in required if name in seen),
            scrutiny=scrutiny,
            status="verified_clean" if scrutiny.success else "blocked",
            failures=() if scrutiny.success else (
                scrutiny.reason,
                *(f"{f.path}:{f.line}:{f.code}" for f in scrutiny.findings[:32]),
            ),
        )
        verify_quality_receipt(
            outcome, files=scrutiny.files, kind=kind,
            required=additional_requirements,
        )
        return outcome


class QualityVerifierAdversary:
    """Mutation challenges to the final quality receipt verifier itself."""

    def review(self, clean: QualityReleaseReceipt, *,
               files: Mapping[str, str], kind: str,
               required: Sequence[str] = ()) -> str:
        if not clean.releasable:
            raise QualityReleaseError("cannot attest blocked source release")
        verify_quality_receipt(clean, files=files, kind=kind, required=required)
        from dataclasses import replace
        mutations = (
            ("stale_source", replace(clean, source_digest="0" * 64), dict(files)),
            ("dropped_standard", replace(clean, standards=()), dict(files)),
            ("checker_omission", replace(clean, executed_checkers=()), dict(files)),
            ("file_mutation", clean, dict(files, **{
                next(iter(files)): files[next(iter(files))] + "\n# changed after check"
            })),
            ("fake_scrutiny", replace(clean, scrutiny=replace(
                clean.scrutiny, status="blocked_no_repair",
            )), dict(files)),
        )
        proofs = []
        for name, mutated, source in mutations:
            try:
                verify_quality_receipt(mutated, files=source, kind=kind, required=required)
            except (QualityReleaseError, ValueError):
                proofs.append(name)
            else:
                raise QualityReleaseError(f"quality verifier accepted adversarial {name}")
        return stable_fingerprint({
            "quality_receipt": clean.digest, "rejected_mutations": proofs,
            "kind": kind, "standards": clean.standards,
        })
