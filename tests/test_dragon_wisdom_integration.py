"""Cross-owner dragon review, legal freshness and original-story regressions."""
from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.ai.game_builder.contracts import (
    ArtifactIdentity, Candidate, Challenge, EvaluatorProvenance, ProducerProvenance,
    QUALITY_AXES, Rival, canonical_digest,
)
from skeleton.ai.game_builder.dual_rival_forge import DualRivalForge
from skeleton.ai.game_builder.control_plane import ForgeControlPlane
from skeleton.ai.game_builder.resource_governor import ResourceEnvelope, ResourceGovernor
from skeleton.ai.game_builder.quality_debt import QualityDebtLedger
from skeleton.ai.game_builder.evaluation import EvaluationPanel, JudgeVerdict
from skeleton.ai.game_builder.dragon_wisdom import IndustryMeasurement, review_candidate
from skeleton.ai.game_builder.dragon_legal_updates import LegalSourceObservation, legal_update_impact, legal_recrawl_plan
from skeleton.ai.game_builder.dragon_porting import (
    JurisdictionReview, MechanicInfusion, REVIEW_AREAS, legal_release_blockers, plan_homebrew_port,
)
from skeleton.ai.game_builder.story_digest import (
    OriginalIngredients, ProfitEvidence, StoryReference, compose_original_premise,
    analyze_story_reference, digest_references, rank_by_profit, triage_story,
)
from skeleton.ai.game_builder.rights import (
    IncorporationDecision, RightsLedger, RightsState, SourceRecord, UseKind,
)


ARTIFACT = "a"*64
EVIDENCE = "e"*64
WORKLOAD = "f"*64
SOURCE = "A navigator explores a city and rebuilds trust through civic service."


def provenance(name="judge", method="measurement", evidence=EVIDENCE):
    return EvaluatorProvenance(name, "review-operation", "review-execution",
        "1"*64, "2"*64, "deterministic_control", "3"*64, method, "4"*40,
        output_evidence_refs=(evidence,))


def candidate(producer=Rival.A.value, token="first"):
    identity = canonical_digest(token)
    pp = ProducerProvenance("project", "run", token, token, identity,
        identity, identity, identity, "4"*40, output_artifact_refs=(ARTIFACT,),
        output_evidence_refs=(EVIDENCE,))
    return Candidate.create(producer_id=producer, producer_provenance=pp,
        artifact=ArtifactIdentity(ARTIFACT, "b"*64, "c"*64, "GB03", "GBL-021"),
        quality={axis: .7 for axis in QUALITY_AXES}, evidence_digests=(EVIDENCE,),
        assumption_digest=EVIDENCE)


def panel(c, score=.7):
    p = EvaluationPanel(("j1", "j2", "j3"))
    for i, name in enumerate(p.evaluator_ids):
        method = f"method-{i}"
        p.submit(JudgeVerdict.create(evaluator_id=name,
            evaluator_provenance=provenance(name, method), candidate_digest=c.digest,
            quality={axis: score for axis in QUALITY_AXES}, confidence=.9,
            evidence_digest=EVIDENCE, method_id=method))
    return p


def rights():
    ledger = RightsLedger()
    ledger.register_source(SourceRecord("source", sha256(SOURCE.encode()).hexdigest(),
        RightsState.FACTS_IDEAS_REFERENCE_ONLY, frozenset({UseKind.FACTS_IDEAS_REFERENCE}),
        "game-analysis", provenance(), EVIDENCE))
    decision = ledger.decide_incorporation(source_id="source", artifact_digest=ARTIFACT,
        use_kind=UseKind.FACTS_IDEAS_REFERENCE)
    return ledger, decision


def reviews(target="pc_windows", disposition="cleared"):
    return tuple(JurisdictionReview(ARTIFACT, target, "NO", area, disposition,
        10, 100, EVIDENCE, provenance(method="human-legal-review")) for area in sorted(REVIEW_AREAS))


def review(c=None, *, comparators=(), legal=None, terminal=False):
    c = c or candidate()
    ledger, receipt = rights()
    return review_candidate(DualRivalForge(effort_mode=100, champion=c), panel(c), ledger,
        candidate=c, workload_digest=WORKLOAD, now=20, incorporation_decisions=(receipt,),
        target_id="pc_windows", jurisdictions=("NO",), legal_reviews=reviews() if legal is None else legal,
        comparators=comparators, terminal=terminal)


def test_dragon_reports_four_squares_and_both_rival_improvements():
    result = review()
    assert [s["id"] for s in result.squares] == ["play", "craft", "delivery", "trust"]
    assert all(s["industry_score"] is None for s in result.squares)
    assert {i.target for i in result.improvements} == {Rival.A.value, Rival.B.value}
    assert not result.blockers
    assert result.to_payload()["release_authority"] is False


def test_existing_control_plane_calls_the_dragon_projection():
    c = candidate()
    owner = ForgeControlPlane(forge=DualRivalForge(effort_mode=100, champion=c),
        evaluation_panel=panel(c), resource_governor=ResourceGovernor(ResourceEnvelope(
            1000, 100, 10000, 10, 2, 2, 1)), quality_debt=QualityDebtLedger())
    ledger, receipt = rights()
    before = owner.checkpoint_bundle()
    result = owner.dragon_review(rights=ledger, candidate=c, workload_digest=WORKLOAD,
        now=20, incorporation_decisions=(receipt,), target_id="pc_windows",
        jurisdictions=("NO",), legal_reviews=reviews())
    assert result.candidate_digest == c.digest and owner.checkpoint_bundle() == before


def test_industry_comparison_uses_matched_fresh_measured_peers_only():
    measure = IndustryMeasurement("peer", WORKLOAD, tuple((a, .8) for a in QUALITY_AXES),
        10, 100, EVIDENCE, provenance())
    result = review(comparators=(measure,))
    assert result.squares[0]["industry_delta"] == -10
    assert review(comparators=(replace(measure, workload_digest="d"*64),)).squares[0]["industry_score"] is None
    assert review(comparators=(replace(measure, expires_at=20),)).squares[0]["industry_score"] is None
    with pytest.raises(ValueError, match="duplicate"):
        review(comparators=(measure, measure))


def test_candidate_claimed_quality_does_not_override_panel():
    c = candidate()
    ledger, receipt = rights()
    result = review_candidate(DualRivalForge(effort_mode=100, champion=c), panel(c, .4), ledger,
        candidate=c, workload_digest=WORKLOAD, now=20, incorporation_decisions=(receipt,),
        target_id="pc_windows", jurisdictions=("NO",), legal_reviews=reviews())
    assert result.squares[0]["score"] == 40


def test_no_terminal_card_before_exact_refinement_budget():
    with pytest.raises(ValueError, match="completed champion"):
        review(terminal=True)


def test_terminal_review_follows_one_hundred_complete_governed_rounds():
    champion = candidate(token="champion")
    forge = DualRivalForge(effort_mode=100, champion=champion)
    for index in range(100):
        built = candidate(forge.builder.value, f"build-{index}")
        improved = candidate(forge.challenger.value, f"attack-{index}")
        forge.submit_construct(built)
        forge.submit_attack(Challenge(forge.challenger.value, built.digest, EVIDENCE, improved, (EVIDENCE,)))
        forge.reconcile(submitted=None, evaluator_id="judge", evaluator_provenance=provenance(),
            authority_evidence_digest=EVIDENCE, gate_results=())
    assert forge.completed and len(forge.receipts) == 100
    ledger, receipt = rights()
    result = review_candidate(forge, panel(champion), ledger, candidate=champion,
        workload_digest=WORKLOAD, now=20, incorporation_decisions=(receipt,),
        target_id="pc_windows", jurisdictions=("NO",), legal_reviews=reviews(), terminal=True)
    assert result.terminal and result.completed_rounds == 100
    assert result.to_payload()["release_authority"] is False
    import sqlite3
    from skeleton.ai.game_builder.dragon_review_store import DragonReviewStore
    db = sqlite3.connect(":memory:")
    store = DragonReviewStore(db, signing_key=b"s"*32)
    with pytest.raises(PermissionError):
        store.publish("alice", result, now=20, expires_at=40, trusted_worker=False)
    digest = store.publish("alice", result, now=20, expires_at=40, trusted_worker=True)
    assert store.publish("alice", result, now=20, expires_at=40, trusted_worker=True) == digest
    snapshot = store.latest("alice", now=21, authorized=True)
    assert snapshot["review"] == result.to_payload()
    assert store.latest("bob", now=21, authorized=True) is None
    assert store.latest("alice", now=19, authorized=True) is None
    assert store.latest("alice", now=40, authorized=True) is None
    with pytest.raises(PermissionError):
        store.latest("alice", now=21, authorized=False)
    db.execute("UPDATE dragon_wisdom_snapshots SET owner='bob'")
    with pytest.raises(ValueError, match="rebound"):
        store.latest("bob", now=21, authorized=True)
    db.execute("UPDATE dragon_wisdom_snapshots SET owner='alice',body=body||' '")
    with pytest.raises(ValueError, match="integrity"):
        store.latest("alice", now=21, authorized=True)


def test_pending_both_rivals_can_be_reviewed_without_forge_mutation():
    champion, built, improved = candidate(token="champion"), candidate(token="built"), candidate(Rival.B.value, "improved")
    forge = DualRivalForge(effort_mode=100, champion=champion)
    forge.submit_construct(built)
    forge.submit_attack(Challenge(Rival.B.value, built.digest, EVIDENCE, improved, (EVIDENCE,)))
    ledger, receipt = rights()
    before = forge.checkpoint()
    for c in (built, improved):
        result = review_candidate(forge, panel(c), ledger, candidate=c, workload_digest=WORKLOAD,
            now=20, incorporation_decisions=(receipt,), target_id="pc_windows", jurisdictions=("NO",), legal_reviews=reviews())
        assert result.candidate_digest == c.digest
    assert forge.checkpoint() == before


def test_missing_stale_and_wrong_target_legal_evidence_blocks():
    result = review(legal=())
    assert len(result.blockers) == len(REVIEW_AREAS)
    assert result.squares[3]["status"] == "blocked"
    stale = tuple(replace(r, expires_at=20) for r in reviews())
    assert len(review(legal=stale).blockers) == len(REVIEW_AREAS)
    with pytest.raises(ValueError, match="another artifact or target"):
        review(legal=reviews("pc_linux"))


def test_primary_source_change_invalidates_review_in_actual_dragon_gate():
    old = LegalSourceObservation("copyright-guidance", "https://www.copyright.gov/circs/circ33.pdf",
        "NO", frozenset({"copyright"}), "b"*64, 5, EVIDENCE, provenance())
    current = replace(old, content_digest="c"*64, captured_at=15)
    impact = legal_update_impact((old,), (current,), reviews(), now=20)
    assert impact["invalidated_reviews"] == [[ARTIFACT, "pc_windows", "NO", "copyright"]]
    # The test scopes a supplied review to NO; it does not make US guidance
    # applicable to Norway by itself. Applicability is a reviewer decision.
    c = candidate()
    ledger, receipt = rights()
    result = review_candidate(DualRivalForge(effort_mode=100, champion=c), panel(c), ledger,
        candidate=c, workload_digest=WORKLOAD, now=20, incorporation_decisions=(receipt,),
        target_id="pc_windows", jurisdictions=("NO",), legal_reviews=reviews(),
        legal_source_baseline=(old,), legal_source_current=(current,))
    assert any("primary source" in b for b in result.blockers)
    assert result.squares[-1]["status"] == "blocked"
    assert not legal_update_impact((old,), (replace(old, captured_at=15),), reviews(), now=20)["events"]
    assert legal_recrawl_plan((old,), now=3605, interval_seconds=3600)[0]["due"]
    with pytest.raises(ValueError, match="primary-source"):
        replace(old, url="https://copyright.gov.attacker.example/case")
    with pytest.raises(ValueError, match="rebound"):
        legal_update_impact((old,), (replace(current, jurisdiction="US"),), reviews(), now=20)


def test_forged_allowed_rights_receipt_cannot_release():
    ledger, receipt = rights()
    body = {**receipt.decision_payload(), "use_kind": UseKind.EXPRESSIVE_INCORPORATION.value,
            "reason": "forged permission"}
    forged = IncorporationDecision(**{**body, "use_kind": UseKind.EXPRESSIVE_INCORPORATION,
        "decision_digest": canonical_digest(body)})
    allowed, blockers = ledger.release_gate(artifact_digest=ARTIFACT, incorporation_decisions=(forged,))
    assert not allowed and any("not issued" in b for b in blockers)


def test_story_digest_preserves_only_abstract_motifs_and_original_ingredients():
    ledger, _ = rights()
    reference = StoryReference("source", sha256(SOURCE.encode()).hexdigest(), SOURCE, ("exploration", "belonging"))
    digest = digest_references((reference,), ledger, artifact_digest=ARTIFACT)
    draft = compose_original_premise(OriginalIngredients("Mira the lens apprentice", "a canal neighborhood",
        "the public tide clock breaks", "the neighborhood restores shared water access",
        "renaissance", "interchangeable navigation lenses", EVIDENCE), digest)
    assert "printing press" in draft["premise"] and SOURCE not in draft["premise"]
    assert draft["release_authority"] is False
    assert triage_story(SOURCE, (reference,)).needs_independent_review
    assert triage_story("Use a ZELDA mask.", (), protected_terms=("zelda",)).needs_independent_review
    with pytest.raises(ValueError, match="custody"):
        digest_references((replace(reference, text=SOURCE+" changed"),), ledger, artifact_digest=ARTIFACT)


def test_story_source_is_actually_analyzed_without_exporting_its_expression():
    ledger, _ = rights()
    reference, evidence = analyze_story_reference(source_id="source", text=SOURCE,
        rights=ledger, artifact_digest=ARTIFACT)
    assert {"exploration", "renewal", "belonging"} <= set(reference.abstract_motifs)
    assert evidence["motif_counts"]["renewal"] == 1
    assert evidence["calibration"] == "heuristic_not_semantic_truth"
    assert SOURCE not in str(evidence)


def test_profit_ranking_accepts_losses_but_rejects_incomparable_claims():
    row = ProfitEvidence("a", "100.01", "USD", "lifetime-2025", "net_after_marketing", EVIDENCE, provenance())
    loss = replace(row, product_id="b", profit="-5")
    assert rank_by_profit((loss, row)) == (row, loss)
    with pytest.raises(ValueError, match="incomparable"):
        rank_by_profit((row, replace(loss, currency="EUR")))
    with pytest.raises(ValueError, match="finite"):
        replace(row, profit="NaN")


def test_cross_era_homebrew_port_keeps_style_and_adds_desktop_design_goals():
    mechanic = MechanicInfusion("lenses", "switch navigation abilities with crafted tools",
        "source", EVIDENCE, 1024, "add layered lighting and accessible lens indicators")
    plan = plan_homebrew_port(source_target="nes", destination_target="pc_windows",
        style="top_down_adventure", mechanics=(mechanic,), preserve=("tile readability", "snappy input"),
        memory_budget_bytes=512, artifact_digest=ARTIFACT, jurisdictions=("NO",), reviews=reviews(), now=20)
    assert plan["source_emitter_available"]
    assert plan["mechanics"][0]["implementation_goal"] == mechanic.desktop_enhancement
    assert plan["build_state"] == "not_built" and plan["release_authority"] is False
    assert not plan["release_blockers"]
    unsupported = plan_homebrew_port(source_target="nes", destination_target="ps5",
        style="top_down_adventure", mechanics=(mechanic,), preserve=("tiles",),
        memory_budget_bytes=2048, artifact_digest=ARTIFACT, jurisdictions=("NO",), reviews=(), now=20)
    assert not unsupported["source_emitter_available"]
    assert any("licensed SDK" in b for b in unsupported["release_blockers"])



def test_review_snapshot_validity_is_bounded_by_current_evidence():
    measure=IndustryMeasurement("peer", WORKLOAD, tuple((a,.8) for a in QUALITY_AXES),
        10,25,EVIDENCE,provenance())
    result=review(comparators=(measure,))
    assert result.reviewed_at==20 and result.valid_until==25
    assert result.to_payload()["valid_until"]==25
    assert review(legal=()).valid_until==320


def test_worker_cannot_republish_old_advice_as_fresh_or_extend_evidence_expiry():
    import sqlite3
    from skeleton.ai.game_builder.dragon_review_store import DragonReviewStore
    # Trusted-boundary receipt fixture; actual governed completion is tested above.
    result=replace(review(),terminal=True,completed_rounds=100)
    store=DragonReviewStore(sqlite3.connect(":memory:"),signing_key=b"s"*32)
    with pytest.raises(ValueError,match="fresh evidence"):
        store.publish("alice",result,now=51,expires_at=60,trusted_worker=True)
    with pytest.raises(ValueError,match="evidence validity"):
        store.publish("alice",result,now=20,expires_at=101,trusted_worker=True)
