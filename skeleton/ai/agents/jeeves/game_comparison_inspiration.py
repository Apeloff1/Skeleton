"""Original media/gameplay inspiration pack from verified comparative study evidence.

Creates real SVG illustrations, synthesized PCM WAV, editable multi-angle
cinematic shot JSON, and original mechanics/world/camera/gameplay documents.
The inputs are source receipts and optionally reviewed *abstract* design notes.
Never reads or copies source ROM frames, audio, protected game assets or story.
No training or weight promotion is implied by generated creative content.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import random
import re
import struct
import wave
from collections import defaultdict
from collections.abc import Mapping
from html import escape
from typing import Any

from .game_comparison_schema import digest

SCHEMA="skeleton.game.comparison_original_inspiration.v1"
STAGES=("earlier","middle","after")
GENRES=("adventure","platformer","puzzle","racing","simulation","combat","strategy","rhythm","sandbox","exploration")
MAX_ASSET_BYTES=2*1024*1024

_GENRE_RULES={
    "adventure":("dialogue_choice","navigation","quest_prerequisites","reputation"),
    "platformer":("movement_acceleration","jump_arc","surface_friction","checkpointing"),
    "puzzle":("state_transitions","reversible_actions","hint_delay","constraint_variation"),
    "racing":("acceleration","turning_radius","route_choice","weather_effects"),
    "simulation":("resources","day_cycle","ecology","npc_schedules"),
    "combat":("attack_windup","defense_window","collision","ability_cooldown"),
    "strategy":("line_of_sight","resource_tradeoff","pathfinding","turn_cost"),
    "rhythm":("beat_windows","input_lag","tempo_changes","audio_feedback"),
    "sandbox":("crafting","object_physics","systemic_interaction","world_persistence"),
    "exploration":("landmarks","navigation","discovery","world_topology"),
}
_SHOTS=("wide_establishing","high_crane","low_tracking","side_dolly","orbit","over_shoulder","detail_insert","reveal_pan","top_down")
_COLORS=(
    ("#111e32","#236c82","#edbb75","#e8f4ec"),
    ("#201b3a","#9b4d83","#efbb81","#eee2db"),
    ("#0e3131","#317d73","#efcb83","#f9f2dd"),
    ("#25233b","#637cad","#f3b0a1","#efe9ef"),
)


class InspirationError(ValueError):
    """Requested original asset synthesis lacks a lawful, finite evidence scope."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()


def _identity(report: Mapping[str, Any], ids: list[str]) -> tuple[str,list[dict[str, Any]]]:
    if (not isinstance(report,dict)
        or report.get("schema_version")!="skeleton.game.comparative_study_result.v1"
        or digest({k:v for k,v in report.items() if k!="result_sha256"})!=report.get("result_sha256")):
        raise InspirationError("Original media generation requires an intact canonical native study result")
    if (not isinstance(ids,list) or not 2<=len(ids)<=30
        or any(type(x) is not str for x in ids) or len(set(ids))!=len(ids)):
        raise InspirationError("Select 2 through 30 distinct actual observed comparison game IDs")
    games=report.get("games")
    if not isinstance(games,dict):
        raise InspirationError("Native game evidence is unavailable")
    observations=[]
    for identity in ids:
        row=games.get(identity)
        if not isinstance(row,dict) or row.get("status")!="actual_native_observations_captured":
            raise InspirationError("Inspiration source requires completed actual native observations")
        stages=row.get("phases")
        if not isinstance(stages,dict) or any(
            not isinstance(stages.get(phase),dict)
            or stages[phase].get("source")!="actual_isolated_libretro"
            or type(stages[phase].get("evidence_sha256")) is not str
            for phase in STAGES
        ):
            raise InspirationError("Native stage receipt is absent from one selected game")
        observations.append({
            "game_id":identity,
            "entry_sha256":row["source_sha256"],
            "core_sha256":row["core_sha256"],
            "stage_receipts":[stages[phase]["evidence_sha256"] for phase in STAGES],
            "source_asset_bytes_admitted":0,
        })
    return report["result_sha256"],observations


def _original_vector(stage: str, rng: random.Random, palette: tuple[str,...],
                     motif: str) -> bytes:
    # Standalone authored SVG geometry. No original game pixels loaded or copied.
    background,mid,bright,light=palette
    shapes=[f'<rect width="512" height="288" fill="{background}"/>',
            f'<path d="M0 214 Q130 135 250 201 T512 177 V288 H0Z" fill="{mid}" opacity=".68"/>']
    count={"earlier":14,"middle":23,"after":36}[stage]
    for i in range(count):
        x=rng.randrange(12,500);y=rng.randrange(18,266)
        width=rng.randrange(8,57);height=rng.randrange(8,51)
        opacity=round(rng.uniform(.22,.81),2)
        color=bright if i%3 else light
        if i%4==0:
            shapes.append(f'<circle cx="{x}" cy="{y}" r="{max(3,width//3)}" fill="{color}" opacity="{opacity}"/>')
        elif i%4==1:
            shapes.append(f'<path d="M{x} {y} l{width} {-height//2} l{width//2} {height} Z" fill="{color}" opacity="{opacity}"/>')
        else:
            shapes.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="4" fill="{color}" opacity="{opacity}"/>')
    # Theme is explicitly a user-authored brief and encoded for XML.
    label=escape(motif[:90],quote=True)
    shapes.append(f'<text x="24" y="268" font-family="sans-serif" font-size="15" fill="{light}">Original {stage} • {label}</text>')
    svg=('<?xml version="1.0" encoding="utf-8"?>\n'
         '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="288" viewBox="0 0 512 288">'
         +''.join(shapes)+'</svg>')
    data=svg.encode()
    if len(data)>MAX_ASSET_BYTES:
        raise InspirationError("Original vector asset exceeded bounded 2 MiB content limit")
    return data


def _original_wav(stage: str, seed: int, genre: str) -> tuple[bytes,dict[str, Any]]:
    rate=16000
    duration={"earlier":3,"middle":4,"after":5}[stage]
    rng=random.Random(seed^int.from_bytes(hashlib.sha256((stage+genre).encode()).digest()[:8],"big"))
    # Pentatonic/floating modes and tempo from independent seeded procedural composition.
    scale=(0,3,5,7,10,12,15,17,19)
    base=rng.choice((110.0,123.47,130.81,146.83,164.81,174.61))
    tempo=rng.randrange(84,161)
    steps=[rng.choice(scale) for _ in range(duration*3)]
    notes=[]
    for i,interval in enumerate(steps):
        hz=base*2**(interval/12)
        notes.append({"beat":i,"frequency_hz":round(hz,3),"length_beats":1,"source":"procedural_not_reconstructed"})
    out=io.BytesIO()
    with wave.open(out,"wb") as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(rate)
        buf=bytearray()
        length=rate*duration
        beat_seconds=60/tempo
        for pos in range(length):
            t=pos/rate
            n=min(len(steps)-1,int(t/beat_seconds))
            elapsed=t-n*beat_seconds
            hz=base*2**(steps[n]/12)
            attack=min(1,elapsed/.02)
            decay=math.exp(-3.1*elapsed/max(.12,beat_seconds))
            amplitude=0.14*attack*decay
            harmonic=(math.sin(2*math.pi*hz*t)+0.22*math.sin(4*math.pi*hz*t))
            sample=int(max(-32767,min(32767,amplitude*harmonic*32767)))
            buf+=struct.pack("<h",sample)
        wf.writeframes(bytes(buf))
    data=out.getvalue()
    return data,{
        "generation":"actual_procedural_pcm_waveform_no_source_melody",
        "duration_seconds":duration,"sample_rate":rate,"channels":1,
        "tempo_bpm":tempo,"notes":notes,
        "source_game_audio_reused":False,
        "music_quality_or_originality_audited_by_human":False,
    }


def _original_cinematic(stage: str, seed: int, brief: str) -> dict[str,Any]:
    rng=random.Random(seed+{"earlier":1,"middle":2,"after":3}[stage])
    count={"earlier":4,"middle":6,"after":9}[stage]
    timeline=[]
    clock=0.0
    for i in range(count):
        duration=round(rng.uniform(1.5,4.6),2)
        kind=_SHOTS[(i+rng.randrange(len(_SHOTS)))%len(_SHOTS)]
        direction=rng.choice(("left_to_right","right_to_left","push_forward","pull_back","vertical_reveal"))
        shot={
            "shot_id":f"{stage}_shot_{i+1:02d}",
            "start_seconds":round(clock,2),"duration_seconds":duration,
            "camera_angle":kind,"pan_to":direction,
            "zoom_start":round(rng.uniform(.88,1.15),3),
            "zoom_end":round(rng.uniform(.93,1.29),3),
            "camera_height_normalized":round(rng.random(),3),
            "cut_style":rng.choice(("cut","dissolve","match_motion")),
            "keyframes":[
                {"offset":0,"focus_x":round(rng.random(),3),"focus_y":round(rng.random(),3)},
                {"offset":duration,"focus_x":round(rng.random(),3),"focus_y":round(rng.random(),3)},
            ],
            "dialogue":"", "source_game_cinematic_reproduced":False,
        }
        timeline.append(shot);clock+=duration
    return {
        "schema_version":"skeleton.game.original_cutscene_draft.v1",
        "stage":stage,"creative_brief":brief,
        "duration_seconds":round(clock,2),"shots":timeline,
        "editable_3d_or_2d_camera_director_input":True,
        "actual_video_rendered":False,
        "licensed_character_assets_used":False,
    }


def _original_mechanics(stage: str, genre: str, selected: list[dict[str,Any]],
                        notes: list[dict[str,Any]]) -> dict[str,Any]:
    progression={"earlier":1,"middle":2,"after":3}[stage]
    mechanics=[]
    for i,name in enumerate(_GENRE_RULES[genre]):
        mechanics.append({
            "key":name,
            "authored_complexity_tier":min(4,1+(i+progression-1)//2),
            "state_inputs":["player_action","world_tick","original_scene_state"],
            "outcomes":["state_transition","observable_response","bounded_reward_signal"],
            "independent_measurement_required":True,
            "implemented_gameplay_code":False,
        })
    return {
        "schema_version":"skeleton.game.original_mechanics_draft.v1",
        "stage":stage,"genre":genre,
        "mechanics":mechanics,
        "interaction_axes":["movement","input","reaction","environment","consequence",
                            "npc","camera","audio","cutscene","timing","strategy"],
        "linked_observation_receipts":[
            {"game_id":row["game_id"],"stage_sha256":row["stage_receipts"][STAGES.index(stage)]}
            for row in selected
        ],
        "attributed_review_notes":[
            {
                "id":note["note_id"],"dimension":note["dimension"],
                "claim_type":note["claim_type"],
                "review_status":"locally_reviewed_not_independently_verified",
            }
            for note in notes[:64]
        ],
        "parameters_inferred_from_source_games":False,
        "production_gameplay_implemented":False,
        "training_weight_updates_applied":0,
    }


def build_original_inspiration_pack(
    report: Mapping[str,Any],*,game_ids:list[str],
    genre:str,creative_brief:str,author_seed:int=1,
) -> tuple[dict[str,bytes],dict[str,Any]]:
    if genre not in GENRES:
        raise InspirationError("Genre must be one of the declared original builder templates")
    if (type(creative_brief) is not str or not 4<=len(creative_brief)<=240
        or any(ord(c)<32 for c in creative_brief)):
        raise InspirationError("Original creative brief requires 4–240 printable characters")
    if type(author_seed) is not int or not 0<=author_seed<2**63:
        raise InspirationError("Original authoring seed exceeds finite generator bounds")
    source_sha,observations=_identity(report,game_ids)
    notes=[
        n for n in report.get("observer_notes",[])
        if n.get("knowledge_status")=="reviewed_observation_candidate"
        and n.get("review_status")=="reviewed"
        and set(n.get("game_ids",[])).issubset(set(game_ids))
        and n.get("evidence")
    ]
    outputs={}
    sections=[]
    counts=defaultdict(int)
    for stage in STAGES:
        stage_seed=int.from_bytes(hashlib.sha256(
            f"{source_sha}:{author_seed}:{stage}:{genre}".encode()
        ).digest()[:8],"big")
        palette=_COLORS[stage_seed%len(_COLORS)]
        vector=_original_vector(stage,random.Random(stage_seed),palette,creative_brief)
        wav,music_meta=_original_wav(stage,stage_seed,genre)
        cutscene=_original_cinematic(stage,stage_seed,creative_brief)
        mechanics=_original_mechanics(stage,genre,observations,notes)
        data={
            f"assets/{stage}_original.svg":vector,
            f"music/{stage}_original.wav":wav,
            f"cutscenes/{stage}_original.json":_canonical_bytes(cutscene),
            f"mechanics/{stage}_original.json":_canonical_bytes(mechanics),
        }
        for name,content in data.items():
            if not 0<len(content)<=MAX_ASSET_BYTES:
                raise InspirationError("Generated original file exceeds 2 MiB")
            outputs[name]=content
            counts[name.split("/")[0]]+=1
        sections.append({
            "stage":stage,
            "source_checkpoint_receipts":[row["stage_receipts"][STAGES.index(stage)] for row in observations],
            "generated_file_receipts":[
                {"path":name,"sha256":hashlib.sha256(content).hexdigest(),
                 "bytes":len(content),"origin":"new_deterministic_homebrew"}
                for name,content in sorted(data.items())
            ],
            "authored_music_metadata":music_meta,
            "cutscene_shot_count":len(cutscene["shots"]),
            "mechanic_count":len(mechanics["mechanics"]),
            "training_progress_claimed":False,
        })
    # Provenance graph and adversarial review tasks for Jeeves/Dragon.
    nodes=[]
    edges=[]
    for source in observations:
        nodes.append({"id":"game:"+source["game_id"],"kind":"observed_native_source",
                      "receipt_sha256":source["entry_sha256"]})
    for stage in sections:
        stage_id="stage:"+stage["stage"]
        nodes.append({"id":stage_id,"kind":"original_generation_stage",
                      "receipt_sha256":digest(stage)})
        for source in observations:
            edges.append({"from":"game:"+source["game_id"],"to":stage_id,
                          "relationship":"abstract_review_context_only"})
        for artifact in stage["generated_file_receipts"]:
            node_id="generated:"+artifact["path"]
            nodes.append({"id":node_id,"kind":"original_generated_artifact",
                          "receipt_sha256":artifact["sha256"]})
            edges.append({"from":stage_id,"to":node_id,
                          "relationship":"procedural_authoring_output"})
    review_dimensions=(
        "controller_response","accessibility","audiovisual_legibility",
        "originality_and_rights","cutscene_pacing","mechanic_consistency",
        "player_choice","npc_interactions","world_continuity",
        "audio_timing","hardware_budget","generalization_and_regression",
    )
    review_queue=[
        {"dimension":dimension,"status":"pending_independent_review",
         "evidence_refs":[source["stage_receipts"][idx]
                          for source in observations for idx in range(3)],
         "measured_gain":None,"llm_weights_updated":False}
        for dimension in review_dimensions
    ]
    packet={
        "knowledge_provenance_graph":{
            "schema_version":"skeleton.game.comparison_inspiration_dag.v1",
            "nodes":nodes,"edges":edges,
            "semantic_learning_claimed":False,
        },
        "adversarial_review_queue":review_queue,
        "schema_version":SCHEMA,
        "study_id":report["study_id"],
        "source_result_sha256":source_sha,
        "selected_game_receipts":observations,
        "author_seed":author_seed,
        "creative_brief":creative_brief,
        "genre":genre,
        "stages":sections,
        "generated_file_count":len(outputs),
        "generated_categories":dict(counts),
        "artifact_output_mode":"real_editable_svg_wav_storyboard_and_mechanics_draft",
        "source_game_rom_pixels_music_character_story_or_maps_copied":False,
        "independent_novelty_and_copyright_review_complete":False,
        "cutscene_video_rendered":False,
        "gameplay_source_compiled":False,
        "large_language_model_training_performed":False,
        "weights_or_parameters_promoted":False,
    }
    packet["pack_receipt_sha256"]=digest(packet)
    return outputs,packet
