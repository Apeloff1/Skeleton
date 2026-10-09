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


def test_originality_report_attaches_to_exact_playable_game_digest(tmp_path):
    from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
    from skeleton.ai.game_builder.port_planner import HomebrewSource
    from skeleton.ai.game_builder.legal_paths import (
        CreativeMode, HardwareAccessFacts, HomebrewLegalRequest,
        Jurisdiction, MaterialKind, MaterialRecord,
    )
    from skeleton.ai.game_builder.legal_native_export import (
        ClearedSourceExportError, compile_originality_gated_desktop,
        export_rights_aware_desktop,
    )

    project = "lawful-evolution-game"
    world = generate_playable_world(
        GameBuildIntent(
            project_id=project, title="Fresh orbit game", subtitle="New worlds",
            seed=8461, width=11, height=11, levels=1,
            collectibles_per_level=1, hazards_per_level=0,
        ),
        authorized=True,
    )
    evidence = "a" * 64
    source = HomebrewSource(
        project, "sega_dreamcast", "project_owned", evidence,
        ("new authored characters", "new tile puzzle", "new soundtrack"),
    )
    facts = HomebrewLegalRequest(
        project_id=project, source_platform_id="sega_dreamcast",
        target_platform_id="windows_modern", mode=CreativeMode.ORIGINAL,
        jurisdictions=(Jurisdiction.NO, Jurisdiction.EU_EEA),
        materials=(
            MaterialRecord("story", "story_dialogue", MaterialKind.ORIGINAL_EXPRESSION, PROOF),
        ), hardware=HardwareAccessFacts(), rights_packet_sha256=evidence,
    )
    audit = audit_game_originality(
        project, assets=make_assets(), candidate_samples=(sample(),),
        references=(external(SYNTHETIC_OTHER),), artifact_sha256=world.digest,
    )
    package = compile_originality_gated_desktop(
        world, source, facts, originality=audit, authorized=True,
    )
    receipt = package.legal_receipt()
    assert receipt["plagiarism_screened"] is True
    assert receipt["originality_artifact_bound"] is True
    assert receipt["originality_screen_digest"] == audit.screen_digest
    assert receipt["false_claim_of_plagiarism_free"] is False
    assert receipt["release_authorized"] is False
    exported = export_rights_aware_desktop(package, tmp_path / "original", authorized=True)
    assert (exported / "legal_review.json").is_file()
    assert __import__("json").loads(
        (exported / "legal_review.json").read_text(),
    )["originality_screen_digest"] == audit.screen_digest
    wrong_audit = replace(audit, artifact_sha256="f" * 64)
    with pytest.raises(ClearedSourceExportError):
        compile_originality_gated_desktop(world, source, facts,
                                         originality=wrong_audit, authorized=True)
    with pytest.raises(ClearedSourceExportError):
        compile_originality_gated_desktop(world, source, facts,
                                         originality=run(references=(external(SYNTHETIC_TEXT),)),
                                         authorized=True)
    with pytest.raises(ClearedSourceExportError):
        compile_originality_gated_desktop(world, source, facts,
                                         originality=None, authorized=True)


def test_unverified_plagiarism_input_cannot_self_certify_complete_source_search():
    baseline = run()
    assert baseline.design_admissible
    assert baseline.public_receipt()["external_sources_exhaustively_searched"] is False
    with pytest.raises(OriginalityError):
        run(candidates=(ExpressionSample("bad", "story_dialogue", "", PROOF),))



def _manifest_for_workspace(root, *, unsafe_reference_path=None):
    from skeleton.ai.game_builder.plagiarism_cli import scan_manifest
    import json
    root.mkdir()
    (root / "candidate.txt").write_text(SYNTHETIC_TEXT, encoding="utf-8")
    (root / "reference.txt").write_text(SYNTHETIC_OTHER, encoding="utf-8")
    document = {
        "schema": "skeleton.originality_input.v1",
        "project_id": "lawful-evolution-game",
        "artifact_sha256": "a"*64,
        "assets": [
            {
                "modality": row.modality,
                "disposition": row.disposition.value,
                "basis": row.basis.value if row.basis else None,
                "provenance_sha256": row.provenance_sha256,
                "author_identity": row.author_identity,
                "attribution": row.attribution.value,
            } for row in make_assets()
        ],
        "candidates": [
            {"work_id": "mine", "modality": "story_dialogue",
             "relative_path": "candidate.txt", "evidence_sha256": PROOF},
        ],
        "references": [
            {"work_id": "prior", "modality": "story_dialogue",
             "relative_path": unsafe_reference_path or "reference.txt"},
        ],
    }
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return manifest


def test_local_cli_scanner_produces_no_source_text_or_released_certificate(tmp_path):
    from skeleton.ai.game_builder.plagiarism_cli import scan_manifest, main
    root = tmp_path / "review"
    manifest = _manifest_for_workspace(root)
    report = scan_manifest(manifest, root)
    assert report["disposition"] == "design_admissible_not_legal_clearance"
    assert report["artifact_sha256"] == "a"*64
    assert SYNTHETIC_TEXT not in str(report)
    assert SYNTHETIC_OTHER not in str(report)
    out = tmp_path / "receipt.json"
    assert main(["scan", "--manifest", str(manifest), "--root", str(root),
                 "--receipt", str(out)]) == 0
    assert __import__("json").loads(out.read_text()) == report
    with pytest.raises(FileExistsError):
        main(["scan", "--manifest", str(manifest), "--root", str(root),
              "--receipt", str(out)])


@pytest.mark.parametrize("attack", ["../outside.txt", "/etc/passwd"])
def test_local_scan_refuses_directory_escape(tmp_path, attack):
    from skeleton.ai.game_builder.plagiarism_cli import scan_manifest
    root = tmp_path / "review"
    manifest = _manifest_for_workspace(root, unsafe_reference_path=attack)
    with pytest.raises(OriginalityError):
        scan_manifest(manifest, root)


def test_local_scan_refuses_symlinked_reference_and_binary_input(tmp_path):
    from skeleton.ai.game_builder.plagiarism_cli import scan_manifest
    root = tmp_path / "review"
    manifest = _manifest_for_workspace(root)
    reference = root / "reference.txt"
    reference.unlink()
    reference.symlink_to(root / "candidate.txt")
    with pytest.raises(OriginalityError):
        scan_manifest(manifest, root)
    reference.unlink()
    reference.write_bytes(b"hello\x00world")
    with pytest.raises(OriginalityError):
        scan_manifest(manifest, root)


def test_local_scan_refuses_incomplete_disclosures(tmp_path):
    from skeleton.ai.game_builder.plagiarism_cli import scan_manifest
    import json
    root = tmp_path / "review"
    manifest = _manifest_for_workspace(root)
    document = json.loads(manifest.read_text())
    document["assets"].pop()
    manifest.write_text(json.dumps(document))
    with pytest.raises(OriginalityError):
        scan_manifest(manifest, root)



def test_plagiarism_report_cannot_be_mutated_into_fake_clearance():
    from skeleton.ai.game_builder.plagiarism_guard import OriginalityDisposition
    flagged = run(references=(external(SYNTHETIC_TEXT),))
    assert flagged.disposition is OriginalityDisposition.HUMAN_REVIEW_REQUIRED
    with pytest.raises(OriginalityError):
        replace(flagged, disposition=OriginalityDisposition.DESIGN_ADMISSIBLE_NOT_LEGAL_CLEARANCE)
    with pytest.raises(OriginalityError):
        replace(flagged, legal_originality_certified=True)
    with pytest.raises(OriginalityError):
        replace(flagged, release_permitted=True)
    with pytest.raises(OriginalityError):
        replace(flagged, independent_human_signoff_complete=True)
    blocked_asset = list(make_assets())
    index = MODALITIES.index("story_dialogue")
    blocked_asset[index] = replace(blocked_asset[index], false_authorship_claim=True)
    blocked = run(assets=tuple(blocked_asset))
    with pytest.raises(OriginalityError):
        replace(blocked, disposition=OriginalityDisposition.HUMAN_REVIEW_REQUIRED)
