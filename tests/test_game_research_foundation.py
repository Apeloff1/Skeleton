"""Synthetic fixtures for reviewer, historical-IP and original-design boundaries."""
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import repeat
import json
import subprocess
import sys

import pytest

from skeleton.ai.game_builder.contracts import EvaluatorProvenance
from skeleton.ai.game_builder.game_research_foundation import (
    TARGETS, ReviewerAssessment, ReviewObservation, acquisition_targets,
    assess_reviewer, distill_observation,
)
from skeleton.ai.game_builder.game_ip_watch import IPWatchSubject, IPStatusReport, plan_ip_watch
from skeleton.ai.game_builder.successor_blueprints import (
    ORIGINALITY_AREAS, SuccessorBlueprint, OriginalityReview, plan_successor_pipeline,
)
from skeleton.ai.game_builder.dragon_porting import JurisdictionReview, REVIEW_AREAS
from skeleton.ai.game_builder.rights import RightsLedger, RightsState, SourceRecord, UseKind

BODY = "The reviewer found the jump timing frustrating in this recorded session."
DIGEST = sha256(BODY.encode()).hexdigest()
URL = "https://review.example/episode"


def authority(method="measurement"):
    return EvaluatorProvenance("reviewer", "operation", "execution", "1"*64, "2"*64,
        "deterministic_control", "3"*64, method, "4"*40, output_evidence_refs=("e"*64,))


def rights(state=RightsState.FACTS_IDEAS_REFERENCE_ONLY):
    ledger = RightsLedger()
    for sid in ("source-a", "source-b"):
        ledger.register_source(SourceRecord(sid, DIGEST, state,
            frozenset() if state is RightsState.UNKNOWN_QUARANTINE else frozenset({UseKind.FACTS_IDEAS_REFERENCE}),
            "review", authority(), "e"*64))
    return ledger


def peers(domain="critical_opinion"):
    return tuple(ReviewerAssessment("source-a", DIGEST, URL, f"peer-{i}", f"group-{i}",
        "publisher", f"https://peer{i}.example/review", str(i)*64,
        domain, True, True, True, True, 900, 2000) for i in (1, 2))


def observation(target="game_review"):
    spec = next(t for t in TARGETS if t.target_id == target)
    return ReviewObservation("obs", target, "game-id", "source-a", URL, BODY, 0, len(BODY),
        "00:10-00:16", "The reviewer expressed frustration, not a population-wide finding.",
        tuple((key, "documented fixture context") for key in spec.required_context))


def test_catalog_covers_every_requested_target_without_granting_rights():
    plan = acquisition_targets("Original homebrew")
    ids = {t["target_id"] for t in plan["targets"]}
    assert {"lets_play", "angry_video_game_nerd", "nostalgia_critic", "blog_review",
        "news_review", "news_engagement", "homebrew", "abandonware", "unlicensed",
        "closed_studio", "reviewer_peer_review", "title_catalog", "mechanic_catalog", "patent_watch"} <= ids
    assert not plan["acquisition_authorized"] and not plan["training_authorized"]
    assert all(t["reputation"] == "not_preapproved" for t in plan["targets"])
    assert acquisition_targets("Title", limit=3)["deferred_targets"] == 12


@pytest.mark.parametrize("target", [t.target_id for t in TARGETS])
def test_every_category_remains_attributed_not_empirical_truth(target):
    spec = next(t for t in TARGETS if t.target_id == target)
    result = distill_observation(observation(target), rights(), peers(spec.evidence_role), now=1000, authorized=True)
    assert result["ready_for_distillation_review"]
    assert result["citation"]["exact_quote"] == BODY
    assert result["citation"]["url"] == URL
    assert not result["empirical_fact"] and not result["reuse_authorized"]
    assert not result["memory_promotion_authorized"]


def test_peer_quality_requires_two_current_independent_documented_assessments():
    for records in (peers()[:1], (peers()[0], replace(peers()[1], reviewer_group="group-1")),
                    (peers()[0], replace(peers()[1], evidence_digest="1"*64)),
                    (peers()[0], replace(peers()[1], sponsorship_disclosed=False)),
                    (peers()[0], replace(peers()[1], expires_at=1000)),
                    (peers()[0], replace(peers()[1], reviewer_group="publisher"))):
        assert not assess_reviewer("source-a", DIGEST, "critical_opinion", records, now=1000)["accepted_for_attributed_analysis"]


def test_peer_dependency_transitive_bridge_cannot_multiply_votes():
    a, b = peers()
    middle = replace(a, reviewer_id="middle", evidence_digest=b.evidence_digest)
    result = assess_reviewer("source-a", DIGEST, "critical_opinion", (a, middle, b), now=1000)
    assert result["independent_review_groups"] == 1


def test_missing_context_custody_and_unlicensed_reuse_fail_closed():
    result = distill_observation(replace(observation(), context=()), rights(), peers(), now=1000, authorized=True)
    assert not result["ready_for_distillation_review"] and result["missing_context"]
    with pytest.raises(ValueError, match="custody"):
        distill_observation(replace(observation(), source_text=BODY+" changed"), rights(), peers(), now=1000, authorized=True)
    with pytest.raises(ValueError, match="rights"):
        distill_observation(observation(), rights(RightsState.UNKNOWN_QUARANTINE), peers(), now=1000, authorized=True)
    with pytest.raises(ValueError, match="URL"):
        distill_observation(replace(observation(), source_url="https://other.example/"), rights(), peers(), now=1000, authorized=True)


def subject():
    return IPWatchSubject("patent-a", "game-id", "patent", "US", "US-fixture", ("abandonware", "closed_studio"))


def reports():
    return (
        IPStatusReport("official", "patent-a", "US", "patent", "US-fixture", "https://patentcenter.uspto.gov/fixture",
            "official_register", "office", "a"*64, "c"*64, "record:status", "expired", 800, 900),
        IPStatusReport("news", "patent-a", "US", "patent", "US-fixture", "https://news.example/fixture",
            "news", "newsroom", "b"*64, "d"*64, "paragraph:4", "expired", 800, 900),
    )


def watch(rows=None, **kw):
    return plan_ip_watch((subject(),), reports() if rows is None else rows, now=1000, authorized=True, **kw)["subjects"][0]


def test_ip_crosscheck_never_grants_reuse_even_for_inactive_labels():
    result = watch()
    assert result["state"] == "crosschecked_report_requires_legal_review"
    assert not result["reuse_authorized"] and not result["release_authority"]


def test_news_alone_or_same_record_copies_do_not_establish_expiry():
    assert "current_primary_record_required" in watch(reports()[1:])["reasons"]
    assert "independent_crosscheck_required" in watch((reports()[0], replace(reports()[1], content_digest="a"*64)))["reasons"]
    disguised = replace(reports()[1], url="https://fees.uspto.gov/fixture", publisher_group="different")
    assert "independent_crosscheck_required" in watch((reports()[0], disguised))["reasons"]


def test_ip_conflicts_lapse_expiry_and_missing_sources_request_review():
    assert "conflicting_status_or_expiry" in watch((reports()[0], replace(reports()[1], reported_status="active")))["reasons"]
    assert "reinstatement_and_grace_period_review_required" in watch(tuple(replace(r, reported_status="lapsed") for r in reports()))["reasons"]
    assert "expiry_basis_incomplete_or_future" in watch(tuple(replace(r, reported_expiry=2000) for r in reports()))["reasons"]
    assert "status_unresolved" in watch(())["reasons"]
    assert "stale_or_future_source_requires_refresh" in watch((replace(reports()[0], observed_at=1001), reports()[1]))["reasons"]


def test_ip_territory_binding_and_history_are_preserved():
    with pytest.raises(ValueError, match="territory"):
        watch((replace(reports()[0], jurisdiction="NO"),))
    changed = replace(reports()[0], report_id="new-official", content_digest="f"*64,
                      observed_at=950, reported_status="reinstated")
    result = watch((*reports(), changed))
    assert len(result["history"]) == 3 and len(result["changes"]) == 1
    assert result["reported_status"] == "unknown"
    with pytest.raises(ValueError, match="same-time"):
        watch((*reports(), replace(changed, observed_at=900)))


def blueprints():
    base = SuccessorBlueprint("base", "Clock Orchard", "industrial", "puzzle", "A gardener repairs a communal clock orchard.",
        "ink", "alternate 1880", "route clockwork water", "draw original orchard art", "implement new simulation",
        "a"*64, ("source-a", "source-b"))
    product = SuccessorBlueprint("roof", "Tidal Observatory", "interstellar", "exploration",
        "An astronomer negotiates seasonal migration routes for drifting habitats.", "luminous geometry",
        "far future", "coordinate tidal navigation and habitat resources", "create new habitat designs",
        "write original orbital simulation", "b"*64, ("source-a", "source-b"), base.digest)
    return base, product


def pipeline(legal=(), originals=(), pair=None):
    return plan_successor_pipeline(*(pair or blueprints()), rights(), target_id="pc_windows",
        jurisdictions=("NO",), legal_reviews=legal, originality_reviews=originals, now=1000, authorized=True)


def test_roof_is_original_design_proposal_not_a_legal_avoidance_certificate():
    report = pipeline()
    assert len(report["changed_creative_axes"]) == 6
    assert not report["pipeline_review_ready"]
    assert all(p["review_blockers"] and p["build_state"] == "not_built" for p in report["projects"])
    assert not report["release_authority"]


def test_parent_clearance_does_not_transfer_to_new_product():
    base, roof = blueprints()
    legal = tuple(JurisdictionReview(base.digest, "pc_windows", "NO", area, "cleared", 900, 2000,
        "e"*64, authority("human-legal-review")) for area in REVIEW_AREAS)
    original = tuple(OriginalityReview(base.digest, area, "independent", "f"*64, "cleared", 900, 2000) for area in ORIGINALITY_AREAS)
    report = pipeline(legal, original)
    assert report["projects"][0]["review_ready"]
    assert not report["projects"][1]["review_ready"]
    with pytest.raises(ValueError, match="bind"):
        pipeline(pair=(base, replace(roof, parent_digest="f"*64)))


def test_bounded_iterators_and_real_catalog_cli():
    with pytest.raises(ValueError, match="bounded"):
        plan_ip_watch(repeat(subject()), (), now=1000, authorized=True)
    run = subprocess.run([sys.executable, "-m", "skeleton.ai.game_builder.game_research_foundation",
        "--title", "Original homebrew"], text=True, capture_output=True, check=True)
    assert json.loads(run.stdout) == json.loads(json.dumps(acquisition_targets("Original homebrew")))


def test_ip_watch_cli_authentication_and_actual_batch_roundtrip(tmp_path):
    path = tmp_path / "watch.json"
    path.write_text(json.dumps({"subjects": [asdict(subject())], "reports": [asdict(r) for r in reports()]}))
    command = [sys.executable, "-m", "skeleton.ai.game_builder.game_ip_watch", "--input", str(path), "--as-of", "1000"]
    denied = subprocess.run(command, capture_output=True, text=True)
    assert denied.returncode != 0 and "authentication" in denied.stderr
    run = subprocess.run([*command, "--trusted-local-operator"], capture_output=True, text=True, check=True)
    result = json.loads(run.stdout)
    assert result["subjects"][0]["watch_digest"] == watch()["watch_digest"]
    assert not result["global_completeness"] and not result["dispatch_authorized"]


def test_full_project_review_still_cannot_release_and_expires_independently():
    legal = tuple(JurisdictionReview(project.digest, "pc_windows", "NO", area, "cleared", 900, 2000,
        "e"*64, authority("human-legal-review")) for project in blueprints() for area in REVIEW_AREAS)
    original = tuple(OriginalityReview(project.digest, area, "independent", "f"*64, "cleared", 900, 2000)
                     for project in blueprints() for area in ORIGINALITY_AREAS)
    ready = pipeline(legal, original)
    assert ready["pipeline_review_ready"] and not ready["release_authority"]
    expired = tuple(replace(r, expires_at=1000) if r.artifact_digest == blueprints()[1].digest else r for r in original)
    result = pipeline(legal, expired)
    assert result["projects"][0]["review_ready"] and not result["projects"][1]["review_ready"]
