"""Original deterministic rhythm game; no imported recordings, assets or melodies.

A legitimate input samples the authenticated simulation clock. Successful
precision requires authored note/lane/time coincidence, not a manually supplied
timestamp, score or fabricated judgement. Holds, chords, slides, mines, timing
windows, clear grades and anti-mash penalties are independent physical rules.
"""
from __future__ import annotations

LANES=6
KINDS=("tap","hold","slide","chord","mine")
ACTIONS=tuple(
 [f"{kind}:{i}" for kind in ("tap","press","release","flick") for i in range(LANES)]
 +[f"chord:{i}:{j}" for i in range(LANES) for j in range(LANES) if i!=j]
 +[f"wait:{ms}" for ms in (10,20,25,50,100,125,250,500,1000,2000)]
 +["finish","inspect","restart_calibration"]
)


class RhythmActionError(ValueError):
    """Unregistered original rhythm input or invalid authored timing source."""


def _int(value,low,high,key):
    if type(value) is not int or not low<=value<=high:
        raise RhythmActionError("invalid original rhythm "+key)
    return value


def _beat_ms(beat,bpm):
    return (beat*60000+bpm//2)//bpm


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    if not 5<=config["perfect_window_ms"]<=config["great_window_ms"]<=config["hit_window_ms"]:
        raise RhythmActionError("temporal difficulty requires perfect <= great <= hit windows")
    count=config["beat_count"]
    notes=[]
    for i in range(count):
        at=_beat_ms(i,config["bpm"])+(min(config["swing"],
              config["swing_limit_ms"]) if i%2 else 0)
        lane=(i*3+seed+i//4)%config["lane_count"]
        kind=("tap" if i==0 else
              "hold" if config["hold_notes"] and i%7==4 else
              "chord" if config["chords"] and i%6==3 else
              "slide" if config["slides"] and i%5==2 else
              "mine" if config["mines"] and i%11==7 else "tap")
        partner=(lane+1+i%max(1,config["lane_count"]-1))%config["lane_count"] if (
                kind=="chord") else None
        notes.append({
            "id":i,"at":at,"lane":lane,"kind":kind,
            "partner":partner,
            "duration":_beat_ms(config["hold_length_beats"],config["bpm"]) if
                         kind=="hold" else 0,
            "accent":i%config["accent_interval"]==0,
        })
    return {
        "title":"Original Rhythm Studies "+str(seed%100),
        "bpm":config["bpm"],"lanes":config["lane_count"],
        "beats":config["beat_count"],"offset_ms":config["song_offset_ms"],
        "meter":config["meter"],"style":"original_synth",
        "notes":notes,
    }


def normalize_layout(config,layout):
    if not 5<=config["perfect_window_ms"]<=config["great_window_ms"]<=config["hit_window_ms"]:
        raise RhythmActionError("typed rhythm hit windows must be ordered perfect <= great <= hit")
    if config["release_window_ms"]<config["perfect_window_ms"]:
        raise RhythmActionError("held release window must allow the actual perfect interval")
    if type(layout) is not dict or set(layout)!={
        "title","bpm","lanes","beats","offset_ms","meter","style","notes"}:
        raise RhythmActionError("original rhythm chart requires exact safe fields")
    title=layout["title"]
    if type(title) is not str or not 3<=len(title)<=64 or not all(
       c.isalnum() or c in " -_." for c in title):
        raise RhythmActionError("song title must be a safe original bounded name")
    if (_int(layout["bpm"],30,320,"BPM")!=config["bpm"] or
        _int(layout["lanes"],3,LANES,"lanes")!=config["lane_count"] or
        _int(layout["beats"],1,256,"beats")!=config["beat_count"]):
        raise RhythmActionError("original chart tempo, length and lanes must match editor")
    _int(layout["offset_ms"],0,config["song_offset_ms"],"source offset")
    if layout["meter"]!=config["meter"] or layout["style"]!="original_synth":
        raise RhythmActionError("original metrical signature or local synthesis marker invalid")
    notes=layout["notes"]
    if type(notes) is not list or len(notes)!=config["beat_count"]:
        raise RhythmActionError("rhythm chart must contain one authored beat event per beat")
    used=set();normalized=[]
    last=-1
    for i,n in enumerate(notes):
        if type(n) is not dict or set(n)!={
          "id","at","lane","kind","partner","duration","accent"}:
            raise RhythmActionError("exact note timing identity and hold grammar required")
        if _int(n["id"],0,255,"note id")!=i:
            raise RhythmActionError("noncanonical original note identity")
        at=_int(n["at"],0,600000,"beat timestamp")
        expected=_beat_ms(i,config["bpm"])
        if abs(at-expected)>config["swing_limit_ms"]:
            raise RhythmActionError("original note event lies outside approved rhythmic grid")
        if at<=last:
            raise RhythmActionError("original note timestamps must increase strictly")
        last=at
        lane=_int(n["lane"],0,config["lane_count"]-1,"note lane")
        kind=n["kind"]
        if type(kind) is not str or kind not in KINDS:
            raise RhythmActionError("unregistered original gameplay note kind")
        if (kind=="hold" and not config["hold_notes"]) or (
             kind=="slide" and not config["slides"]) or (
             kind=="chord" and not config["chords"]) or (
             kind=="mine" and not config["mines"]):
            raise RhythmActionError("authored note type disabled by explicit policy")
        partner=n["partner"]
        if kind=="chord":
            if type(partner) is not int or not 0<=partner<config["lane_count"] or partner==lane:
                raise RhythmActionError("real two-lane chord requires distinct valid lanes")
        elif partner is not None:
            raise RhythmActionError("single note cannot mint a second phantom chord lane")
        duration=_int(n["duration"],0,4000,"held note duration")
        if kind=="hold":
            if duration!=_beat_ms(config["hold_length_beats"],config["bpm"]):
                raise RhythmActionError("held interval must obey authored meter and duration")
        elif duration!=0:
            raise RhythmActionError("only sustained notes may have a release interval")
        if type(n["accent"]) is not bool:
            raise RhythmActionError("rhythm accent must have exact boolean type")
        point=(at,lane,partner)
        if point in used:raise RhythmActionError("same original note has duplicate physical lane")
        used.add(point);normalized.append(dict(n))
    return {**dict(layout),"notes":normalized}


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    state["chart"]=source
    state["clock_ms"]=source["offset_ms"]
    state["judgements"]=[None for _ in source["notes"]]
    state["pressed"]={}
    state["held"]=[]
    return state


def start(config,seed):
    _int(seed,0,2**31-1,"seed")
    state={
      "seed":seed,"chart":{},"clock_ms":0,"turn":0,
      "judgements":[],"pressed":{},"held":[],
      "combo":0,"best_combo":0,"score":0,"perfect":0,"great":0,
      "good":0,"miss":0,"mines_avoided":0,"mines_hit":0,
      "stray":0,"health":config["starting_health"],
      "max_health":config["starting_health"],"max_score":0,
      "hit_count":0,"accuracy":0,"rank":"ungraded",
      "finished":False,"failed":False,"victory":False,
      "events":[],"reason":"",
    }
    return apply_scene(state,config,default_layout(config,seed))


def _score(state,config,note,grade,events):
    idx=note["id"]
    if state["judgements"][idx] is not None:
        raise RhythmActionError("already-judged original note cannot be scored twice")
    state["judgements"][idx]=grade
    if grade=="miss":
        state["miss"]+=1
        state["combo"]=0
        state["health"]=max(0,state["health"]-config["miss_health"])
        state["score"]=max(0,state["score"]-config["miss_penalty"])
        events.append("original_beat_genuinely_missed")
    elif grade=="mine_avoided":
        state["mines_avoided"]+=1
        events.append("hazard_note_safely_avoided_in_real_time")
    else:
        state[grade]+=1
        state["hit_count"]+=1
        state["combo"]+=1
        state["best_combo"]=max(state["best_combo"],state["combo"])
        weight={"perfect":config["perfect_points"],
                "great":config["great_points"],
                "good":config["good_points"]}[grade]
        multiplier=min(config["max_multiplier"],
            1+(state["combo"]-1)//config["combo_interval"])
        state["score"]+=weight*multiplier*(config["hold_bonus"] if
                                note["kind"]=="hold" else 1)
        state["health"]=min(state["max_health"],
                            state["health"]+config["hit_heal"])
        events.append("original_player_hit_timed_"+grade+"_note")
    if state["health"]==0 and config["fail_mode"]=="health" and not config["practice_mode"]:
        state["failed"]=True
        state["reason"]="original_challenge_health_exhausted"


def _expire(state,config,events):
    clock=state["clock_ms"]
    for note in state["chart"]["notes"]:
        idx=note["id"]
        if state["judgements"][idx] is not None:continue
        # A calibrated device reports sound-relative input late; the
        # server-owned expiration clock must use the same effective phase.
        at=note["at"]+state["chart"]["offset_ms"]+config["timing_calibration_ms"]
        if note["kind"]=="mine":
            if clock>at+config["hit_window_ms"]:
                _score(state,config,note,"mine_avoided",events)
        elif note["kind"]=="hold" and str(idx) in state["pressed"]:
            if clock>at+note["duration"]+config["release_window_ms"]:
                del state["pressed"][str(idx)]
                state["held"]=[x for x in state["held"] if x!=idx]
                _score(state,config,note,"miss",events)
        elif clock>at+config["hit_window_ms"]+(
             20 if config["assist_mode"]=="expanded" else 0):
            _score(state,config,note,"miss",events)


def _quality(abs_delta,config):
    if abs_delta<=config["perfect_window_ms"]:return "perfect"
    if abs_delta<=config["great_window_ms"]:return "great"
    if abs_delta<=config["hit_window_ms"]+(
        20 if config["assist_mode"]=="expanded" else 0):return "good"
    return None


def _max_points(state,config):
    return sum(config["perfect_points"]*(config["hold_bonus"] if
       n["kind"]=="hold" else 1) for n in state["chart"]["notes"]
       if n["kind"]!="mine")


def _finish(state,config,events):
    if state["pressed"] or any(x is None for x in state["judgements"]):
        raise RhythmActionError("cannot finish with unjudged real notes or uncompleted holds")
    base=_max_points(state,config)
    state["max_score"]=base
    earned=state["perfect"]*config["perfect_points"]+(
        state["great"]*config["great_points"])+(
        state["good"]*config["good_points"])
    # Unmultiplied calibration accuracy from earned timing judgement,
    # not from combo multiplier (which can legitimately exceed 100%).
    state["accuracy"]=(10000*earned)//max(1,sum(
        config["perfect_points"] for n in state["chart"]["notes"]
        if n["kind"]!="mine"))
    pct=state["accuracy"]
    state["rank"]="SS" if pct>=9900 else "S" if pct>=9500 else (
       "A" if pct>=8500 else "B" if pct>=7000 else "C")
    state["finished"]=True
    state["victory"]=pct>=max(config["clear_threshold_percent"],
                             config["accuracy_floor"])*100
    state["reason"]="original_rhythm_chart_cleared" if state["victory"] else (
         "original_rhythm_chart_completed_below_clear_target")
    events.append("original_authoritative_rhythm_chart_finalized")


def step(state,config,action):
    if action not in ACTIONS:
        raise RhythmActionError("unregistered original rhythmic input")
    if state["failed"] or state["finished"]:
        raise RhythmActionError("terminal rhythm chart cannot accept further input")
    events=[]
    clock=state["clock_ms"]
    if action.startswith("wait:"):
        delta=int(action.split(":")[1])
        state["clock_ms"]+=delta
        events.append("actual_original_simulation_audio_clock_advanced")
        _expire(state,config,events)
    elif action in ("inspect","restart_calibration"):
        if action=="restart_calibration" and state["hit_count"]==0 and state["miss"]==0:
            state["clock_ms"]=state["chart"]["offset_ms"]
            events.append("original_pre_song_clock_calibrated")
        elif action=="restart_calibration":
            raise RhythmActionError("cannot reset live score or timing mid-song")
        else:
            events.append("original_timing_chart_inspected_without_autoplay")
    elif action=="finish":
        _expire(state,config,events)
        _finish(state,config,events)
    else:
        fields=action.split(":")
        kind=fields[0]
        lane=int(fields[1])
        partner=int(fields[2]) if kind=="chord" else None
        # Releasing a key is not a generic missable stroke. It must
        # match a real previously held note on the authoritative lane.
        if kind=="release" and not any(
             n["lane"]==lane and str(n["id"]) in state["pressed"]
             for n in state["chart"]["notes"]):
            raise RhythmActionError("hold release requires a previously authenticated key press")
        if lane>=state["chart"]["lanes"] or (
            partner is not None and partner>=state["chart"]["lanes"]):
            raise RhythmActionError("physical key is outside authored lane count")
        candidate=None
        # User-authored timing calibration compensates a delayed physical
        # key press, without accepting client supplied hit timestamps.
        judged_clock=clock-config["timing_calibration_ms"]
        for note in state["chart"]["notes"]:
            if state["judgements"][note["id"]] is not None:continue
            if note["lane"]!=lane:continue
            match=(kind=="tap" and note["kind"] in ("tap","mine")
                 or kind=="press" and note["kind"]=="hold"
                 or kind=="release" and note["kind"]=="hold"
                 or kind=="flick" and note["kind"]=="slide"
                 or kind=="chord" and note["kind"]=="chord" and note["partner"]==partner)
            if not match:continue
            at=note["at"]+state["chart"]["offset_ms"]
            target=at+note["duration"] if kind=="release" else at
            window=(config["release_window_ms"] if kind=="release" else
                    config["hit_window_ms"])
            if config["assist_mode"]=="expanded":window+=20
            if config["difficulty_curve"]=="staged":
                window=max(config["perfect_window_ms"],window-
                           (20*note["id"]//max(1,state["chart"]["beats"])))
            elif config["difficulty_curve"]=="dynamic" and state["combo"]>=config["combo_interval"]:
                window=max(config["perfect_window_ms"],window-10)
            if abs(judged_clock-target)<=window:
                candidate=note;break
        if candidate is None:
            state["stray"]+=1
            state["combo"]=0
            if state["stray"]%config["stray_interval"]==0:
                state["health"]=max(0,state["health"]-config["stray_health"])
                if config["auto_fail_on_stray"] and not config["practice_mode"]:
                    state["failed"]=True
                    state["reason"]="original_excessive_mashing_fail"
            events.append("unmatched_real_time_original_input")
        else:
            at=candidate["at"]+state["chart"]["offset_ms"]
            if candidate["kind"]=="mine":
                state["judgements"][candidate["id"]]="mine_hit"
                state["mines_hit"]+=1
                state["health"]=max(0,state["health"]-config["mine_damage"])
                state["combo"]=0
                events.append("original_hazard_mine_triggered_by_actual_key")
            elif kind=="press":
                if str(candidate["id"]) in state["pressed"]:
                    raise RhythmActionError("cannot start same physical note hold twice")
                grade=_quality(abs(judged_clock-at),config)
                if grade is None:
                    state["stray"]+=1
                    events.append("unmatched_real_time_original_input")
                else:
                    state["pressed"][str(candidate["id"])]=grade
                    state["held"].append(candidate["id"])
                    events.append("original_hold_key_physically_pressed")
            elif kind=="release":
                grade=state["pressed"].get(str(candidate["id"]))
                if grade is None:
                    raise RhythmActionError("hold release requires a previously authenticated key press")
                end=at+candidate["duration"]
                release_quality=_quality(abs(judged_clock-end),config)
                if abs(judged_clock-end)>min(config["release_window_ms"],
                                         config["sustain_tolerance_ms"]) or release_quality is None:
                    raise RhythmActionError("real held note needs an accurately timed release")
                del state["pressed"][str(candidate["id"])]
                state["held"].remove(candidate["id"])
                grades=("perfect","great","good")
                quality=grades[max(grades.index(grade),grades.index(release_quality))]
                _score(state,config,candidate,quality,events)
            else:
                grade=_quality(abs(judged_clock-at),config)
                if grade is None:
                    raise RhythmActionError("rhythmic hit outside playable timing window")
                _score(state,config,candidate,grade,events)
        if state["health"]==0 and config["fail_mode"]=="health" and not config["practice_mode"]:
            state["failed"]=True
            state["reason"]="original_rhythm_input_health_exhausted"
    state["turn"]+=1
    state["events"]=events
    return events


__all__=["LANES","KINDS","ACTIONS","RhythmActionError",
         "default_layout","normalize_layout","start","apply_scene","step"]
