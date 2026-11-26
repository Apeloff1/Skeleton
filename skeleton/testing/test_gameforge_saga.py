"""Actual recovered exploration, convoy, narrative and persistent saga integration."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sqlite3

import pytest

from skeleton.app.gameforge_saga import (
    REQUEST_SCHEMA, build_saga, play_saga, resume_saga, verify_saga,
)
from skeleton.app.gameforge_saga_author import (
    SCHEMA as AUTHOR_SCHEMA, author_saga, verify_authoring,
)
from skeleton.app.gameforge_saga_board import (
    board, compare, episode_evidence, recover, selected_action, turn, verify_derived,
)
from skeleton.app.gameforge_saga_cli import main
from skeleton.app.gameforge_saga_store import SagaStore
from skeleton.app.gameforge_expedition_store import ExpeditionStore
from skeleton.app.gameforge_campaign_store import CampaignStoreError, RevisionConflict
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay import harbor_crafting_expedition as exploration
from skeleton.game.gameplay.harbor_crafting_expedition_ui import (
    parse_command, scripted_expedition_commands,
)
from skeleton.game.gameplay.harbor_crafting_convoy_solver import solve_convoy
from skeleton.game.gameplay.harbor_crafting_convoy_contracts import verify_convoy_contract_report
from skeleton.testing.test_gameforge_expedition import request as expedition_request


def fixture(suffix=""):
    path = Path(harbor.__file__).parent / "fixtures" / ("harbor_lantern_quay" + suffix + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def authored():
    world = fixture()
    survey = {"survey": fixture("_survey"), "weather": fixture("_weather"),
              "dialogue": fixture("_dialogue"), "required_ending": "beacon"}
    tactical = {"convoy": fixture("_convoy"), "contracts": fixture("_convoy_contracts"),
                "choice": "relief"}
    exploration_actions = [parse_command(line) for line in scripted_expedition_commands().splitlines()]
    convoy_actions = solve_convoy(world, tactical["convoy"])["actions"]
    return {"schema": REQUEST_SCHEMA, "expedition": expedition_request(),
            "episodes": [
                {"objective": "s1", "kind": "survey_expedition", "source": world,
                 "rules": survey, "witness": exploration_actions},
                {"objective": "s2", "kind": "convoy_contract", "source": world,
                 "rules": tactical, "witness": convoy_actions},
            ]}


@pytest.fixture(scope="module")
def design(authored):
    return build_saga(authored)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("ascii")


def reseal(value, key):
    value[key] = hashlib.sha256(encoded({k: v for k, v in value.items() if k != key})).hexdigest()


def invoke(command, value, path=None):
    args = [command] + (["--database", str(path)] if path is not None else [])
    output, error = io.StringIO(), io.StringIO()
    code = main(args, stdin=io.BytesIO(encoded(value)), stdout=output, stderr=error)
    return code, json.loads(output.getvalue()) if output.getvalue() else None, error.getvalue()


def first_episode(actions, oid):
    return next(i for i, action in enumerate(actions)
                if action["type"] == "episode" and action["objective"] == oid)


def resolve_index(actions, oid):
    return next(i for i, action in enumerate(actions)
                if action["type"] == "resolve" and action["objective"] == oid)


def test_both_recovered_owners_gate_actual_generated_progress(authored, design):
    assert verify_saga(authored, design)
    witness = design["witness"]
    assert first_episode(witness, "s1") < resolve_index(witness, "s1")
    assert first_episode(witness, "s2") < resolve_index(witness, "s2")
    complete = play_saga(authored, witness)
    assert complete["state"] == design["witness_state"]
    assert complete["state"]["status"] == "completed"
    assert len(complete["state"]["earned_rewards"]) == 4
    explored = complete["state"]["episodes"]["s1"]
    escorted = complete["state"]["episodes"]["s2"]
    assert explored["gate_satisfied"] and explored["delivery_permit"]
    assert not explored["required_sites_remaining"]
    assert explored["state"]["ending"] == "beacon"
    assert escorted["gate_satisfied"] and escorted["bounty"] == 7
    assert escorted["hull"] >= 3
    assert not escorted["required_contracts_remaining"]
    assert escorted["credits"] == 0 and escorted["reputation"] > 0
    assert complete["state"]["legal_actions"] == []
    assert not complete["release_qualified"] and not complete["native_qualified"]


def test_no_design_or_local_witness_can_grant_genesis_progress(authored, design):
    initial = play_saga(authored, [])
    assert initial["state"]["earned_rewards"] == []
    assert initial["actions"] == []
    assert all(ep["state"]["tick"] == 0 and not ep["gate_satisfied"]
               for ep in initial["state"]["episodes"].values())
    assert "?" in "".join(initial["state"]["episodes"]["s1"]["grid"])
    assert all(not ep["terminal"] for ep in initial["state"]["episodes"].values())
    assert not any(a["type"] == "episode" for a in initial["state"]["legal_actions"])
    with pytest.raises(ValueError):
        play_saga(authored, [design["witness"][first_episode(design["witness"], "s1")]])


def test_advanced_game_cannot_be_skipped_and_board_fences_actions(authored, design):
    actions = design["witness"]
    start = first_episode(actions, "s1")
    end = resolve_index(actions, "s1")
    ready = play_saga(authored, actions[:start])
    assert ready["state"]["blockers"][0]["reason"] == "advanced_episode_in_progress"
    assert actions[end] not in ready["state"]["legal_actions"]
    with pytest.raises(ValueError, match="outcome"):
        play_saga(authored, actions[:start] + [actions[end]])
    current = board(authored, ready)
    assert current["expedition_view"]["legal_actions"] == current["legal_actions"]
    assert current["expedition_view"]["campaign_view"]["legal_actions"] == current["legal_actions"]
    index = current["legal_actions"].index(actions[start])
    updated = turn(authored, ready, current["board_digest"], index)
    assert updated["receipt"]["actions"] == actions[:start + 1]
    assert updated["receipt"]["state"]["episodes"]["s1"]["state"]["tick"] == 1
    with pytest.raises(ValueError, match="changed"):
        selected_action(authored, updated["receipt"], current["board_digest"], index)
    assert verify_derived(authored, ready, current, kind="board")


def test_owner_projection_reports_real_weather_permits_and_earned_contracts(authored, design):
    complete = play_saga(authored, design["witness"])
    evidence = episode_evidence(authored, complete, "s1")
    state = exploration.verify_expedition(evidence["report"], require_complete=True)
    assert state["ending"] == "beacon"
    assert evidence["summary"] == complete["state"]["episodes"]["s1"]
    assert verify_derived(authored, complete, evidence, kind="evidence")
    escort = episode_evidence(authored, complete, "s2")
    status = verify_convoy_contract_report(escort["report"], require_all=True)
    assert status["complete"] and status["choice"] == "relief"
    assert status["points"] == escort["summary"]["points"]
    assert verify_derived(authored, complete, escort, kind="evidence")
    forged = deepcopy(escort)
    forged["report"]["credits"] = 999
    reseal(forged, "evidence_digest")
    assert not verify_derived(authored, complete, forged, kind="evidence")


def test_local_choice_and_convoy_attack_reject_illegal_actions(authored, design):
    actions = design["witness"]
    start = first_episode(actions, "s1")
    prefix = actions[:start]
    with pytest.raises(ValueError):
        play_saga(authored, prefix + [{"type": "episode", "objective": "s1",
                                      "action": {"op": "deliver"}}])
    with pytest.raises(ValueError):
        play_saga(authored, prefix + [{"type": "episode", "objective": "s1",
                                      "action": {"op": "talk", "node": "merchant_intro", "choice": "permit"}}])
    convoy_start = first_episode(actions, "s2")
    with pytest.raises(ValueError):
        play_saga(authored, actions[:convoy_start] + [{"type": "episode", "objective": "s2",
                                                     "action": {"op": "strike"}}])


def test_recovery_produces_actual_combined_suffix_and_comparison(authored, design):
    actions = design["witness"]
    start = first_episode(actions, "s1")
    partial = play_saga(authored, actions[:start + 1])
    result = recover(authored, partial)
    assert result["status"] == "completion_witness"
    assert result["advanced_strategies"]["s1"]["strategy"] == "verified_witness_suffix"
    assert verify_derived(authored, partial, result, kind="recovery")
    complete = resume_saga(authored, partial, result["additional"])
    assert complete["state"]["status"] == "completed"
    assert complete["session_digest"] == result["completion_digest"]
    difference = compare(authored, partial, complete)
    assert difference["common_prefix"] == len(partial["actions"])
    assert difference["advanced_outcomes"]["s1"]["right_gate"]
    assert difference["advanced_outcomes"]["s2"]["bounty_delta"] == 7
    assert verify_derived(authored, partial, difference, kind="comparison", other=complete)
    forged = deepcopy(result)
    forged["additional"] = []
    reseal(forged, "recovery_digest")
    assert not verify_derived(authored, partial, forged, kind="recovery")


def test_saga_store_reopens_forks_and_restores_without_namespace_downgrade(authored, design, tmp_path):
    path = tmp_path / "saga.sqlite"
    first = design["witness"][:1]
    with sqlite3.connect(path) as db:
        store = SagaStore(db)
        zero = store.create("slot", authored, "init")
        stage = store.append("slot", authored, 0, "first", first)
        assert store.append("slot", authored, 0, "first", first) == stage
        with pytest.raises(RevisionConflict):
            store.append("slot", authored, 0, "stale", first)
        fork = store.fork("slot", authored, 0, zero["receipt"]["session_digest"], "branch")
        assert fork["child"]["receipt"] == zero["receipt"]
        base = ExpeditionStore(db)
        ordinary = base.create("slot", authored["expedition"], "init")
        assert ordinary["receipt"]["schema"] != stage["receipt"]["schema"]
    with sqlite3.connect(path) as db:
        store = SagaStore(db, initialize=False)
        assert store.read("slot", authored) == stage
        archive = store.snapshot("slot", authored)
        assert archive["namespace"] == "saga"
        restored = store.restore("restored", authored, archive)
        assert restored["receipt"] == stage["receipt"]
        with pytest.raises(CampaignStoreError):
            ExpeditionStore(db, initialize=False).restore("wrong", authored["expedition"], archive)
        assert store.read("branch", authored)["receipt"] == zero["receipt"]


def test_authoring_reuses_package_and_solver_without_preearned_progress(authored):
    request = {"schema": AUTHOR_SCHEMA, "expedition": authored["expedition"],
               "bindings": deepcopy(authored["episodes"])}
    survey, tactical = request["bindings"]
    rules = survey["rules"]
    survey["package"] = exploration.build_expedition_package(
        survey["source"]["id"], survey["source"], rules["survey"], rules["weather"], rules["dialogue"])
    tactical.pop("witness")
    composition = author_saga(request)
    assert composition["owner_custody"][0]["package_digest"] == survey["package"]["package_digest"]
    assert composition["owner_custody"][1]["witness_origin"] == "canonical_solver"
    assert verify_authoring(request, composition)
    genesis = play_saga(composition["request"], [])
    assert genesis["session_digest"] == composition["genesis_digest"]
    assert genesis["state"]["earned_rewards"] == []
    assert not genesis["state"]["episodes"]["s2"]["gate_satisfied"]


def test_source_and_owner_admission_is_fail_closed(authored, design):
    for change in ("owner", "duplicate", "witness", "objective", "world"):
        bad = deepcopy(authored)
        if change == "owner":
            bad["episodes"][0]["kind"] = "dynamic_module"
        elif change == "duplicate":
            bad["episodes"][1]["objective"] = bad["episodes"][0]["objective"]
        elif change == "witness":
            bad["episodes"][0]["witness"] = [{"op": "wait"}]
        elif change == "objective":
            bad["episodes"][0]["objective"] = "unknown"
        else:
            bad["episodes"][0]["source"]["id"] = "other"
        assert invoke("build", bad)[0] == 1
        assert not verify_saga(bad, design)


def test_saga_installed_cli_routes_authority_and_persistent_board(authored, tmp_path):
    path = tmp_path / "saga.sqlite"
    slot = {"request": authored, "slot": "play"}
    code, zero, _ = invoke("create-slot", {**slot, "operation": "init"}, path)
    assert code == 0 and zero["revision"] == 0
    current = invoke("board-slot", slot, path)[1]["board"]
    assert current["checkpoint_digest"] == zero["receipt"]["session_digest"]
    index = current["legal_actions"].index({"type": "dialogue", "npc": "keeper", "choice": "listen"})
    operation = {**slot, "operation": "turn", "expected_revision": 0,
                 "board_digest": current["board_digest"], "index": index}
    code, stage, _ = invoke("turn-slot", operation, path)
    assert code == 0 and stage["revision"] == 1
    assert invoke("turn-slot", operation, path)[1] == stage
    assert invoke("turn-slot", {**operation, "operation": "stale"}, path)[0] == 1
    archive = invoke("snapshot-slot", slot, path)[1]
    assert invoke("restore-slot", {**slot, "slot": "restored", "archive": archive}, path)[0] == 0
    assert invoke("verify-play", {"request": authored, "receipt": stage["receipt"]})[0] == 0


def test_interactive_player_commits_only_selected_actions_and_reopens(authored, tmp_path):
    from skeleton.app.gameforge_saga_live import play_live
    path = tmp_path / "live.sqlite"
    with sqlite3.connect(path) as db:
        store = SagaStore(db)
        zero = store.create("slot", authored, "init")
        current = board(authored, zero["receipt"])
        action = {"type": "dialogue", "npc": "keeper", "choice": "listen"}
        selected = current["legal_actions"].index(action) + 1
        outgoing = io.StringIO()
        commands = ("not-a-command\n9999\nhint\n" + str(selected) + "\nquit\n").encode("ascii")
        assert play_live(store, authored, "slot", io.BytesIO(commands), outgoing) == 0
        text = outgoing.getvalue()
        assert "REJECTED unknown player command" in text
        assert "REJECTED selection outside current menu" in text
        assert "HINT " in text and "ACCEPTED " in text and "CHECKPOINT " in text
        assert store.read("slot", authored)["receipt"]["actions"] == [action]
    with sqlite3.connect(path) as db:
        store = SagaStore(db, initialize=False)
        before = store.read("slot", authored)
        out = io.StringIO()
        assert play_live(store, authored, "slot", io.BytesIO(b"status\nquit\n"), out) == 0
        assert store.read("slot", authored) == before
        assert play_live(store, authored, "slot", io.BytesIO(b"x"*257+b"\n1\n"), out) == 2
        assert store.read("slot", authored) == before


def test_live_player_cli_reopens_same_independent_source(authored, tmp_path):
    from skeleton.app.gameforge_saga_live import main as live_main
    source = tmp_path / "source.json"
    source.write_bytes(encoded(authored))
    database = tmp_path / "saga.sqlite"
    args = ["--source", str(source), "--database", str(database), "--slot", "live"]
    output, error = io.StringIO(), io.StringIO()
    assert live_main([*args, "--create"], stdin=io.BytesIO(b"quit\n"), stdout=output, stderr=error) == 0
    assert live_main(args, stdin=io.BytesIO(b"quit\n"), stdout=output, stderr=error) == 0
    assert "CHECKPOINT " in output.getvalue()
