"""Real conductor/quest integration and player-event custody regressions."""
from collections import deque
from copy import deepcopy
import hashlib
import io
import json
import subprocess
import sys

import pytest

from skeleton.app.gameforge_quest_bridge import (
    GRAPH_SEMANTICS, REQUEST_SCHEMA, build_design, play, resume,
    verify_design, verify_session,
)
from skeleton.app.gameforge_quest_cli import main
from skeleton.app.original_quest_cli import MAX_BYTES, QuestRequestError, _encode
from skeleton.gameforge.conductor import ConductorConfig, GameForgeConductor
from skeleton.gameforge.plans import STEPS


def source():
    return {
        "schema": REQUEST_SCHEMA,
        "vision": {
            "title": "Lantern Harbor", "pitch": "Discover lost lights in a coastal town",
            "genre": "adventure", "pillars": ["exploration", "story"],
            "era": "HOUSE_ERA", "target_minutes": 12,
        },
        "config": {"budget_bytes": 200_000, "regions": 8, "target": "bundle"},
        "quest": {
            "packs": [
                {"id": "movement", "provides": ["movement"]},
                {"id": "quest", "provides": ["quests"], "requires": ["movement"]},
            ],
            "pack_ids": ["quest", "movement"],
            "policy": {
                "allowed_reward_kinds": ["gold"], "max_reward_per_step": 3,
                "max_total_reward": 48,
            },
            "seed": 31, "quest_length": 8,
            "npcs": {"ranger": "r00", "keeper": "r03"},
        },
    }


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      ensure_ascii=True).encode("ascii")


def rehash(value, field):
    value[field] = hashlib.sha256(encoded({k: v for k, v in value.items() if k != field})).hexdigest()


def invoke(command, value):
    out, err = io.StringIO(), io.StringIO()
    code = main([command], stdin=io.BytesIO(encoded(value)), stdout=out, stderr=err)
    return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()


def travel(edges, start, end):
    queue = deque([(start, [])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        if node == end:
            return path
        for neighbor in edges[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, path + [{"type": "move", "to": neighbor}]))
    raise AssertionError("test fixture is disconnected")


def test_design_uses_actual_conductor_graph_and_artifact_manifest():
    spec = source()
    owner = GameForgeConductor(config=ConductorConfig(**spec["config"])).run(spec["vision"])
    assert owner.ok
    result = build_design(spec)
    assert result["conductor_manifest"] == owner.manifest.to_dict()
    assert result["conductor_manifest"]["steps"] == list(STEPS)
    assert result["placeholder_artifact_bytes"] == sum(map(len, owner.artifacts.values()))
    assert result["graph_semantics"] == GRAPH_SEMANTICS
    world = owner.plans["world"]
    expected = {region.key: set() for region in world.regions}
    for region in world.regions:
        for neighbor in region.neighbors:
            expected[region.key].add(neighbor)
            expected[neighbor].add(region.key)
    assert result["world"]["edges"] == {k: sorted(v) for k, v in expected.items()}
    assert result["world"]["start"] == world.start
    assert result["quest_receipt"]["artifact"]["mechanics"]["slice_id"] == owner.manifest.game_id
    assert result["route_replay"]["status"] == "completed"
    assert result["route_replay"]["resolutions"] == 8
    assert result["route_replay"]["earned_rewards"] == result["quest_receipt"]["artifact"]["proof"]["rewards"]
    assert result["route_replay"]["legal_actions"] == []
    assert result["native_qualified"] is False and result["release_qualified"] is False
    assert result == build_design(deepcopy(spec))
    assert verify_design(spec, result)


@pytest.mark.parametrize("genre", ["adventure", "rpg", "platformer", "puzzle",
                                  "shooter", "strategy", "racing", "sandbox"])
def test_all_archived_genres_feed_the_same_quest_runtime(genre):
    spec = source()
    spec["vision"]["genre"] = genre
    result = build_design(spec)
    assert result["conductor_manifest"]["metadata"]["genre"] == genre
    assert result["route_replay"]["status"] == "completed"


@pytest.mark.parametrize("era", ["HOUSE_ERA", "PIXEL_8BIT", "PIXEL_16BIT", "LOWPOLY_3D"])
def test_era_pins_survive_the_cross_runtime_bridge(era):
    spec = source()
    spec["vision"]["era"] = era
    result = build_design(spec)
    assert result["conductor_manifest"]["era"] == era
    assert all(row["era"] == era for row in result["conductor_manifest"]["receipts"])


def test_design_proof_does_not_auto_complete_a_player_session():
    spec = source()
    design = build_design(spec)
    empty = play(spec, [])
    assert empty["state"]["status"] == "in_progress"
    assert empty["state"]["earned_rewards"] == []
    assert empty["state"]["resolutions"] == 0
    assert empty["state"]["legal_actions"]
    assert verify_session(spec, empty)
    actions = design["route_witness"]
    first_objective = next(i for i, action in enumerate(actions) if action["type"] == "resolve")
    checkpoint = play(spec, actions[:first_objective + 1])
    assert checkpoint["state"]["resolutions"] == 1
    assert len(checkpoint["state"]["earned_rewards"]) == 1
    completed = resume(spec, checkpoint, actions[first_objective + 1:])
    assert completed == play(spec, actions)
    assert completed["state"] == design["route_replay"]
    assert verify_session(spec, completed)
    assert checkpoint["state"]["status"] == "in_progress"
    with pytest.raises(ValueError):
        resume(spec, completed, [{"type": "move", "to": "r00"}])


def test_each_witness_action_is_visible_as_legal_before_execution():
    spec = source()
    result = build_design(spec)
    actions = result["route_witness"]
    for index, next_action in enumerate(actions):
        previous = play(spec, actions[:index])
        assert next_action in previous["state"]["legal_actions"]


def test_wrong_region_wrong_npc_and_out_of_order_objectives_do_not_award():
    spec = source()
    design = build_design(spec)
    world = design["world"]
    steps = design["quest_receipt"]["artifact"]["world_quest"]["quest"]["steps"]
    with pytest.raises(ValueError):
        play(spec, [{"type": "move", "to": "r99"}])
    action = {"type": "resolve", "objective": steps[0]["id"], "npc": "impostor"}
    first_path = travel(world["edges"], world["start"], steps[0]["location"])
    with pytest.raises(ValueError):
        play(spec, first_path + [action])
    second_path = travel(world["edges"], world["start"], steps[1]["location"])
    with pytest.raises(ValueError):
        play(spec, second_path + [{"type": "resolve", "objective": steps[1]["id"],
                                    "npc": steps[1]["npc"]}])
    actual = {"type": "resolve", "objective": steps[0]["id"], "npc": steps[0]["npc"]}
    with pytest.raises(ValueError):
        play(spec, first_path + [actual, actual])
    if first_path:
        with pytest.raises(ValueError):
            play(spec, [actual])
    assert play(spec, [])["state"]["earned_rewards"] == []


def test_checkpoints_are_source_bound_and_rehashed_forgery_does_not_resume():
    spec = source()
    design = build_design(spec)
    first = design["route_witness"][0]
    checkpoint = play(spec, [first])
    corrupt = deepcopy(checkpoint)
    corrupt["state"]["earned_rewards"].append({"kind": "gold", "amount": 999})
    rehash(corrupt, "session_digest")
    assert not verify_session(spec, corrupt)
    with pytest.raises(ValueError):
        resume(spec, corrupt, [design["route_witness"][1]])
    other = deepcopy(spec)
    other["quest"]["seed"] += 1
    assert not verify_session(other, checkpoint)
    with pytest.raises(ValueError):
        resume(other, checkpoint, [design["route_witness"][1]])


def test_design_manifest_and_world_rehash_does_not_grant_authority():
    spec = source()
    design = build_design(spec)
    forged = deepcopy(design)
    forged["world"]["edges"]["r00"].append("r99")
    rehash(forged, "design_digest")
    assert not verify_design(spec, forged)
    forged = deepcopy(design)
    forged["conductor_manifest"]["receipts"][0]["step"] = "world"
    rehash(forged["conductor_manifest"], "manifest_digest")
    rehash(forged, "design_digest")
    assert not verify_design(spec, forged)
    forged = deepcopy(design)
    forged["native_qualified"] = True
    rehash(forged, "design_digest")
    assert not verify_design(spec, forged)


@pytest.mark.parametrize("mutate", [
    lambda d: d["vision"].update(title=False),
    lambda d: d["vision"].update(genre="unknown"),
    lambda d: d["vision"].update(era="UNKNOWN"),
    lambda d: d["vision"].update(target_minutes=True),
    lambda d: d["vision"].update(pillars=["Story", "story"]),
    lambda d: d["config"].update(regions=65),
    lambda d: d["config"].update(budget_bytes=1),
    lambda d: d["config"].update(budget_bytes=10**9),
    lambda d: d["config"].update(target="unsafe"),
    lambda d: d["quest"].update(world={"start": "forged"}),
    lambda d: d["quest"].update(npcs={"ghost": "r99"}),
    lambda d: d["quest"].update(pack_ids=["movement"]),
    lambda d: d["quest"]["policy"].update(max_total_reward=0),
])
def test_invalid_source_never_emits_a_design(mutate):
    spec = source()
    mutate(spec)
    code, data, error = invoke("build", spec)
    assert code == 1 and data is None
    assert error.startswith("gameforge quest rejected:")
    assert "Lantern Harbor" not in error


@pytest.mark.parametrize("actions", [
    [{"type": "move", "to": "r00", "extra": "ignored?"}],
    [{"type": "grant", "amount": 100}],
    [{"type": "resolve", "objective": "s0"}],
    [{"type": "move", "to": True}],
    [None],
    [True] * 8193,
])
def test_invalid_event_shapes_fail_closed(actions):
    assert invoke("play", {"request": source(), "actions": actions})[0] == 1


def test_session_is_detached_from_caller_mutations():
    spec = source()
    design = build_design(spec)
    actions = deepcopy(design["route_witness"][:1])
    session = play(spec, actions)
    actions[0]["type"] = "grant"
    assert session["actions"][0]["type"] != "grant"
    assert verify_session(spec, session)


def test_cli_all_operations_and_real_package_module():
    spec = source()
    code, design, _ = invoke("build", spec)
    assert code == 0
    assert invoke("verify", {"request": spec, "receipt": design})[0] == 0
    code, initial, _ = invoke("play", {"request": spec, "actions": []})
    assert code == 0
    code, completed, _ = invoke("resume", {"request": spec, "receipt": initial,
                                          "additional": design["route_witness"]})
    assert code == 0 and completed["state"]["status"] == "completed"
    assert invoke("verify-play", {"request": spec, "receipt": completed})[0] == 0
    assert invoke("verify-play", {"request": spec, "receipt": design})[0] == 1
    proc = subprocess.run([sys.executable, "-m", "skeleton", "gameforge-quest", "build"],
                          input=encoded(spec), capture_output=True, timeout=60, check=True)
    assert json.loads(proc.stdout) == design


def test_direct_python_input_cannot_amplify_pending_nodes_or_text():
    repeated = "x" * 16_384
    with pytest.raises(QuestRequestError, match="character budget"):
        _encode([repeated] * (MAX_BYTES // len(repeated) + 1))
    with pytest.raises(QuestRequestError, match="pending node budget"):
        _encode([[0] * 10_000] * 11)


def test_only_minimal_cli_dispatch_and_packaging_are_added():
    import skeleton.__main__ as entrypoint
    assert "original-quest" in entrypoint.__doc__
    assert "gameforge-quest" in entrypoint.__doc__
