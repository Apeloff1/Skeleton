"""Mission capabilities 17-20: value, fairness, adaptive recrawl and stopping."""
from dataclasses import replace

import pytest

from skeleton.ai.webcrawler.core import CrawlPolicy
from skeleton.ai.webcrawler.dragon_mission_scheduler import (
    AcquisitionCandidate, PrioritizedAcquisition, RecrawlSource,
    rank_acquisition_candidates, allocate_host_dispatches,
    plan_adaptive_recrawls, decide_mission_stop,
)
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import (
    EvidencePass,
)
from skeleton.ai.webcrawler.dragon_source_independence import SourceProvenance
from skeleton.ai.webcrawler.dragon_provenance_assurance import assure_crawler_evidence


def candidate(name, host="example.org", *, gain=.8, relevance=.8,
              quality=.8, bytes=1000):
    return AcquisitionCandidate(
        f"https://{host}/{name}",relevance,gain,quality,bytes,
    )


def source(sid, polarity=True):
    return tuple(EvidencePass(
        sid,"rev",f"pass-{i}","mission",polarity,.9,.9,
        sid,f"span:{i}","Cited document observation",
    ) for i in (1,2,3))


def assurance(conflicting=False):
    observations=source("alpha")+source("beta",polarity=not conflicting)
    manifest=(
        SourceProvenance("alpha","a"*64,"https://alpha.example/doc"),
        SourceProvenance("beta","b"*64,"https://beta.example/doc"),
    )
    return assure_crawler_evidence("mission",observations,manifest,
                                   authorized=True)


def test_17_ranking_increases_with_information_gain_and_relevance():
    high=candidate("high",gain=.9)
    low=candidate("low",gain=.1)
    ranked=rank_acquisition_candidates((low,high))
    assert ranked[0].url.endswith("/high")
    assert ranked[0].score>ranked[1].score
    assert ranked==rank_acquisition_candidates((high,low))


def test_17_canonical_url_dedupe_and_tracking_removal():
    cases=(
        AcquisitionCandidate("https://example.org/a?utm_campaign=promo",
                             .9,.9,.9,200),
        AcquisitionCandidate("https://example.org/a",.2,.2,.2,200),
    )
    result=rank_acquisition_candidates(cases)
    assert len(result)==1
    assert result[0].url=="https://example.org/a"
    assert result[0].score>0


def test_17_policy_denial_and_byte_cap_are_fail_closed():
    scope=CrawlPolicy(allowed_hosts=frozenset({"example.org"}),max_response_bytes=500)
    selected=rank_acquisition_candidates((
        candidate("too-big",bytes=1000),
        candidate("external",host="unapproved.org",bytes=100),
        candidate("allowed",bytes=100),
    ),policy=scope)
    assert sum(item.admitted for item in selected)==1
    assert selected[0].url.endswith("/allowed")
    assert {p.reason for p in selected if not p.admitted}=={
        "policy_denied","response_size_budget"
    }


def test_17_nonfinite_scores_and_invalid_bytes_are_rejected():
    with pytest.raises(ValueError,match="information gain"):
        rank_acquisition_candidates((candidate("a",gain=float("nan")),))
    with pytest.raises(ValueError,match="expected bytes"):
        rank_acquisition_candidates((candidate("a",bytes=-1),))


def test_18_round_robin_prevents_one_host_monopolizing_dispatch():
    inputs=tuple(candidate(str(i),host="alpha.example") for i in range(5))+(
        candidate("only",host="beta.example"),
    )
    ranked=rank_acquisition_candidates(inputs)
    selected=allocate_host_dispatches(ranked,now=100,
                                      max_dispatch=5,max_per_host=4,
                                      host_delay=2)
    assert len(selected)==5
    assert selected[0].host=="alpha.example"
    assert selected[1].host=="beta.example"
    assert [x.rank for x in selected]==[1,2,3,4,5]
    alpha=[x for x in selected if x.host=="alpha.example"]
    assert [x.ready_at for x in alpha]==[100,102,104,106]


def test_18_existing_host_cooldown_and_per_host_caps_applied():
    items=rank_acquisition_candidates(tuple(candidate(str(i)) for i in range(10)))
    plan=allocate_host_dispatches(
        items, now=10,host_ready_at={"example.org":40},
        host_delay=3,max_per_host=2,max_dispatch=10,
    )
    assert len(plan)==2
    assert [x.ready_at for x in plan]==[40,43]


def test_18_invalid_schedule_and_duplicate_urls_not_accepted():
    ranked=rank_acquisition_candidates((candidate("same"),))
    plan=allocate_host_dispatches(ranked+ranked,now=10)
    assert len(plan)==1
    with pytest.raises(ValueError,match="host-ready"):
        allocate_host_dispatches(ranked,now=10,
                                  host_ready_at={"example.org":float("inf")})


def test_19_high_volatility_sources_are_due_sooner():
    recent=100
    volatile=RecrawlSource("volatile","https://one.example/a",
                           recent, recent,.99,1)
    stable=RecrawlSource("stable","https://two.example/a",
                         recent,recent,.01,.1,15)
    plan=plan_adaptive_recrawls((stable,volatile),now=100000,
                                 minimum_interval=3600)
    lookup={x.source_id:x for x in plan}
    assert lookup["volatile"].revisit_interval < lookup["stable"].revisit_interval
    assert lookup["volatile"].next_due < lookup["stable"].next_due
    assert plan==plan_adaptive_recrawls((volatile,stable),now=100000,
                                      minimum_interval=3600)


def test_19_stale_sources_become_due_without_external_fetch():
    entry=RecrawlSource("alpha","https://alpha.example/study",
                        100,50,.7,.8)
    not_yet=plan_adaptive_recrawls((entry,),now=101)[0]
    later=plan_adaptive_recrawls((entry,),now=100000)[0]
    assert not not_yet.due
    assert later.due
    assert later.urgency>0


def test_19_invalid_time_and_duplicate_source_fails_closed():
    entry=RecrawlSource("alpha","https://alpha.example/study",100,50,.5,.5)
    with pytest.raises(ValueError,match="duplicate"):
        plan_adaptive_recrawls((entry,entry),now=200)
    with pytest.raises(ValueError,match="timestamp"):
        plan_adaptive_recrawls((replace(entry,last_fetched=300),),now=200)


def test_20_adequate_evidence_stops_and_routes_to_human_review():
    report=assurance()
    assert report.candidate_for_review
    result=decide_mission_stop(report,remaining_requests=20,
                               novelty_scores=(.5,.2,.1))
    assert result.should_stop
    assert result.review_required
    assert result.recommended_next==("submit_for_human_review",)
    assert len(result.fingerprint)==64


def test_20_contradictions_keep_research_open_when_budget_remains():
    report=assurance(conflicting=True)
    decision=decide_mission_stop(
        report,remaining_requests=100,
        novelty_scores=(.2,.1,.09),
    )
    assert not decision.should_stop
    assert "contradiction_review" in decision.unmet_goals
    assert decision.recommended_next==("target_contradictions",)


def test_20_exhausted_budget_stops_fetch_but_not_review():
    report=assurance(conflicting=True)
    decision=decide_mission_stop(report,remaining_requests=0,
                                 novelty_scores=(.2,.1,.01))
    assert decision.should_stop
    assert decision.review_required
    assert "budget_exhausted_with_unresolved_goals" in decision.unmet_goals
    assert decision.recommended_next==("increase_authorized_budget_or_escalate",)


def test_20_corrupted_or_nonfinite_novelty_is_rejected():
    with pytest.raises(ValueError,match="novelty"):
        decide_mission_stop(assurance(),remaining_requests=10,
                            novelty_scores=(.1,float("inf")))


def test_20_reports_are_order_stable_and_digest_binds_budget():
    report=assurance()
    first=decide_mission_stop(report,remaining_requests=20,
                              novelty_scores=(.2,.1))
    same=decide_mission_stop(report,remaining_requests=20,
                             novelty_scores=(.2,.1))
    changed=decide_mission_stop(report,remaining_requests=19,
                                novelty_scores=(.2,.1))
    assert first==same
    assert first.fingerprint != changed.fingerprint
