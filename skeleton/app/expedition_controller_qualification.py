"""Run every original controller layout through three real source replay variants."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from skeleton.app.recovered_evidence import EvidenceError,digest,pin,seal
from skeleton.app.expedition_controller_model import source
from skeleton.app.expedition_controller_bridge import Journey
from skeleton.jeeves.game_frontier_expedition import ExpeditionEpisode
from skeleton.jeeves.game_frontier_expedition_controllers import controller_profiles,ControllerEvent
from skeleton.jeeves.game_frontier_expedition_input import (
    AxisCalibration,AxisBinding,AnalogSample,remap_controller,merge_input_replays,verify_input_replay,
)
from skeleton.jeeves.game_frontier_expedition_save_store import ExpeditionSaveStore

VARIANTS=("digital","remapped","mixed_analog")


def compile_input(profile,actions,variant):
    if variant not in VARIANTS:
        raise EvidenceError("unknown input variant")
    if variant=="remapped":
        profile=remap_controller(profile,action="travel",button_index=31)
    buttons={b.action:b.godot_button for b in profile.buttons}
    calibration=AxisCalibration(0,deadzone=.2,engage=.65,release=.35)
    bindings=(AxisBinding(calibration,1,"navigate_down"),
              AxisBinding(calibration,-1,"navigate_up"))
    digital=[]
    analog=[]
    for index,action in enumerate(actions,1):
        frame=index*4
        if variant=="mixed_analog" and action in ("navigate_up","navigate_down"):
            sign=1 if action=="navigate_down" else -1
            analog.extend((AnalogSample(frame-1,0,.15*sign),
                           AnalogSample(frame,0,.9*sign),
                           AnalogSample(frame+1,0,.55*sign),
                           AnalogSample(frame+2,0,0)))
        else:
            button=buttons[action]
            digital.extend((ControllerEvent(frame,button,True),
                            ControllerEvent(frame+1,button,True),
                            ControllerEvent(frame+2,button,False)))
    return profile,tuple(digital),tuple(analog),bindings


def _run(world,player,plan,profile,variant,db):
    profile,digital,analog,bindings=compile_input(profile,plan["semantic_actions"],variant)
    events=merge_input_replays(profile,digital,analog,bindings,world_digest=world.digest)
    verify_input_replay(profile,digital,analog,bindings,events,world_digest=world.digest)
    if [e.action for e in events]!=plan["semantic_actions"]:
        raise EvidenceError("canonical controller variant changed action semantics")
    journey=Journey(ExpeditionEpisode(world,player))
    split=len(events)//2
    runid=profile.profile_id+"."+variant
    for event in events[:split]:
        journey.apply(event)
    # Persist the actual episode; UI selection is reconstructed from the
    # exact source prefix in a separate in-memory replay, not guessed.
    with ExpeditionSaveStore(db) as store:
        first=store.save(runid,journey.episode)
    with ExpeditionSaveStore(db) as store:
        restored=store.load(runid,world,player)
        if restored is None or restored.receipt!=first.receipt:
            raise EvidenceError("reopened expedition checkpoint differs")
        prefix=Journey(ExpeditionEpisode(world,player))
        for event in events[:split]:
            prefix.apply(event)
        if prefix.episode.snapshot()!=restored.episode.snapshot() or prefix.selection!=journey.selection:
            raise EvidenceError("controller selection reconstruction differs")
        prefix.episode=restored.episode
        for event in events[split:]:
            prefix.apply(event)
        final=store.save(runid,prefix.episode,expected_generation=first.generation)
    with ExpeditionSaveStore(db) as store:
        reopened=store.load(runid,world,player)
        history=store.history(runid)
        if reopened is None or reopened.receipt!=final.receipt:
            raise EvidenceError("reopened terminal episode differs")
        snapshot=reopened.episode.snapshot()
        if not reopened.episode.won or snapshot["snapshot_digest"]!=plan["expected_snapshot_digest"]:
            raise EvidenceError("actual gameplay parity mismatch")
        if digest(prefix.records)!=plan["semantic_state_chain"]:
            raise EvidenceError("cross-layout semantic state chain diverged")
        if len(history)!=2 or final.generation!=2:
            raise EvidenceError("expedition generation accounting mismatch")
    return {"profile":profile.profile_id,"variant":variant,"profile_digest":profile.digest,
            "input_trace_digest":digest([asdict(e) for e in events]),
            "input_head":events[-1].receipt,"digital_samples":len(digital),"analog_samples":len(analog),
            "semantic_actions":len(events),"gameplay_actions":len(reopened.episode.actions),
            "snapshot_digest":snapshot["snapshot_digest"],"save_head":final.receipt,
            "actual_save_generations":len(history),"reopened_connections":2,
            "final_state":reopened.episode.state()}


def qualify_journey(raw,*,expected_plan_digest,authorized):
    if authorized is not True:
        raise PermissionError("explicit local controller operator required")
    world,player,plan=source(raw)
    pin(plan["digest"],expected_plan_digest)
    runs=[]
    # A qualification database is private and temporary, never an existing
    # user save or release path. All controller variants execute real actions.
    with TemporaryDirectory(prefix="skeleton-expedition-controller-") as d:
        db=Path(d)/"journeys.sqlite3"
        for profile in controller_profiles():
            for variant in VARIANTS:
                runs.append(_run(world,player,plan,profile,variant,db))
    if len({r["snapshot_digest"] for r in runs})!=1:
        raise EvidenceError("controller layouts did not produce identical game state")
    return seal({"schema":"skeleton.expedition-controller-journey.report.v1",
                 "plan":plan,"variants":runs,"profile_count":len(controller_profiles()),
                 "executed_variant_count":len(runs),"actual_gameplay_action_count":sum(r["gameplay_actions"] for r in runs),
                 "source_gameplay_equivalence":True,"sqlite_reopen_verified":True,
                 "hardware_devices_tested":0,"native_engine_executed":False,"release_certified":False})
