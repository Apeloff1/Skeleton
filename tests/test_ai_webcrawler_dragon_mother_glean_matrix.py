"""Mother Dragon: audited cross-hatchling subtext, repeated lens probes and handoff."""
from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
)
from skeleton.ai.webcrawler.dragon_nest_progression import (
    AcquiredKnowledge, feed_parent, learn_when_idle, new_nest,
)
from skeleton.ai.webcrawler.dragon_mother_glean_matrix import (
    HatchlingReceipt, LENSES, glean_mother_insights, verify_mother_report,
)
from skeleton.ai.webcrawler.dragon_mother_glean_ledger import MotherGleanLedger

OWNER = "mother-owner"
T0 = "2026-10-12T12:00:00Z"
T1 = "2026-10-12T12:10:00Z"
T2 = "2026-10-12T12:20:00Z"
ALL_MEANING = (
    "Movement because feedback enables player agency while latency creates "
    "performance tradeoff and failure fallback. Accessibility input and "
    "console hardware port require adaptive systemic interaction and "
    "transfer across genre. Updated revision tests benchmark replay for "
    "license permission, adversarial exploit and attack prevention."
)


def document(source, *, group=None, at=T0, statement=ALL_MEANING,
             text="Movement original observations.", stance="supports"):
    host = "www.youtube.com" if source == "beta" else source + ".example.org"
    return ReviewedDocument(
        OWNER, source, "https://" + host + "/research",
        "Movement research", text, at, "rights-reference",
        ("design_reference",), "qualified-reviewer", True,
        (ReviewedNote("note-" + source, "movement", statement, 0, 8,
                      stance, 975000, group or ("group-" + source),
                      ("movement", "gameplay")),),
    )


@pytest.fixture
def scenario(tmp_path):
    knowledge = ReviewedKnowledgeStore(tmp_path / "mother_reviewed.sqlite")
    original = {}
    for sid in ("alpha", "beta", "gamma"):
        original[sid] = knowledge.import_document(
            document(sid), expected_parent_digest=None, authorized=True,
        )
    # The freshness hatchling needs a real changed *canonical* revision.
    knowledge.import_document(
        document("gamma", at="2026-10-12T12:05:00Z",
                 text="Movement original observations. Newly reviewed changes."),
        expected_parent_digest=original["gamma"].revision_digest,
        authorized=True,
    )
    hits = {source: knowledge.search(
        OWNER, "movement", authorized=True, diversify=False
    ) for source in ("alpha", "beta", "gamma")}
    all_hits = hits["alpha"]
    by_id = {hit.source_id: hit for hit in all_hits}
    nest = new_nest(
        OWNER, ("alpha", "beta", "gamma"),
        focus_tags=("movement",), adjacent_tags=("gameplay",), at=T0,
    )
    for sid in ("alpha", "beta", "gamma"):
        nest = feed_parent(
            nest, sid, content_sha256=by_id[sid].source_text_digest,
            at=T1, authorized=True, reviewed=True, lawful=True,
        )
    receipts = []
    for lane, sid in (("article", "alpha"), ("video", "beta"), ("updates", "gamma")):
        item = by_id[sid]
        nest = learn_when_idle(
            nest, lane,
            AcquiredKnowledge(
                sid, item.source_text_digest, T1, ("movement",), True, True,
                .99, "2026-10-12T12:05:00Z", lane,
            ),
            at=T1, idle_since=T0, consented=True,
            background_allowed=True, owner_authorized=True,
        )
        receipts.append(HatchlingReceipt(
            lane, sid, item.source_text_digest, "note-" + sid, T1,
        ))
    db = sqlite3.connect(":memory:")
    ledger = MotherGleanLedger(
        db, signing_key=b"mother-shadow-history-secret-32bytes-long",
    )
    try:
        yield knowledge, nest, tuple(receipts), ledger, db
    finally:
        knowledge.close()
        db.close()


def run(knowledge, nest, acquisitions, *, at=T2, idle_since=T1, **changes):
    opts = dict(owner_authorized=True, consented=True, background_allowed=True)
    opts.update(changes)
    return glean_mother_insights(
        knowledge, nest, acquisitions, at=at, idle_since=idle_since, **opts,
    )


def test_mother_searches_each_hatchling_three_times_across_twelve_lenses(scenario):
    knowledge, nest, acquisitions, _, _ = scenario
    result = run(knowledge, nest, acquisitions)
    assert result.schema == "skeleton.dragon.mother_glean.v1"
    assert len(result.probes) == len(acquisitions) * 3 * len(LENSES)
    assert {p.lens for p in result.probes} == {x.key for x in LENSES}
    assert all(p.query.startswith("movement ") for p in result.probes)
    assert all(p.digest and p.evidence_ids for p in result.probes)
    assert result.hypotheses
    assert all(h.status == "shadow_hypothesis" and h.independent_groups >= 2
               and h.empirically_validated is False
               and h.model_promotion_authorized is False
               for h in result.hypotheses)
    assert result.synergies
    assert any(s.lenses == ("causal", "failure") for s in result.synergies)
    assert result.neural_weights_modified is False
    assert result.promotion_authorized is False
    assert "no automatic weight promotion" in result.improvement
    assert verify_mother_report(result)
    assert result == run(knowledge, nest, acquisitions)


@pytest.mark.parametrize("changes", [
    {"owner_authorized": False}, {"consented": False},
    {"background_allowed": False},
    {"idle_since": "2026-10-12T12:19:59Z"},
])
def test_mother_is_idle_only_and_owner_authorized(scenario, changes):
    knowledge, nest, acquisitions, _, _ = scenario
    with pytest.raises(PermissionError):
        run(knowledge, nest, acquisitions, **changes)


def test_forged_or_missing_hatchling_receipts_refused(scenario):
    knowledge, nest, acquisitions, _, _ = scenario
    forged = replace(acquisitions[0], source_text_digest="f" * 64)
    with pytest.raises(ValueError, match="lineage"):
        run(knowledge, nest, (forged,))
    with pytest.raises(ValueError, match="duplicate"):
        run(knowledge, nest, (acquisitions[0], acquisitions[0]))
    with pytest.raises(ValueError):
        run(knowledge, replace(nest, head="e" * 64), acquisitions)
    with pytest.raises(ValueError, match="future"):
        run(
            knowledge, nest, acquisitions, at=T0,
            idle_since="2026-10-12T11:00:00Z",
        )


def test_freshness_video_and_source_revision_bound_to_canonical_review(scenario):
    knowledge, nest, acquisitions, _, _ = scenario
    incorrect_lane = replace(acquisitions[1], lane="article")
    # A copy of video evidence in a different hatchling lane is not eligible.
    with pytest.raises(ValueError, match="lineage"):
        run(knowledge, nest, (incorrect_lane,))
    original = knowledge.history(OWNER, "alpha", authorized=True)[-1]
    knowledge.import_document(
        document("alpha", at="2026-10-12T12:15:00Z",
                 text="Movement facts updated and confirmed."),
        expected_parent_digest=original.revision_digest, authorized=True,
    )
    with pytest.raises(ValueError, match="lineage|active reviewed"):
        run(knowledge, nest, (acquisitions[0],))


def test_conflicting_sources_never_become_shadow_hypotheses(scenario):
    knowledge, nest, acquisitions, _, _ = scenario
    latest = knowledge.history(OWNER, "gamma", authorized=True)[-1]
    knowledge.import_document(
        document(
            "gamma", at="2026-10-12T12:15:00Z",
            text="Movement revised through contradictory claims.",
            statement="Movement because latency fails in this case.",
            stance="challenges",
        ),
        expected_parent_digest=latest.revision_digest, authorized=True,
    )
    # Unrelated/revised source is no longer a valid child acquisition.
    with pytest.raises(ValueError):
        run(knowledge, nest, acquisitions)
    # Restrict acquisition to article alpha, whose content is still current.
    report = run(knowledge, nest, (acquisitions[0],))
    assert not [h for h in report.hypotheses if h.lens == "causal"]
    assert report.conflict_ids


def test_repeated_same_publisher_does_not_fake_independent_glean(scenario):
    knowledge, nest, acquisitions, _, _ = scenario
    latest = knowledge.history(OWNER, "beta", authorized=True)[-1]
    knowledge.import_document(
        document("beta", at="2026-10-12T12:15:00Z",
                 group="group-alpha", text="Movement newly updated."),
        expected_parent_digest=latest.revision_digest, authorized=True,
    )
    latest = knowledge.history(OWNER, "gamma", authorized=True)[-1]
    knowledge.import_document(
        document("gamma", at="2026-10-12T12:16:00Z",
                 group="group-alpha", text="Movement newly updated, same group."),
        expected_parent_digest=latest.revision_digest, authorized=True,
    )
    report = run(knowledge, nest, (acquisitions[0],))
    assert len(report.probes) == 3 * len(LENSES)
    assert not report.hypotheses
    assert report.research_gaps


def test_report_tampering_and_ledgers_are_fail_closed(scenario):
    knowledge, nest, acquisitions, ledger, db = scenario
    report = ledger.run(
        knowledge, nest, acquisitions, at=T2, idle_since=T1,
        owner_authorized=True, consented=True, background_allowed=True,
    )
    assert verify_mother_report(report)
    assert not verify_mother_report(replace(
        report, improvement="(fabricated gain)",
    ))
    assert ledger.history(OWNER, authorized=True) == (report,)
    # Repeated polls do not multiply reports or count as independent searches.
    duplicate = ledger.run(
        knowledge, nest, acquisitions,
        at="2026-10-12T12:25:00Z", idle_since=T1,
        owner_authorized=True, consented=True, background_allowed=True,
    )
    assert duplicate == report
    assert len(ledger.history(OWNER, authorized=True)) == 1
    with pytest.raises(PermissionError):
        ledger.history(OWNER, authorized=False)
    db.execute("UPDATE dragon_mother_glean SET payload='{}' WHERE owner=?", (OWNER,))
    db.commit()
    with pytest.raises(ValueError, match="signature"):
        ledger.history(OWNER, authorized=True)


def test_no_corroboration_is_a_research_gap_not_model_improvement(tmp_path):
    lib = ReviewedKnowledgeStore(tmp_path / "single.sqlite")
    lib.import_document(document("alpha"), expected_parent_digest=None, authorized=True)
    hit = lib.search(OWNER, "movement", authorized=True)[0]
    nest = new_nest(OWNER, ("alpha",), focus_tags=("movement",), at=T0)
    nest = feed_parent(nest, "alpha", content_sha256=hit.source_text_digest,
                       at=T0, authorized=True, reviewed=True, lawful=True)
    nest = learn_when_idle(
        nest, "article",
        AcquiredKnowledge(
            "alpha", hit.source_text_digest, T1, ("movement",), True,
            True, .99, None, "article",
        ),
        at=T1, idle_since=T0, consented=True,
        background_allowed=True, owner_authorized=True,
    )
    acquisition = HatchlingReceipt("article", "alpha", hit.source_text_digest,
                                   "note-alpha", T1)
    result = run(lib, nest, (acquisition,))
    assert not result.hypotheses
    assert not result.synergies
    assert len(result.research_gaps) == len(LENSES)
    lib.close()
