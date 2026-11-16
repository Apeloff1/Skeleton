"""Real canonical action, collision, fixed-clock and SQLite custody regression source."""
from copy import deepcopy
import json

import pytest

from skeleton.app.recovered_evidence import EvidenceError, seal
from skeleton.game.simulation.fixed_input_replay import Simulation, qualify_motion
from skeleton.app.recovered_save_qualification import qualify_storage


def binding(control,axis,scale=1000):
    return {"control":control,"axis":axis,"scale_milli":scale,
            "deadzone_milli":0,"modifiers":[]}


@pytest.fixture
def motion():
    return {"schema":"skeleton.fixed-input-replay.order.v1","project_id":"motion",
            "step_us":10000,"max_steps":4,
            "player":{"id":"player","position":[0,0,0],"speed":1000,"half_extent":1},
            "obstacles":[{"id":"wall","min":[25,-20,-3],"max":[30,20,3]}],
            "controls":{"defaults":[binding("keyboard:key.d","x"),
                                   binding("keyboard:key.a","x",-1000),
                                   binding("keyboard:key.w","y")],"overrides":None},
            "frames":[
                {"elapsed_us":10000,"samples":[{"control":"keyboard:key.d","value":1000}]},
                {"elapsed_us":10000,"samples":[]},
                {"elapsed_us":100000,"samples":[]},
                {"elapsed_us":10000,"samples":[{"control":"keyboard:key.d","value":0},
                                                {"control":"keyboard:key.a","value":1000}]},
            ]}


def test_actual_clock_collision_and_reconstruction(motion):
    result=qualify_motion(motion,authorized=True)
    assert result["fixed_clock_executed"]
    assert result["final"]["state"]["clock"]["tick"]==7
    assert result["final"]["state"]["clock"]["dropped_us"]==60000
    assert result["blocked_x_steps"]==4
    assert result["final"]["state"]["position"]==[10,0,0]
    assert result["rollback_receipt_digest"]
    assert result==qualify_motion(motion,authorized=True)


def test_remap_passes_through_canonical_owner(motion):
    motion["controls"]["overrides"]=[binding("gamepad:stick.left.x","x")]
    motion["frames"]=[{"elapsed_us":10000,"samples":[
        {"control":"gamepad:stick.left.x","value":1000}]}]
    result=qualify_motion(motion,authorized=True)
    assert result["final"]["state"]["position"]==[10,0,0]


def test_forged_snapshot_rejected(motion):
    sim=Simulation.start(motion,authorized=True)
    sim.frame()
    snapshot=sim.snapshot()
    body={k:deepcopy(v) for k,v in snapshot.items() if k!="digest"}
    body["state"]["position"]=[999,0,0]
    forged=seal(body)
    with pytest.raises(EvidenceError):
        Simulation.restore(motion,forged,expected_digest=forged["digest"],authorized=True)


def test_duplicate_input_and_authorization(motion):
    with pytest.raises(PermissionError):
        Simulation.start(motion,authorized=False)
    motion["frames"][0]["samples"].append(motion["frames"][0]["samples"][0])
    with pytest.raises(EvidenceError):
        Simulation.start(motion,authorized=True)


def test_sqlite_movement_version_and_rollback(motion):
    report=qualify_storage("movement",motion,authorized=True)
    assert report["sqlite_disk_roundtrip_executed"]
    assert report["sqlite_connections_reopened"]==3
    assert report["prior_version_retained"]
    assert report["file_diff"]["files"]["changed"]==["replay/save.json"]
    assert [v["sequence"] for v in report["versions"]]==[1,2,3]
    assert not report["crash_recovery_tested"]


def test_sqlite_quest_version_and_rollback():
    order={"schema":"skeleton.synthesized-quest.order.v1","campaign_id":"recovery",
           "title":"Lantern","seed":8,"length":3,
           "world":{"start":"dock","edges":{"dock":["hill"],"hill":["dock"]},"npcs":{}},
           "policy":{"banned_terms":[],"max_reward_per_step":4,"max_total_reward":12,
                     "allowed_reward_kinds":["xp"]},
           "mechanics":{"registry":[
               {"id":"travel","provides":["travel"],"requires":[],"conflicts":[],"params":{}},
               {"id":"quest","provides":["quest"],"requires":["travel"],"conflicts":[],"params":{}},
           ],"selected":["travel","quest"],"overrides":{}}}
    report=qualify_storage("quest",order,authorized=True)
    assert report["kind"]=="quest"
    assert report["journal_event_count"]>=3
    assert report["rollback"]["new_head"]==3


def test_installed_fixed_replay(motion,tmp_path,capsys):
    from skeleton.__main__ import main
    path=tmp_path/"order.json"
    path.write_text(json.dumps(motion),encoding="utf-8")
    assert main(["fixed-input-replay","qualify","--order",str(path),"--trusted-local-operator"])==0
    assert json.loads(capsys.readouterr().out)["final"]["trace_ticks"]==7
