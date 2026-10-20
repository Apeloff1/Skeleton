"""Real governed Jeeves Studio interactions with durable expedition state."""
import pytest

from skeleton.jeeves.agent.tools import ToolDenied,ToolRegistry
from skeleton.jeeves.game_studio_tools import (
    StudioCommand, studio_command_catalog,register_studio_tools,
)
from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_save_store import ExpeditionSaveStore
from skeleton.jeeves.game_frontier_expedition_studio_tools import (
    OPERATIONS, expedition_studio_handlers,
)
from tests.test_game_frontier_expedition_native_runner import world,traveler


def host(tmp_path):
    w,p=world(),traveler()
    store=ExpeditionSaveStore(tmp_path/"game.sqlite")
    return w,p,store,expedition_studio_handlers(
        {w.project_id:(w,p)},save_store=store,export_root=tmp_path)


def request(name,project="native_expedition",**payload):
    return StudioCommand(name,project,payload)


def test_seven_host_owned_studio_commands_are_real_capabilities(tmp_path):
    w,p,store,handlers=host(tmp_path)
    assert set(handlers)==set(OPERATIONS)
    catalog=studio_command_catalog()
    assert set(OPERATIONS).issubset(
        set(catalog["read_operations"]+catalog["write_operations"]))
    read=handlers["expedition.inspect"](
        request("expedition.inspect"),None)
    assert read["world_digest"]==w.digest
    assert read["session"] is None
    route=handlers["expedition.preview"](
        request("expedition.preview"),None)
    assert route["won"]
    assert route["route"]
    assert not route["native_run_claimed"]
    store.close()


def test_governed_player_interaction_updates_actual_persisted_state(tmp_path):
    w,p,store,handlers=host(tmp_path)
    started=handlers["expedition.start"](
        request("expedition.start",run_id="run1"),None)
    assert started["generation"]==1
    moved=handlers["expedition.action"](
        request("expedition.action",run_id="run1",
                expected_generation=1,kind="travel",edge_id="launch"),None)
    assert moved["generation"]==2
    assert moved["state"]["position"]=="cliff"
    assert "discovered:cliff" in moved["events"]
    loaded=handlers["expedition.inspect"](
        request("expedition.inspect",run_id="run1"),None)
    assert loaded["session"]["generation"]==2
    assert loaded["session"]["state"]["position"]=="cliff"
    with pytest.raises(ExpeditionError,match="current checkpoint"):
        handlers["expedition.action"](
            request("expedition.action",run_id="run1",
                    expected_generation=1,kind="travel",edge_id="bridge"),None)
    assert store.load("native_expedition:run1",w,p).generation==2
    store.close()


def test_actual_native_project_export_is_safely_scoped(tmp_path):
    w,p,store,handlers=host(tmp_path)
    outcome=handlers["expedition.export"](
        request("expedition.export",folder="new_original_game"),None)
    assert outcome["file_count"]>=6
    assert len(outcome["receipt"])==64
    assert (tmp_path/"new_original_game"/"project.godot").is_file()
    assert (tmp_path/"new_original_game"/"game/frontier/expedition.gd").is_file()
    with pytest.raises(ExpeditionError,match="exists"):
        handlers["expedition.export"](
            request("expedition.export",folder="new_original_game"),None)
    with pytest.raises(ExpeditionError,match="safe original"):
        handlers["expedition.export"](
            request("expedition.export",folder="../bad"),None)
    assert not (tmp_path.parent/"bad").exists()
    store.close()


def test_qa_and_release_reads_never_claim_independent_native_signoff(tmp_path):
    _,_,store,handlers=host(tmp_path)
    scenario=handlers["expedition.qa"](
        request("expedition.qa",seeds=[11],islands=5),None)
    assert scenario["scenarios_executed"]==7
    assert scenario["routes_executed"]>0
    assert scenario["native_runs"]==0
    release=handlers["expedition.release.inspect"](
        request("expedition.release.inspect"),None)
    assert release["status"]=="blocked"
    assert release["axes"]["independent_replay"]
    assert not release["production_release_approved"]
    assert "native_validation" in release["blocked_axes"]
    store.close()


def test_studio_registry_denies_mutation_without_exact_host_authorizer(tmp_path):
    w,p,store,handlers=host(tmp_path)
    registry=ToolRegistry()
    registered=register_studio_tools(
        registry,handlers=handlers,authorize=lambda cmd,context:False)
    assert set(registered)=={"studio_inspect","studio_execute"}
    mutator=registry.get("studio_execute")
    assert mutator is not None
    with pytest.raises(ToolDenied,match="did not authorize"):
        mutator.handler({
            "operation":"expedition.start","project_id":w.project_id,
            "payload":{"run_id":"denied"},
        },None)
    assert store.load("native_expedition:denied",w,p) is None
    store.close()


def test_studio_registry_authorized_exact_execution_returns_source_receipts(tmp_path):
    w,p,store,handlers=host(tmp_path)
    registry=ToolRegistry()
    register_studio_tools(
        registry,handlers=handlers,
        authorize=lambda command,ctx: command.operation=="expedition.preview",
    )
    reader=registry.get("studio_inspect")
    proof=reader.handler({
        "operation":"expedition.preview","project_id":w.project_id,
        "payload":{},
    },None)
    assert proof["operation"]=="expedition.preview"
    assert proof["result"]["won"]
    assert len(proof["result_digest"])==64
    store.close()


def test_unknown_project_and_missing_session_never_spawn_fake_progress(tmp_path):
    w,p,store,handlers=host(tmp_path)
    with pytest.raises(ExpeditionError,match="unknown"):
        handlers["expedition.inspect"](
            request("expedition.inspect",project="foreign"),None)
    with pytest.raises(ExpeditionError,match="before durable"):
        handlers["expedition.action"](
            request("expedition.action",run_id="missing",kind="travel",
                    edge_id="launch",expected_generation=1),None)
    assert store.history("native_expedition:missing")==()
    store.close()
