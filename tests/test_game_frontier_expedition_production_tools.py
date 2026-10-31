"""Jeeves production tool control: source ownership, resumed canon and fail-closed writes."""
from pathlib import Path
import pytest

from skeleton.jeeves.agent.tools import ToolRegistry,ToolDenied
from skeleton.jeeves.game_studio_tools import (
    StudioCommand,studio_command_catalog,register_studio_tools,
)
from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_production_store import ProductionSessionStore
from skeleton.jeeves.game_frontier_expedition_production_tools import (
    READ_OPERATIONS,WRITE_OPERATIONS,production_studio_handlers,
)
from tests.test_game_frontier_production_seven import sources


def host(tmp_path):
    world,player,story,quest=sources()
    store=ProductionSessionStore(tmp_path/"production.sqlite")
    handlers=production_studio_handlers(
        {world.project_id:(world,player,story,quest)},
        store=store,
    )
    return world,player,story,quest,store,handlers


def command(operation,project="seven_more_original_games",**payload):
    return StudioCommand(operation,project,payload)


def test_five_real_production_commands_are_visible_through_studio_catalog(tmp_path):
    w,p,s,q,store,handlers=host(tmp_path)
    catalog=studio_command_catalog()
    assert set(handlers)==set(READ_OPERATIONS+WRITE_OPERATIONS)
    assert set(READ_OPERATIONS).issubset(catalog["read_operations"])
    assert set(WRITE_OPERATIONS).issubset(catalog["write_operations"])
    store.close()


def test_studio_create_choice_travel_and_resume_quest_with_durable_receipts(tmp_path):
    w,p,s,q,store,handlers=host(tmp_path)
    missing=handlers["expedition.production.inspect"](
        command("expedition.production.inspect",run_id="major"),None)
    assert not missing["exists"]
    a=handlers["expedition.production.start"](
        command("expedition.production.start",run_id="major"),None)
    assert a["generation"]==1
    b=handlers["expedition.production.choose"](
        command("expedition.production.choose",run_id="major",
                expected_generation=1,scene_id="departure",choice_id="chart"),None)
    assert b["generation"]==2
    assert b["story_flags"]==["map_promised"]
    assert b["quest_flags"]==["chart_contract"]
    c=handlers["expedition.production.act"](
        command("expedition.production.act",run_id="major",
                expected_generation=2,kind="travel",edge_id="launch_updraft"),None)
    assert c["generation"]==3
    assert c["game"]["position"]==w.waypoints[1].waypoint_id
    progress=handlers["expedition.production.inspect"](
        command("expedition.production.inspect",run_id="major"),None)
    assert progress["exists"]
    assert progress["quest_progress"]["chart_the_islands"]==2
    assert progress["story_choices"]==1
    store.close()
    with ProductionSessionStore(tmp_path/"production.sqlite") as again:
        checkpoint=again.load("seven_more_original_games:major",w,p,s,q)
        assert checkpoint is not None
        assert checkpoint[0]==3
        assert len(checkpoint[1].events)==2


def test_exact_host_authorization_rejects_unapproved_game_mutations(tmp_path):
    w,p,s,q,store,handlers=host(tmp_path)
    registry=ToolRegistry()
    register_studio_tools(
        registry,handlers=handlers,
        authorize=lambda cmd,ctx:False,
    )
    executor=registry.get("studio_execute")
    with pytest.raises(ToolDenied,match="did not authorize"):
        executor.handler({
            "operation":"expedition.production.start",
            "project_id":w.project_id,
            "payload":{"run_id":"blocked"},
        },None)
    assert store.history("seven_more_original_games:blocked")==()
    store.close()


def test_exact_read_tool_reports_no_fake_winner_and_rejects_early_ending(tmp_path):
    w,p,s,q,store,handlers=host(tmp_path)
    handlers["expedition.production.start"](
        command("expedition.production.start",run_id="run1"),None)
    with pytest.raises(ExpeditionError,match="without completing"):
        handlers["expedition.production.ending"](
            command("expedition.production.ending",run_id="run1"),None)
    store.close()


def test_unknown_project_invalid_run_and_stale_generation_fail_closed(tmp_path):
    w,p,s,q,store,handlers=host(tmp_path)
    with pytest.raises(ExpeditionError,match="not owned"):
        handlers["expedition.production.inspect"](
            command("expedition.production.inspect",project="foreign",
                    run_id="run1"),None)
    with pytest.raises(ExpeditionError,match="identity"):
        handlers["expedition.production.start"](
            command("expedition.production.start",run_id="../bad"),None)
    handlers["expedition.production.start"](
        command("expedition.production.start",run_id="valid"),None)
    with pytest.raises(ExpeditionError,match="stale expected generation"):
        handlers["expedition.production.choose"](
            command("expedition.production.choose",run_id="valid",
                    expected_generation=0,scene_id="departure",
                    choice_id="chart"),None)
    assert store.history("seven_more_original_games:valid")[0]["version"]==1
    store.close()
