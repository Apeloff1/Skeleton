"""B023: blueprint-to-ECS adapter and script systems."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.ecs.blueprint import BlueprintAdapterError, build_ecs, normalize_blueprint
from skeleton.ecs.script_system import script_system
from skeleton.simulation.ecs.errors import AccessViolationError, ScriptRuntimeError, ValidationError
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.ticker import SystemFailure, TickScheduler

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = json.loads((ROOT / "frontend/scripts/skeleton-forge/fixtures/compose.json").read_text())


def test_normalize_compose_result_prefers_topology() -> None:
    bp = normalize_blueprint(COMPOSE)
    assert bp.blueprint_id
    assert [n.instance_id for n in bp.nodes][:2] == ["operator", "forge"]
    assert {w.channel for w in bp.wires} >= {"operator.intent", "operator.state"}
    assert bp.fingerprint() == normalize_blueprint(json.loads(json.dumps(COMPOSE))).fingerprint()


def test_normalize_flat_list_and_universal_blueprint() -> None:
    flat = {"components": [{"instance_id": "p", "kind": "player", "feature": "player"}, {"instance_id": "h", "kind": "sink"}],
            "wires": [{"from": ["p", "intent"], "to": ["h", "in"]}]}
    bp = normalize_blueprint(flat)
    assert bp.node("p").config["feature"] == "player"
    from skeleton.forge.universal import Blueprint, Component, Port

    ub = Blueprint("bp-x", "x")
    ub.add_component(Component("p", "player", (Port("intent", "event", "out"),)))
    ub.add_component(Component("h", "sink", (Port("in", "event", "in"),)))
    ub.connect(("p", "intent"), ("h", "in"))
    nb = normalize_blueprint(ub)
    assert nb.blueprint_id == "bp-x" and nb.wires[0].channel == "p.intent"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"components": "nope"},
        {"components": [{"instance_id": "1bad", "kind": "player"}]},
        {"components": [{"instance_id": "a", "kind": "player"}, {"instance_id": "a", "kind": "sink"}]},
        {"components": [{"instance_id": "a", "kind": "player"}], "wires": [{"from": ["a", "x"], "to": ["ghost", "in"]}]},
        {"components": [{"instance_id": "a", "kind": "player"}], "wires": [{"from": ["a"], "to": ["a", "in"]}]},
        {"components": [{"instance_id": f"c{i}", "kind": "sink"} for i in range(300)]},
    ],
)
def test_normalize_rejects_malformed(bad) -> None:
    with pytest.raises(BlueprintAdapterError):
        normalize_blueprint(bad)


def test_build_creates_entities_channels_and_ordered_systems() -> None:
    b = build_ecs(COMPOSE, seed=1)
    assert set(b.entities) == {n.instance_id for n in b.blueprint.nodes}
    assert b.world.get(b.entities["operator"], "node")["kind"] == "player"
    assert "operator.intent" in b.channels
    systems = list(b.systems)
    assert systems.index("bp.operator") < systems.index("bp.collapse")
    assert systems.index("bp.operator") < systems.index("bp.vault")
    m = b.manifest()
    assert m["blueprint_fingerprint"] == b.blueprint.fingerprint()
    b.world.check_integrity()


def test_signals_cross_the_graph_in_one_tick() -> None:
    b = build_ecs(COMPOSE, seed=1)
    b.step(1)
    assert b.component("vault", "vault")["writes"] == 1
    assert b.component("collapse", "clock")["remaining"] == 599


def test_run_is_deterministic_per_seed() -> None:
    d = []
    for seed in (5, 5, 6):
        b = build_ecs(COMPOSE, seed=seed)
        b.step(40)
        d.append(b.world.state_digest)
    assert d[0] == d[1]
    assert d[0] != d[2]


def test_snapshot_rollback_replays_identically() -> None:
    b = build_ecs(COMPOSE, seed=3)
    b.step(5)
    snap = b.world.snapshot()
    b.step(10)
    after = b.world.state_digest
    b.world.restore(snap)
    b.step(10)
    assert b.world.state_digest == after


def test_full_featured_vision_reaches_an_outcome() -> None:
    from skeleton.forge.vision_compose import FEATURES, _plan_wires, detect_features

    features, _ = detect_features("fight hordes, craft gear, heat rises, storm countdown, extract with a butler, stash loot, hud score")
    by_name = {f.name: f for f in FEATURES}
    comps = [{"instance_id": "operator", "kind": "player", "feature": "player"}]
    comps += [{"instance_id": by_name[f].instance_id, "kind": by_name[f].kind, "feature": f} for f in features]
    data = {"components": comps, "wires": [{"from": list(a), "to": list(b)} for a, b in _plan_wires(features)]}
    b = build_ecs(data, seed=11)
    kinds = {n.kind for n in b.blueprint.nodes}
    assert {"player", "enemy_spawner", "collapse", "extract", "jeeves"} <= kinds
    b.step(200)
    assert b.world.get_resource("outcome")["result"] in {"extracted", "collapsed"}
    assert b.component("spawner", "spawner")["spawned"] >= 1
    assert b.component("jeeves", "advisor")["advice"]
    assert any(True for _ in b.world.query("hostile"))


def test_config_overrides_known_fields_only() -> None:
    bp = {"components": [{"instance_id": "c", "kind": "collapse", "config": {"clock": {"remaining": 2, "evil": 1}}}]}
    b = build_ecs(bp)
    assert b.component("c", "clock")["remaining"] == 2
    assert "evil" not in b.component("c", "clock")
    b.step(3)
    assert b.world.get_resource("outcome")["result"] == "collapsed"


def test_unknown_kind_gets_generic_counter() -> None:
    bp = {"components": [{"instance_id": "p", "kind": "player"}, {"instance_id": "x", "kind": "mystery_box"}],
          "wires": [{"from": ["p", "intent"], "to": ["x", "in"]}]}
    b = build_ecs(bp)
    b.step(4)
    assert b.component("x", "generic")["received"] == 4


def test_cyclic_wires_still_build_deterministically() -> None:
    bp = {"components": [{"instance_id": "a", "kind": "sink"}, {"instance_id": "b", "kind": "sink"}],
          "wires": [{"from": ["a", "out"], "to": ["b", "in"]}, {"from": ["b", "out"], "to": ["a", "in"]}]}
    assert build_ecs(bp).systems == build_ecs(bp).systems


def test_attached_script_runs_after_its_node() -> None:
    script = (
        "def on_tick():\n"
        "    v = read(self_e, 'vault')\n"
        "    if v and v['writes'] % 2 == 0:\n"
        "        store('even_writes', v['writes'])\n"
    )
    b = build_ecs(COMPOSE, scripts={"vault": {"source": "self_e = 0\n" + script, "reads": ["vault"], "writes": ["res:even_writes"]}})
    assert "bp.vault.script" in b.systems
    # bind the vault entity explicitly through a resource-free constant
    b2 = build_ecs(COMPOSE, scripts={"vault": {"source": f"self_e = {b.entities['vault']}\n" + script, "reads": ["vault"], "writes": ["res:even_writes"]}})
    b2.step(4)
    assert b2.world.get_resource("even_writes") == 4
    assert b2.manifest()["scripts"]["vault"]


def test_script_access_is_enforced() -> None:
    w = LiveWorld()
    w.register_component("hp")
    w.spawn({"hp": {"v": 1}})
    s = TickScheduler()
    s.add(script_system("def on_tick():\n    for r in query('hp'):\n        write(r[0], 'hp', {'v': 0})\n", name="sneaky", reads=("hp",)))
    with pytest.raises((AccessViolationError, SystemFailure)):
        s.run_tick(w)


def test_script_system_full_api() -> None:
    w = LiveWorld(seed=9)
    w.register_component("hp")
    w.register_component("tag")
    w.spawn({"hp": {"v": 0}})
    w.spawn({"hp": {"v": 5}})
    src = (
        "def on_tick():\n"
        "    for r in query('hp'):\n"
        "        if r[1]['v'] <= 0:\n"
        "            despawn(r[0])\n"
        "            emit('died', {'e': r[0], 't': tick})\n"
        "        else:\n"
        "            patch(r[0], 'hp', {'v': r[1]['v'] - 1})\n"
        "    spawn({'tag': {'roll': randint(1, 6), 'f': rand() < 1}})\n"
        "    store('seen', len(events('died')))\n"
    )
    s = TickScheduler()
    s.add(script_system(src, name="logic", reads=("hp", "event:died"), writes=("hp", "tag", "event:died", "res:seen")))
    s.run(w, 2)
    rows = list(w.query("tag"))
    assert len(rows) == 2 and all(1 <= r[1]["roll"] <= 6 for r in rows)
    assert [r[1]["v"] for r in w.query("hp")] == [3]
    w2 = LiveWorld(seed=9)
    w2.register_component("hp")
    w2.register_component("tag")
    w2.spawn({"hp": {"v": 0}})
    w2.spawn({"hp": {"v": 5}})
    s2 = TickScheduler()
    s2.add(script_system(src, name="logic", reads=("hp", "event:died"), writes=("hp", "tag", "event:died", "res:seen")))
    s2.run(w2, 2)
    assert w.state_digest == w2.state_digest


def test_script_system_requires_entrypoint_and_validates_args() -> None:
    with pytest.raises(ValidationError):
        script_system("def other():\n    pass\n", name="x")
    w = LiveWorld()
    s = TickScheduler()
    s.add(script_system("def on_tick():\n    despawn(-1)\n", name="bad"))
    with pytest.raises((ScriptRuntimeError, SystemFailure)):
        s.run_tick(w)
