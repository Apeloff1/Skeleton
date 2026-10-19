"""Adversarial code/game release-gate tests; no fabricated native benchmarks."""

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.code_delivery_quality import (
    CODE_CHECKS, GAME_CHECKS, CodeDeliveryQualityReviewer,
    QualityCheckResult, QualityReleaseError, QualityVerifierAdversary,
    required_checker_names, required_delivery_kind, verify_quality_receipt,
)
from skeleton.jeeves.agent.code_scrutiny_loop import CodeFinding, verify_scrutiny_receipts
from skeleton.jeeves.agent.types import Goal, stable_fingerprint


def checker(name, problems=()):
    def run(files):
        return QualityCheckResult(
            checker_id=name,
            source_digest=stable_fingerprint(dict(files)),
            passed=not problems,
            evidence_ref="host:" + name + ":" + stable_fingerprint(dict(files))[:20],
            findings=tuple(problems),
        )
    return run


def certified(kind="code", *, additional=()):
    return {key: checker(key) for key in required_checker_names(kind, additional)}


def test_enforced_core_tenets_and_clean_delivery():
    files = {"game/source.py": "def tick(dt):\n    return dt * 2\n"}
    review = CodeDeliveryQualityReviewer().inspect(
        "code", files, checkers=certified()
    )
    assert review.releasable
    assert len(review.standards) == len(CODE_CHECKS)
    assert review.scrutiny.stable_passes == 2
    assert len(review.scrutiny.receipts) == 2
    assert {name for name, ref in review.checker_evidence} == set(CODE_CHECKS)
    assert all(ref.startswith("host:") for _, ref in review.checker_evidence)
    verify_scrutiny_receipts(review.scrutiny)
    proof = QualityVerifierAdversary().review(review, files=files, kind="code")
    assert len(proof) == 64


def test_lint_syntax_and_error_search_require_checkers():
    files = {"app.py": "return 0"}
    missing = certified()
    missing.pop("lint")
    with pytest.raises(QualityReleaseError, match="lint"):
        CodeDeliveryQualityReviewer().inspect("code", files, checkers=missing)
    valid = CodeDeliveryQualityReviewer().inspect("code", files, checkers=certified())
    assert not valid.releasable
    assert any(issue.code == "PY_SYNTAX" for issue in valid.scrutiny.findings)


def test_incomplete_game_review_blocks_playthrough_claim():
    files = {"game/main.py": "def render():\n    return True\n"}
    with pytest.raises(QualityReleaseError, match="playthrough"):
        CodeDeliveryQualityReviewer().inspect("game", files, checkers=certified("code"))
    full = CodeDeliveryQualityReviewer().inspect("game", files, checkers=certified("game"))
    assert full.releasable
    assert set(GAME_CHECKS).issubset(set(full.standards))


def test_source_evidence_must_be_typed_exact_and_attributable():
    files = {"app.py": "pass\n"}
    checkers = certified()
    checkers["lint"] = lambda sources: ()
    with pytest.raises(QualityReleaseError, match="typed result"):
        CodeDeliveryQualityReviewer().inspect("code", files, checkers=checkers)
    checkers = certified()
    checkers["lint"] = lambda sources: QualityCheckResult(
        "lint", "0" * 64, True, "fabricated:evidence",
    )
    with pytest.raises(QualityReleaseError, match="stale"):
        CodeDeliveryQualityReviewer().inspect("code", files, checkers=checkers)


def test_extra_requested_requirements_add_but_never_remove_core():
    extra = ("console_compatibility", "save_resume")
    files = {"game.py": "print('ok')"}
    with pytest.raises(QualityReleaseError, match="console_compatibility"):
        CodeDeliveryQualityReviewer().inspect(
            "code", files, checkers=certified(), additional_requirements=extra
        )
    with pytest.raises(QualityReleaseError, match="save_resume"):
        CodeDeliveryQualityReviewer().inspect(
            "code", files,
            checkers={**certified(), "console_compatibility": checker("console_compatibility")},
            additional_requirements=extra,
        )
    verified = CodeDeliveryQualityReviewer().inspect(
        "code", files, checkers=certified(additional=extra),
        additional_requirements=extra,
    )
    assert verified.releasable
    assert set(extra).issubset(verified.standards)
    assert set(CODE_CHECKS).issubset(verified.standards)


def test_error_search_and_repairs_rescan_until_stable():
    files = {"src.py": "def f(:\n    pass\n"}
    state = {"calls": 0}
    def repair(source, findings, pass_number):
        state["calls"] += 1
        assert pass_number == 1
        assert any(f.category == "syntax" for f in findings)
        return {"src.py": "def f():\n    pass\n"}
    repaired = CodeDeliveryQualityReviewer().inspect(
        "code", files, checkers=certified(), repair=repair,
        authorize_repairs=True,
    )
    assert repaired.releasable
    assert repaired.scrutiny.corrections == 1
    assert len(repaired.scrutiny.receipts) == 3
    assert state["calls"] == 1


def test_repair_absent_cannot_authorize_false_success():
    file = {"app.py": "def nope(:\n  pass"}
    report = CodeDeliveryQualityReviewer().inspect(
        "code", file, checkers=certified(), authorize_repairs=True,
    )
    assert not report.releasable
    assert report.scrutiny.status == "blocked_no_repair"


def test_verifier_adversary_detects_tampered_quality_evidence():
    files = {"app.py": "def correct():\n    return 1\n"}
    clean = CodeDeliveryQualityReviewer().inspect("code", files, checkers=certified())
    changed = replace(clean, checker_evidence=())
    with pytest.raises(QualityReleaseError, match="evidence"):
        verify_quality_receipt(changed, files=files, kind="code", required=())


def test_code_and_game_intent_detection_refuses_metadata_bypass():
    assert required_delivery_kind(Goal("g1", "Implement game engine features")) == "game"
    assert required_delivery_kind(Goal("g2", "Fix Python code errors")) == "code"
    assert required_delivery_kind(Goal("g3", "Explain game history")) is None
    assert required_delivery_kind(Goal(
        "g4", "Build a game", metadata={"delivery_kind": "non_code"}
    )) == "game"


def test_checker_failure_with_no_detail_is_still_blocking():
    files = {"app.py": "pass"}
    checks = certified()
    checks["efficiency"] = lambda sources: QualityCheckResult(
        "efficiency", stable_fingerprint(dict(sources)), False,
        "host:benchmark-failed",
    )
    outcome = CodeDeliveryQualityReviewer().inspect("code", files, checkers=checks)
    assert not outcome.releasable
    assert any(f.code == "CHECK_FAILED" for f in outcome.scrutiny.findings)
