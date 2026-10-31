"""Source and game-state challenge of candidate Godot expedition observations."""

import copy
import hashlib
import json

import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionAction, ExpeditionEpisode, Traveler, find_route,
)
from skeleton.jeeves.game_frontier_expedition_native_verify import (
    PREFIX, SCHEMA, NativeExpeditionError, inspect_native_expedition_trace,
)
from tests.test_game_frontier_expedition import world


def player():
    return Traveler(
        permitted_modes=frozenset(("walk","rope_bridge","updraft","glide","portal")),
        flags=frozenset(("glider",)),equipment=frozenset(("instrument_navigation",)),
        max_stamina=1000,skill=.5,
    )


def sample_records(*, complete=True):
    w,p=world(),player()
    episode=ExpeditionEpisode(w,p)
    def record(action,evidence,index):
        state=episode.state()
        return {
            "schema":SCHEMA,
            "source_digest":w.source_digest,
            "world_digest":w.digest,
            "traveler_digest":episode.traveler_digest,
            "project_id":w.project_id,
            "action":action,"evidence":evidence,
            "state":{
                **state,
                "flags":sorted(set(state["flags"])|set(p.equipment)),
                "failed":state["health"]<=0,
            },
            "receipt_head":(
                hashlib.sha256(
                    (w.source_digest+":"+w.project_id+":"+w.arrival).encode()
                ).hexdigest() if index==0 else
                hashlib.sha256(f"candidate-step-{index}".encode()).hexdigest()
            ),
            "native_authority":"untrusted_native_candidate_for_independent_review",
        }
    rows=[record("spawn","start",0)]
    route=find_route(w,p,"exit")
    actions=route.edge_ids if complete else route.edge_ids[:2]
    for n,link in enumerate(actions,1):
        episode.step(ExpeditionAction("travel",link))
        rows.append(record("travel",link,n))
    return w,p,rows


def as_stdout(rows):
    return "Godot Engine\nEXPEDITION_READY original_realm 7 10\n" + "".join(
        PREFIX+json.dumps(row,separators=(",",":"))+"\n"
        for row in rows
    )


def test_complete_original_native_candidate_trace_replays_all_actions():
    w,p,rows=sample_records()
    result=inspect_native_expedition_trace(
        as_stdout(rows),w,p,expected_complete=True,
    )
    assert result["observations"]==len(rows)
    assert result["executed_actions"]==len(rows)-1
    assert result["won"]
    assert result["verified_source_gameplay"]
    assert not result["native_process_origin_independently_attested"]
    assert not result["device_location_used"]
    assert len(result["receipt_digest"])==64


def test_partial_native_gameplay_is_valid_prefix_but_not_complete():
    w,p,rows=sample_records(complete=False)
    prefix=inspect_native_expedition_trace(as_stdout(rows),w,p)
    assert prefix["executed_actions"]==2
    assert not prefix["won"]
    with pytest.raises(NativeExpeditionError,match="never reached"):
        inspect_native_expedition_trace(
            as_stdout(rows),w,p,expected_complete=True,
        )


@pytest.mark.parametrize("field,alteration",(
    ("source_digest","0"*64),
    ("world_digest","1"*64),
    ("traveler_digest","2"*64),
    ("project_id","forged-game"),
))
def test_native_source_spoofing_is_rejected(field,alteration):
    w,p,rows=sample_records()
    rows[0][field]=alteration
    with pytest.raises(NativeExpeditionError,match="foreign source"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


def test_native_position_teleport_is_rejected():
    w,p,rows=sample_records()
    rows[1]["state"]["position"]="exit"
    with pytest.raises(NativeExpeditionError,match="contradicts"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


@pytest.mark.parametrize("field,value",(
    ("stamina",999),
    ("health",1),
    ("seconds",1e12),
    ("won",True),
    ("actions",99),
))
def test_fake_native_metrics_do_not_override_source_gameplay(field,value):
    w,p,rows=sample_records()
    rows[1]["state"][field]=value
    with pytest.raises(NativeExpeditionError):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


def test_native_cannot_invent_collected_items_or_quest_flags():
    w,p,rows=sample_records()
    rows[1]["state"]["inventory"]=["forged-asset"]
    with pytest.raises(NativeExpeditionError,match="continuity"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)
    w,p,rows=sample_records()
    rows[1]["state"]["flags"].append("false_quest")
    with pytest.raises(NativeExpeditionError,match="continuity"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


def test_duplicate_receipt_history_is_detected():
    w,p,rows=sample_records()
    rows[2]["receipt_head"]=rows[1]["receipt_head"]
    with pytest.raises(NativeExpeditionError,match="repeated"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


def test_unconnected_travel_edge_cannot_be_faked():
    w,p,rows=sample_records()
    rows[1]["evidence"]="goal_path"
    with pytest.raises(NativeExpeditionError,match="not playable"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


def test_native_restart_requires_a_new_explicit_session():
    w,p,rows=sample_records()
    rows[1]["action"]="spawn"
    with pytest.raises(NativeExpeditionError,match="restarted"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


def test_missing_initial_spawn_is_blocked():
    w,p,rows=sample_records()
    with pytest.raises(NativeExpeditionError,match="initial spawn"):
        inspect_native_expedition_trace(as_stdout(rows[1:]),w,p)


def test_foreign_initial_receipt_cannot_bind_a_valid_game():
    w,p,rows=sample_records()
    rows[0]["receipt_head"]="0"*64
    with pytest.raises(NativeExpeditionError,match="spawn receipt"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


def test_native_data_rejects_json_duplicate_keys_and_nan():
    w,p,rows=sample_records()
    line=json.dumps(rows[0])
    line=line[:-1]+',"schema":"forged"}'
    with pytest.raises(NativeExpeditionError,match="duplicate"):
        inspect_native_expedition_trace(PREFIX+line,w,p)
    line=json.dumps(rows[0]).replace('"seconds": 0.0','"seconds": NaN')
    with pytest.raises(NativeExpeditionError):
        inspect_native_expedition_trace(PREFIX+line,w,p)


def test_native_observation_has_hard_budget_and_must_not_be_empty():
    w,p,rows=sample_records()
    with pytest.raises(NativeExpeditionError,match="no game observation"):
        inspect_native_expedition_trace("Godot Engine launched",w,p)
    with pytest.raises(NativeExpeditionError,match="bounded"):
        inspect_native_expedition_trace("X" * 4_000_001,w,p)


def test_native_precondition_rejects_fake_signoff_flags():
    w,p,rows=sample_records()
    rows[0]["native_authority"]="independently_verified"
    with pytest.raises(NativeExpeditionError,match="source authority"):
        inspect_native_expedition_trace(as_stdout(rows),w,p)


def test_explicit_rest_is_replayed_only_on_authored_safe_nodes():
    w,p,rows=sample_records(complete=False)
    episode=ExpeditionEpisode(w,p)
    episode.step(ExpeditionAction("travel","launch"))
    episode.step(ExpeditionAction("travel","bridge"))
    # Actual position "sky" is not safe to rest.
    last=copy.deepcopy(rows[-1])
    last["action"]="rest"
    last["evidence"]="sky"
    last["receipt_head"]=hashlib.sha256(b"pretend-rest").hexdigest()
    last["state"]["actions"]=3
    with pytest.raises(NativeExpeditionError,match="not playable"):
        inspect_native_expedition_trace(as_stdout(rows+[last]),w,p)
