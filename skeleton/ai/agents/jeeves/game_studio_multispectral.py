"""Source-attested ten-pass audit and derived multispectral mirror telemetry.

This is *not* a physical RGB/depth/thermal sensor, camera or spectral
renderer. Ten independently named, measured channels are projections
of the authoritative game state, command custody and reward stream.
No second sensory information is manufactured by re-labeling a channel.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from .game_studio_environment import StudioGameEnvironment, parse_studio_source

SCHEMA="skeleton.game_builder.multispectral_audit.v1"
BANDS=("motion","economy","vitals","objectives","reward","events",
       "control","temporal","novelty","safety")
CHECKS=("source_custody","runtime_identity","seed_bounds",
        "action_allowlist","transition_chain","reward_finiteness",
        "terminal_and_command_counts","final_state_custody",
        "reverse_checkpoint_replay","channel_derivation")
MAX_AUDIT_STEPS=48


class MultispectralAuditError(ValueError):
    """A registered simulation, source or derived channel failed scrutiny."""


def _digest(value):
    try:
        data=json.dumps(value,sort_keys=True,separators=(",",":"),
                        ensure_ascii=True,allow_nan=False).encode()
    except (ValueError,TypeError,RecursionError) as exc:
        raise MultispectralAuditError("nonfinite or foreign spectral evidence") from exc
    return sha256(data).hexdigest()


def _numbers(value):
    if type(value) is not dict:
        raise MultispectralAuditError("source observation must be a map")
    for key,item in value.items():
        if type(key) is not str or type(item) not in (int,float) or not math.isfinite(item):
            raise MultispectralAuditError("source observation contains fabricated or nonfinite channel")
    return {key:float(item) for key,item in value.items()}


def audit_simulation(source: dict, lane: dict, *, steps: int) -> dict:
    """Independently replay one mirrored run, audit ten contracts, reverse-check.

    The verifier is deliberately separate from the episode executor and
    cannot train models, apply scenario edits, or authorize policy promotion.
    """
    original=parse_studio_source(source)
    if (type(lane) is not dict or type(steps) is not int
            or not 1<=steps<=MAX_AUDIT_STEPS
            or type(lane.get("seed")) is not int
            or not 0<=lane["seed"]<=2**31-1):
        raise MultispectralAuditError("bounded original game audit source required")
    commands=lane.get("actions")
    transitions=lane.get("transition_digests")
    if (type(commands) is not list or not 1<=len(commands)<=steps
            or type(transitions) is not list
            or len(commands)!=len(transitions)
            or type(lane.get("steps")) is not int
            or lane["steps"]!=len(commands)):
        raise MultispectralAuditError("complete bounded source action trace required")
    env=StudioGameEnvironment(original,max_steps=steps)
    accepted=0
    rejected=0
    earned=0.0
    checks=[]
    rows=[]
    checkpoints=[]
    seen=set()
    try:
        obs=_numbers(dict(env.reset(lane["seed"])))
        checks.append(("source_custody",
                       env.source_digest==lane.get("source_digest")))
        checks.append(("runtime_identity",
                       env.spec.environment_digest==lane.get("environment_digest")))
        checks.append(("seed_bounds",env.snapshot()["seed"]==lane["seed"]))
        checkpoints.append((0,env.snapshot()))
        features=tuple(key for key in sorted(obs) if key!="time")
        def state(values):
            return tuple(round(values[k],6) for k in features)
        seen.add(state(obs))
        all_known=all(type(action) is str and action in env.spec.actions
                      for action in commands)
        checks.append(("action_allowlist",all_known))
        if not all_known or not all(ok for _,ok in checks):
            raise MultispectralAuditError("source identity or action palette differs from executed game")
        for position,action in enumerate(commands,1):
            if env.done:
                raise MultispectralAuditError("postterminal game command present")
            before=obs
            step=env.step(action)
            obs=_numbers(dict(step.observation))
            if step.transition_digest!=transitions[position-1]:
                raise MultispectralAuditError("transition chain changed during independent replay")
            witness=step.info.get("evidence",{})
            valid=witness.get("accepted") is True
            accepted+=int(valid)
            rejected+=int(not valid)
            rewards=_numbers(dict(step.reward_components))
            total=math.fsum(rewards.values())
            earned+=total
            novel=state(obs) not in seen
            seen.add(state(obs))
            delta={k:obs[k]-before[k] for k in features}
            event_list=(env._receipt or {}).get("state",{}).get("events",[])
            event_count=len(event_list) if type(event_list) is list else 0
            data={
                "motion":abs(delta.get("progress",0)),
                "economy":abs(delta.get("score",0))+abs(delta.get("resources",0)),
                "vitals":abs(delta.get("health",0)),
                "objectives":abs(delta.get("success",0))+abs(delta.get("failure",0)),
                "reward":total,
                "events":float(min(64,event_count)),
                "control":float(valid),
                "temporal":obs.get("time",0)-before.get("time",0),
                "novelty":float(novel and valid),
                "safety":float((not valid) or obs.get("failure",0)>0),
            }
            if any(not math.isfinite(value) for value in data.values()):
                raise MultispectralAuditError("derived spectral channel is not finite")
            rows.append(data)
            if position==len(commands)//2 or position==len(commands):
                checkpoints.append((position,env.snapshot()))
        ending=env.snapshot()
        checks.append(("transition_chain",True))
        checks.append(("reward_finiteness",
                       math.isfinite(earned) and abs(earned-lane.get("total_reward",float("inf")))<1e-4))
        checks.append(("terminal_and_command_counts",
                       accepted==lane.get("accepted_actions")
                       and rejected==lane.get("rejected_actions")
                       and ending["actions"]==commands))
        checks.append(("final_state_custody",
                       ending["digest"]==lane.get("snapshot_digest")
                       and obs==_numbers(lane.get("last_observation",{}))))
        # Reverse audit reconstitutes committed intermediate checkpoints in
        # descending order, not an imaginary time-reversal of the game.
        reverse=[]
        for at,snapshot in reversed(checkpoints):
            verifier=StudioGameEnvironment(original,max_steps=steps)
            try:
                verifier.restore(snapshot)
                equal=verifier.snapshot()==snapshot
                if not equal:
                    raise MultispectralAuditError("reverse-prefix source replay diverged")
                reverse.append({"at_step":at,"snapshot_digest":snapshot["digest"]})
            finally:
                verifier.close()
        checks.append(("reverse_checkpoint_replay",len(reverse)>=2))
        channels={}
        for key in BANDS:
            values=[round(row[key],6) for row in rows]
            channels[key]={
                "values":values,
                "minimum":min(values),"maximum":max(values),
                "mean":round(math.fsum(values)/len(values),6),
                "derivation":"original_game_numeric_state_and_action_evidence",
                "digest":_digest({"channel":key,"samples":values,
                                  "trace":transitions}),
            }
        checks.append(("channel_derivation",
                       set(channels)==set(BANDS) and
                       all(len(band["values"])==len(commands) for band in channels.values())))
        if tuple(name for name,_ in checks)!=CHECKS or not all(ok for _,ok in checks):
            raise MultispectralAuditError("one of ten postrun game audits failed")
        audit={
            "schema_version":SCHEMA,
            "source_digest":env.source_digest,
            "environment_digest":env.spec.environment_digest,
            "lane_seed":lane["seed"],
            "run_actions":len(commands),
            "actual_replayed_actions":sum(range(1,len(commands)+1)),
            "checks":[{"name":name,"passed":ok} for name,ok in checks],
            "passed_count":len(checks),
            "failed_count":0,
            "reverse_checkpoints":reverse,
            "spectral_channels":channels,
            "spectral_type":"derived_multiband_gameplay_telemetry",
            "real_rgb_depth_thermal_sensors":False,
            "real_visual_cameras":False,
            "independent_information_streams_claimed":False,
            "promotion_authorized":False,
        }
        return {**audit,"digest":_digest(audit)}
    finally:
        env.close()


__all__=["SCHEMA","BANDS","CHECKS","MultispectralAuditError","audit_simulation"]
