"""Adversarial originality gate and multi-modal provenance checks for game ports.

Synthetic in-memory references only; tests never embed actual commercial games.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.game_builder.plagiarism_guard import (
    AssetDeclaration, AssetDisposition, AttributionStatus, ExpressionSample,
    OriginalityDisposition, OriginalityError, UseBasis, audit_game_originality,
    find_expression_overlap,
)

PROOF = "b" * 64
REVIEW = "c" * 64
MODALITIES = (
    "artwork", "characters", "interface_appearance", "level_maps",
    "marketing_brand", "music_audio", "source_code", "story_dialogue",
)
SYNTHETIC_TEXT = (
    "Within the tiny bronze observatory a purple moth counted twelve "
    "copper stars and recorded their quiet voices on parchment."
)
SYNTHETIC_OTHER = (
    "The engineer arranged seven stones near an abandoned lighthouse "
    "and selected a different path for the merchant vessel."
)


def make_assets(*, text_included: bool = True, artwork_included: bool = False):
    results = []
    for modality in MODALITIES:
        included = (text_included and modality == "story_dialogue") or (
            artwork_included and modality == "artwork")
        results.append(AssetDeclaration(
            modality=modality,
            disposition=AssetDisposition.INCLUDED if included else AssetDisposition.NOT_USED,
            basis=UseBasis.OWN_CREATION if included else None,
            provenance_sha256=PROOF if included else None,
            author_identity="the project's author" if included else None,
            attribution=AttributionStatus.NOT_REQUIRED,
            comparable_media_screened=artwork_included and modality == "artwork",
            reviewer_evidence_sha256=REVIEW if artwork_included and modality == "artwork" else None,
        ))
    return tuple(results)


def sample(text=SYNTHETIC_TEXT, work_id="new_original_story"):
    return ExpressionSample(
        work_id=work_id, modality="story_dialogue", text=text,
        evidence_sha256=PROOF,
    )


def external(text, name="external_story"):
    return ExpressionSample(work_id=name, modality="story_dialogue", text=text)


def run(assets=None, candidates=None, references=None):
    return audit_game_originality(
        "lawful-evolution-game", assets=make_assets() if assets is None else assets,
        candidate_samples=(sample(),) if candidates is None else candidates,
        references=(external(SYNTHETIC_OTHER),) if references is None else references,
    )


def test_original_project_design_can_proceed_but_never_claim_nonplagiarism_certificate():
    report = run()
    assert report.disposition is OriginalityDisposition.DESIGN_ADMISSIBLE_NOT_LEGAL_CLEARANCE
    assert report.design_admissible is True
    assert report.overlap_findings == ()
    assert report.release_permitted is False
    assert report.legal_originality_certified is False
    assert report.independent_human_signoff_complete is False
    receipt = report.public_receipt()
    assert receipt["external_sources_exhaustively_searched"] is False
    assert receipt["legal_similarity_threshold_exists"] is False
    assert receipt["release_permitted"] is False
    assert receipt["screened_asset_classes"] == sorted(MODALITIES)
    assert "NONEXHAUSTIVE_SIMILARITY_CORPUS_AND_HUMAN_RELEASE_REVIEW_REQUIRED" in report.review_issues


def test_identical_protected_story_is_review_hold_and_does_not_quote_text_in_receipt():
    original = sample()
    report = run(references=(external(SYNTHETIC_TEXT),))
    assert report.disposition is OriginalityDisposition.HUMAN_REVIEW_REQUIRED
    assert len(report.overlap_findings) == 1
    finding = report.overlap_findings[0]
    assert finding.exact_normalized_match
    assert finding.triage_signal == "IDENTICAL_NORMALIZED_EXPRESSION"
    assert finding.legal_infringement_determined is False
    receipt = report.public_receipt()
    assert SYNTHETIC_TEXT not in str(receipt)
    assert len(finding.reference_sha256) == 64


def test_long_partial_text_copy_is_flagged_without_magical_legal_percentage():
    text = SYNTHETIC_TEXT + " The remaining words of the new tale are entirely different."
    prior = SYNTHETIC_TEXT + " Closing note."
    finding = find_expression_overlap(sample(text), external(prior))
    assert finding is not None
    assert finding.longest_consecutive_tokens >= 12
    assert finding.triage_signal == "LONG_IDENTICAL_EXPRESSION_RUN"


def test_reference_unrelated_or_mechanical_patterns_not_automatically_infringing():
    assert find_expression_overlap(sample(), external(SYNTHETIC_OTHER)) is None
    assert find_expression_overlap(
        ExpressionSample("one", "source_code", "for index in objects: render(index)"),
        ExpressionSample("two", "source_code", "for index in objects: render(index)"),
    ) is None
    assert find_expression_overlap(
        ExpressionSample("one", "source_code", "if player.health > 0: pass"),
        sample(),
    ) is None


def test_unlicensed_asset_is_blocked_even_without_similarity_database_match():
    a = list(make_assets())
    i = MODALITIES.index("story_dialogue")
    a[i] = replace(a[i], basis=UseBasis.UNLICENSED_PROTECTED)
    result = run(assets=tuple(a))
    assert result.disposition is OriginalityDisposition.BLOCKED
    assert "PROTECTED_EXPRESSION_UNLICENSED:story_dialogue" in result.blockers
    assert result.release_permitted is False


def test_false_authorship_claim_is_blocked_irrespective_of_game_copyright():
    a = list(make_assets())
    a[MODALITIES.index("story_dialogue")] = replace(
        a[MODALITIES.index("story_dialogue")], false_authorship_claim=True,
    )
    report = run(assets=tuple(a))
    assert report.disposition is OriginalityDisposition.BLOCKED
    assert "DECEPTIVE_AUTHORSHIP_OR_ATTRIBUTION:story_dialogue" in report.blockers


def test_music_and_graphics_require_real_modality_specific_provenance_review():
    unreviewed = list(make_assets(artwork_included=True))
    k = MODALITIES.index("artwork")
    unreviewed[k] = replace(
        unreviewed[k], comparable_media_screened=False, reviewer_evidence_sha256=None,
    )
    report = run(assets=tuple(unreviewed))
    assert report.disposition is OriginalityDisposition.HUMAN_REVIEW_REQUIRED
    assert "artwork" in report.unexamined_external_media
    assert "NON_TEXT_SIMILARITY_NOT_INDEPENDENTLY_REVIEWED:artwork" in report.review_issues
    reviewed = run(assets=make_assets(artwork_included=True))
    assert reviewed.design_admissible


def test_public_domain_does_not_erase_credit_requirements_or_review():
    a = list(make_assets())
    idx = MODALITIES.index("story_dialogue")
    a[idx] = replace(a[idx],
        basis=UseBasis.VERIFIED_PUBLIC_DOMAIN,
        public_domain_independently_checked=True,
        attribution=AttributionStatus.MISSING,
    )
    report = run(assets=tuple(a))
    assert report.disposition is OriginalityDisposition.HUMAN_REVIEW_REQUIRED
    assert "THIRD_PARTY_CREDIT_OR_ATTRIBUTION_MISSING:story_dialogue" in report.review_issues


def test_license_is_not_permission_for_every_use_or_without_credit():
    a = list(make_assets())
    idx = MODALITIES.index("story_dialogue")
    a[idx] = replace(a[idx], basis=UseBasis.LICENSED_REUSE,
                     license_identifier="CC-BY-4.0", rights_holder="synthetic author",
                     proposed_use_licensed=False,
                     attribution=AttributionStatus.MISSING)
    report = run(assets=tuple(a))
    assert "LICENSE_SCOPE_UNVERIFIED:story_dialogue" in report.review_issues
    assert "THIRD_PARTY_CREDIT_OR_ATTRIBUTION_MISSING:story_dialogue" in report.review_issues


def test_unknown_rights_and_missing_provenance_cannot_get_clean_design():
    a = list(make_assets())
    idx = MODALITIES.index("story_dialogue")
    a[idx] = replace(a[idx], basis=UseBasis.UNKNOWN)
    report = run(assets=tuple(a))
    assert report.disposition is OriginalityDisposition.HUMAN_REVIEW_REQUIRED
    assert "ASSET_ORIGIN_UNKNOWN:story_dialogue" in report.review_issues
    a[idx] = replace(a[idx], basis=UseBasis.OWN_CREATION,
                     provenance_sha256=None, author_identity=None)
    report = run(assets=tuple(a))
    assert "AUTHORSHIP_HISTORY_UNDOCUMENTED:story_dialogue" in report.review_issues


def test_empty_reference_corpus_is_never_false_clearance():
    report = run(references=())
    assert report.disposition is OriginalityDisposition.HUMAN_REVIEW_REQUIRED
    assert "NO_REFERENCE_CORPUS_PROVIDED" in report.review_issues


def test_submitted_text_is_bound_to_authorship_digest():
    result = run(candidates=(sample(work_id="fresh_text"),))
    assert result.design_admissible
    substituted = run(candidates=(ExpressionSample("fresh_text","story_dialogue",SYNTHETIC_TEXT,
                                                   evidence_sha256="e"*64),))
    assert substituted.disposition is OriginalityDisposition.HUMAN_REVIEW_REQUIRED
    assert "EXPRESSION_NOT_BOUND_TO_AUTHORED_PROVENANCE:story_dialogue" in substituted.review_issues


def test_explicit_unused_categories_and_all_eight_coverages_required():
    with pytest.raises(OriginalityError):
        run(assets=make_assets()[:-1])
    with pytest.raises(OriginalityError):
        run(assets=tuple(make_assets()) + (make_assets()[0],))
    with pytest.raises(OriginalityError):
        run(candidates=(sample(), ExpressionSample("fake_illustration", "artwork", "x")))
    with pytest.raises(OriginalityError):
        run(assets=tuple(replace(a, disposition=AssetDisposition.NOT_USED, basis=None)
                         if a.modality == "story_dialogue" else a for a in make_assets()))


def test_claim_of_complete_global_corpus_is_rejected():
    with pytest.raises(OriginalityError):
        audit_game_originality(
            "lawful-evolution-game", assets=make_assets(),
            candidate_samples=(sample(),), references=(external(SYNTHETIC_OTHER),),
            reference_corpus_declared_complete=True,
        )


def test_report_is_deterministic_and_identity_sensitive():
    a = run()
    assert a == run()
    assert a.screen_digest != run(references=(external(SYNTHETIC_OTHER + " One new sentence."),)).screen_digest
    assert a.screen_digest != run(candidates=(sample(SYNTHETIC_TEXT + " New ending."),)).screen_digest


def test_too_many_words_are_rejected_not_truncated_to_hide_copy():
    huge = "original " * 17000
    with pytest.raises(OriginalityError):
        run(candidates=(sample(huge),))


def test_malicious_bool_or_bad_asset_provenance_fails_closed():
    with pytest.raises(OriginalityError):
        AssetDeclaration("source_code", AssetDisposition.INCLUDED,
                         UseBasis.OWN_CREATION, "short", author_identity="author")
    with pytest.raises(OriginalityError):
        AssetDeclaration("source_code", AssetDisposition.INCLUDED,
                         UseBasis.OWN_CREATION, PROOF, author_identity="author",
                         comparable_media_screened="yes")
    with pytest.raises(OriginalityError):
        AssetDeclaration("story_dialogue", AssetDisposition.NOT_USED,
                         basis=UseBasis.OWN_CREATION)


def test_small_self_similar_generic_code_is_not_an_automatic_copyright_violation():
    code = ExpressionSample("own", "source_code", "score += 1; health -= 1")
    reference = ExpressionSample("public", "source_code", "score += 1; health -= 1")
    assert find_expression_overlap(code, reference) is None
