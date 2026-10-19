"""Adversarial comparative, objective, provenance and creative review contracts."""

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.final_delivery_reviews import (
    ComparativeObjectiveFinalReviewer, ContentReviewResult, FinalReviewAdversary,
    FinalReviewError, MeasuredCriterion, SourceProvenance, verify_final_release,
    required_final_kind,
)
from skeleton.jeeves.agent.types import Goal, stable_fingerprint


SOURCES = {
    "game/scene.md": "An original sky-island mechanic using the user's story bible.",
    "delivery/jeeves_final_answer.md": "Implemented a fictional sky-island scene.",
}
UPSTREAM = "a" * 64
AXES = ("modularity", "efficiency", "performance", "cleanliness",
        "maintainability", "machine_friendly")


def measurements(*, weak=None):
    return tuple(MeasuredCriterion(
        axis=axis, unit="index_points", method="same-fixture-v1",
        direction="higher", observed=2.0 if weak == axis else 91.0,
        baseline=80.0, target=85.0,
        observed_evidence="host:run-" + axis,
        baseline_evidence="host:baseline-" + axis,
        target_evidence="host:target-" + axis,
        sample_count=40, baseline_sample_count=40,
    ) for axis in AXES)


def provenance(files=SOURCES, **overrides):
    entries = []
    for path, value in files.items():
        options = dict(
            path=path, content_digest=stable_fingerprint(value),
            origin="original", rights_evidence="host:originality:" + path,
            permitted_use=True,
        )
        options.update(overrides.get(path, {}))
        entries.append(SourceProvenance(**options))
    return tuple(entries)


def check(stage, events, *, passed=True, covered=None, scope=None, findings=()):
    def callback(sources, rights):
        events.append(stage)
        return ContentReviewResult(
            stage=stage, source_digest=stable_fingerprint(dict(sources)),
            checker="host:" + stage,
            evidence_ref="host:evidence:" + stage,
            review_scope=scope or "fictional game corpus and declared source licenses",
            covered_paths=tuple(sources if covered is None else covered),
            passed=passed, findings=tuple(findings),
            checked_dimensions=(
                ("provenance", "permissions", "license_conditions", "source_similarity")
                if stage == "copyright"
                else ("originality", "substantive_transformation", "canon", "author_voice")
            ),
        )
    return callback


def review(files=SOURCES, metrics=None, rights=None, copyright=None, rewrite=None, events=None):
    log = [] if events is None else events
    return ComparativeObjectiveFinalReviewer().inspect(
        "game", files,
        metrics=measurements() if metrics is None else metrics,
        provenance=provenance(files) if rights is None else rights,
        copyright_checker=copyright or check("copyright", log),
        rewrite_checker=rewrite or check("creative_rewrite", log),
        upstream_quality_digest=UPSTREAM,
    )


def test_real_order_and_content_bound_receipts():
    events = []
    result = review(events=events)
    assert result.passed and not result.findings
    assert events == ["copyright", "creative_rewrite"]
    assert [x.stage for x in result.receipts] == [
        "comparative", "objective", "copyright", "creative_rewrite",
    ]
    assert result.receipts[0].serial == "JVR-000001-P000001"
    assert result.receipts[-1].previous == result.receipts[-2].digest
    assert result.upstream_quality_digest == UPSTREAM
    assert result.source_digest == stable_fingerprint(SOURCES)
    verify_final_release(result, SOURCES, upstream_quality_digest=UPSTREAM)
    proof = FinalReviewAdversary.challenge(
        result, SOURCES, upstream_quality_digest=UPSTREAM,
    )
    assert len(proof) == 64


def test_comparison_regressions_and_failed_objectives_cannot_pass():
    result = review(metrics=measurements(weak="efficiency"))
    assert not result.passed
    assert "comparative:efficiency:regressed" in result.findings
    assert "objective:efficiency:below_target" in result.findings
    with pytest.raises(FinalReviewError, match="cannot attest"):
        FinalReviewAdversary.challenge(
            result, SOURCES, upstream_quality_digest=UPSTREAM,
        )


def test_missing_core_axis_and_unsupported_metric_values_block():
    with pytest.raises(FinalReviewError, match="missing objective"):
        review(metrics=measurements()[:-1])
    with pytest.raises(FinalReviewError, match="finite"):
        replace(measurements()[0], observed=float("nan"))
    with pytest.raises(FinalReviewError, match="samples"):
        replace(measurements()[0], sample_count=0)


def test_unknown_or_unauthorized_material_cannot_clear_copyright():
    rights = list(provenance())
    rights[0] = replace(rights[0], origin="unknown", permitted_use=False)
    result = review(rights=tuple(rights))
    assert not result.passed
    assert "copyright:game/scene.md:rights_unresolved" in result.findings


def test_licensed_material_requires_conditions_and_proof():
    original = provenance()[0]
    with pytest.raises(FinalReviewError, match="condition"):
        replace(original, origin="licensed")
    with_license = replace(
        original, origin="licensed",
        license_condition_evidence="host:license-conditions-v1",
    )
    rights = (with_license, *provenance()[1:])
    assert review(rights=rights).passed


def test_manifest_must_cover_every_rendered_asset_and_response():
    with pytest.raises(FinalReviewError, match="coverage"):
        review(rights=provenance()[:-1])
    rights = list(provenance())
    rights[0] = replace(rights[0], content_digest="0" * 64)
    with pytest.raises(FinalReviewError, match="stale"):
        review(rights=rights)


def test_copyright_checker_failure_or_missing_scope_blocks():
    result = review(
        copyright=check("copyright", [], passed=False,
                        findings=("source permissions unresolved",)),
    )
    assert not result.passed
    assert "copyright:source permissions unresolved" in result.findings
    with pytest.raises(FinalReviewError, match="evidence or scope"):
        review(copyright=check("copyright", [], scope=" "))


def test_rewrite_verifier_catches_cosmetic_paraphrase():
    result = review(
        rewrite=check("creative_rewrite", [], passed=False, findings=(
            "only names changed; narrative beats remain near-identical",
            "GDD canon mismatch",
        )),
    )
    assert not result.passed
    assert "creative_rewrite:GDD canon mismatch" in result.findings


def test_checker_cannot_certify_fewer_files_than_delivered():
    with pytest.raises(FinalReviewError, match="all source artifacts"):
        review(copyright=check("copyright", [], covered=("game/scene.md",)))
    with pytest.raises(FinalReviewError, match="all source artifacts"):
        review(rewrite=check("creative_rewrite", [], covered=("game/scene.md",)))


def test_missing_checker_fails_closed_and_no_legal_guarantee_implied():
    with pytest.raises(FinalReviewError, match="both final"):
        ComparativeObjectiveFinalReviewer().inspect(
            "game", SOURCES, metrics=measurements(), provenance=provenance(),
            copyright_checker=None, rewrite_checker=None,
            upstream_quality_digest=UPSTREAM,
        )


def test_receipt_reattachment_and_reordering_rejected():
    result = review()
    stale = replace(result, receipts=tuple(reversed(result.receipts)))
    with pytest.raises(FinalReviewError, match="stage ordering"):
        verify_final_release(stale, SOURCES, upstream_quality_digest=UPSTREAM)
    with pytest.raises(FinalReviewError, match="previous quality"):
        verify_final_release(result, SOURCES, upstream_quality_digest="b" * 64)


def test_changing_original_work_after_review_invalidates_copyright_and_rewrite():
    verified = review()
    edited = dict(SOURCES)
    edited["game/scene.md"] += " unreviewed copied dialogue"
    with pytest.raises(FinalReviewError, match="current source"):
        verify_final_release(
            verified, edited, upstream_quality_digest=UPSTREAM,
        )


def test_verifier_cannot_accept_fabricated_copyright_or_rewrite_pass():
    result = review()
    forged = replace(result, copyright=replace(result.copyright, passed=False))
    with pytest.raises(FinalReviewError, match="verdict"):
        verify_final_release(forged, SOURCES, upstream_quality_digest=UPSTREAM)
    forged = replace(result, creative_rewrite=replace(
        result.creative_rewrite, evidence_ref="different and unsupported",
    ))
    with pytest.raises(FinalReviewError, match="hash receipts"):
        verify_final_release(forged, SOURCES, upstream_quality_digest=UPSTREAM)


def test_creative_noncode_outputs_require_originality_and_coherence():
    sources = {"delivery/jeeves_final_answer.md": "A standalone short story."}
    metrics = (
        MeasuredCriterion(
            axis=axis, unit="score", method="narrative-review-v1",
            direction="higher", observed=90, baseline=80, target=85,
            observed_evidence="host:observed:" + axis,
            baseline_evidence="host:baseline:" + axis,
            target_evidence="host:target:" + axis,
            sample_count=3, baseline_sample_count=3,
        )
        for axis in ("originality", "coherence")
    )
    log = []
    result = ComparativeObjectiveFinalReviewer().inspect(
        "creative", sources, metrics=tuple(metrics),
        provenance=provenance(sources),
        copyright_checker=check("copyright", log),
        rewrite_checker=check("creative_rewrite", log),
    )
    assert result.passed and result.upstream_quality_digest is None
    assert log == ["copyright", "creative_rewrite"]


def test_creative_delivery_detection_and_noncreative_question():
    assert required_final_kind(Goal("g1", "Write a short story about an inventor")) == "creative"
    assert required_final_kind(Goal("g2", "Compose a song with original lyrics")) == "creative"
    assert required_final_kind(Goal("g3", "Create code in Python")) == "code"
    assert required_final_kind(Goal("g4", "Implement a game engine")) == "game"
    assert required_final_kind(Goal("g5", "Explain the history of poetry")) is None


def test_separate_rights_and_rewrite_verifiers_cannot_share_evidence():
    events = []
    same = check("copyright", events)
    with pytest.raises(FinalReviewError, match="separate host callbacks"):
        review(copyright=same, rewrite=same)
    def identical_evidence(sources, rights):
        return ContentReviewResult(
            stage="creative_rewrite", source_digest=stable_fingerprint(dict(sources)),
            checker="host:creative_rewrite",
            evidence_ref="host:evidence:copyright",
            review_scope="authorial continuity and narrative canon",
            covered_paths=tuple(sources), passed=True,
            checked_dimensions=(
                "originality", "substantive_transformation", "canon", "author_voice",
            ),
        )
    with pytest.raises(FinalReviewError, match="independent"):
        review(rewrite=identical_evidence)


def test_copyright_must_check_similarity_permissions_license_and_provenance():
    def omissions(files, rights):
        return ContentReviewResult(
            stage="copyright", source_digest=stable_fingerprint(dict(files)),
            checker="host:copyright", evidence_ref="host:evidence:copyright",
            review_scope="scanned inventory only", covered_paths=tuple(files),
            passed=True, checked_dimensions=("provenance",),
        )
    with pytest.raises(FinalReviewError, match="mandatory scrutiny dimensions"):
        review(copyright=omissions)


def test_rewrite_must_verify_originality_actual_transformation_voice_and_canon():
    def omissions(files, rights):
        return ContentReviewResult(
            stage="creative_rewrite", source_digest=stable_fingerprint(dict(files)),
            checker="host:rewrite", evidence_ref="host:evidence:rewrite",
            review_scope="reviewed narrative", covered_paths=tuple(files),
            passed=True, checked_dimensions=("originality", "substantive_transformation"),
        )
    with pytest.raises(FinalReviewError, match="mandatory scrutiny dimensions"):
        review(rewrite=omissions)
