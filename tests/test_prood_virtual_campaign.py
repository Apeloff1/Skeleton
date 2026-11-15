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


@pytest.mark.asyncio
async def test_campaign_save_cas_replay_and_restart(campaign_factory,tmp_path):
    from skeleton.prood.campaign_save import CampaignSaveStore,SaveConflict,SaveIntegrityError
    campaign=campaign_factory(CampaignScale(2,3,9))
    path=tmp_path/"campaign.sqlite"
    db=sqlite3.connect(path)
    store=CampaignSaveStore(db,campaign=campaign,scope="player",key=b"s"*32)
    initial=store.create("slot")
    first=store.step("slot",Action("resolve","aid"),expected_head=initial.head,request_id="first")
    assert first.saved.revision==1
    duplicate=store.step("slot",Action("resolve","aid"),expected_head=initial.head,request_id="first")
    assert duplicate.replayed and duplicate.saved==first.saved
    with pytest.raises(SaveConflict):
        store.step("slot",Action("resolve","force"),expected_head=initial.head,request_id="first")
    with pytest.raises(SaveConflict):
        store.step("slot",Action("advance"),expected_head=initial.head,request_id="stale")
    second=store.step("slot",Action("advance"),expected_head=first.saved.head,request_id="next")
    assert second.saved.state.ordinal==2
    store.close()
    db.close()
    db=sqlite3.connect(path)
    reopened=CampaignSaveStore(db,campaign=campaign,scope="player",key=b"s"*32,initialize=False)
    assert reopened.audit("slot",trusted_head=second.saved.head)==second.saved
    with pytest.raises(SaveConflict):
        reopened.audit("slot",trusted_head=initial.head)
    db.execute("DELETE FROM prood_campaign_event_v1 WHERE sequence=1")
    db.commit()
    with pytest.raises(SaveIntegrityError):
        reopened.audit("slot")
    db.close()


@pytest.mark.asyncio
async def test_campaign_save_scope_and_capacity(campaign_factory,tmp_path):
    from skeleton.prood.campaign_save import CampaignSaveStore,SaveCapacity
    campaign=campaign_factory(CampaignScale(1,1,3))
    path=tmp_path/"capacity.sqlite"
    connection=sqlite3.connect(path)
    store=CampaignSaveStore(connection,campaign=campaign,scope="first",key=b"s"*32,max_events=1)
    first=store.create("slot")
    saved=store.step("slot",Action("resolve","aid"),expected_head=first.head,request_id="one").saved
    with pytest.raises(SaveCapacity):
        store.step("slot",Action("advance"),expected_head=saved.head,request_id="two")
    assert store.audit("slot")==saved
    second=sqlite3.connect(path)
    foreign=CampaignSaveStore(second,campaign=campaign,scope="second",key=b"s"*32)
    with pytest.raises(KeyError):
        foreign.audit("slot")
    second.close()
    connection.close()


@pytest.mark.asyncio
async def test_private_save_reopen_requires_existing_schema(campaign_factory,tmp_path):
    import os
    if os.name!="posix":
        pytest.skip("canonical private SQLite POSIX custody")
    from skeleton.app.offline_design_runtime import open_campaign_save
    campaign=campaign_factory(CampaignScale(1,1,3))
    tmp_path.chmod(0o700)
    args=dict(campaign=campaign,scope="player",key=b"s"*32)
    with pytest.raises(OSError):
        with open_campaign_save(tmp_path,create=False,**args):
            pass
    with open_campaign_save(tmp_path,create=True,**args) as saves:
        created=saves.create("slot")
    with open_campaign_save(tmp_path,create=False,**args) as saves:
        assert saves.audit("slot",trusted_head=created.head)==created
