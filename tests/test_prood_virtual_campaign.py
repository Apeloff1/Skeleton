"""Virtual campaign scale, bounded action semantics and deterministic replay."""
from dataclasses import replace
import sqlite3

import pytest
import pytest_asyncio

from skeleton.frontier.durable_work import DurableWorkJournal
from skeleton.frontier.worker_results import WorkerResultStore
from skeleton.prood.campaign_world import CampaignScale,campaign_from_results
from skeleton.prood.campaign_play import Action,apply,available_actions,genesis,initial_state,replay,transition
from skeleton.prood.design_campaign import admit_design,design_supervisor
from skeleton.prood.design_contract import DesignRequest


class Policy:
    def allow(self,work):
        return True


@pytest_asyncio.fixture
async def campaign_factory(tmp_path):
    db=sqlite3.connect(tmp_path/"work.sqlite")
    rd=sqlite3.connect(tmp_path/"result.sqlite")
    journal=DurableWorkJournal(db,scope="campaign",custody_key=b"w"*32)
    results=WorkerResultStore(rd,scope="campaign",key=b"r"*32)
    request=DesignRequest("campaign","Original RPG dungeon",seed=16,variants=1)
    admit_design(journal,request)
    supervisor=design_supervisor(journal,results,request,admission=Policy(),owner="operator")
    for _ in range(6):
        report=await supervisor.dispatch()
        assert len(report.completed)==1 and not report.uncertain
    def create(scale=CampaignScale()):
        return campaign_from_results(journal,results,request,scale=scale)
    try:
        yield create
    finally:
        db.close()
        rd.close()


@pytest.mark.asyncio
async def test_full_scale_addressability_and_adjacent_regions(campaign_factory):
    campaign=campaign_factory()
    assert campaign.scale==CampaignScale(100,1000,9999)
    assert len(campaign.route)<=46
    chapters,acts=set(),set()
    prior=None
    for ordinal in range(1,10000):
        scene=campaign.scene(ordinal)
        address=scene.address
        assert campaign.ordinal(chapter=address.chapter,act=address.chapter_act,scene=address.scene_in_act)==ordinal
        chapters.add(address.chapter)
        acts.add(address.act)
        if prior is not None:
            assert scene.region in prior.paths
        prior=scene
    assert len(chapters)==100 and len(acts)==1000
    assert prior.campaign_end and prior.chapter_end
    assert len(campaign.page(9990,limit=256))==10


@pytest.mark.asyncio
async def test_exploration_rest_and_resolution_are_bounded(campaign_factory):
    campaign=campaign_factory(CampaignScale(2,4,12))
    state=initial_state(campaign)
    scene=campaign.scene(1)
    explored=apply(campaign,state,Action("explore",scene.paths[0]))
    assert explored.region in scene.paths and explored.knowledge==3
    assert available_actions(campaign,explored)==(Action("return"),)
    returned=apply(campaign,explored,Action("return"))
    assert not any(a.kind=="explore" for a in available_actions(campaign,returned))
    rested=apply(campaign,returned,Action("rest"))
    assert Action("rest") not in available_actions(campaign,rested)
    resolved=apply(campaign,rested,Action("resolve","aid"))
    assert resolved.reputation==3 and resolved.resolved
    with pytest.raises(ValueError):
        apply(campaign,resolved,Action("resolve","aid"))
    moved=apply(campaign,resolved,Action("advance"))
    assert moved.ordinal==2 and not moved.resolved and not moved.explored and not moved.rested


@pytest.mark.asyncio
async def test_earned_guardian_ending_and_replay(campaign_factory):
    campaign=campaign_factory(CampaignScale(2,3,8))
    state=initial_state(campaign)
    head=genesis(campaign)
    events=[]
    while not state.ending:
        action=Action("advance") if state.resolved else Action("resolve","aid")
        state,event=transition(campaign,state,action,previous=head)
        events.append(event)
        head=event.event_digest
    assert state.ending=="guardian" and state.ordinal==8 and state.turn==16
    assert replay(campaign,events,expected_head=head)==(state,head)
    with pytest.raises(ValueError,match="trusted head"):
        replay(campaign,events[:-1],expected_head=head)
    with pytest.raises(ValueError,match="deterministic replay"):
        replay(campaign,[replace(events[0],after="a"*64),*events[1:]])
    assert not available_actions(campaign,state)
