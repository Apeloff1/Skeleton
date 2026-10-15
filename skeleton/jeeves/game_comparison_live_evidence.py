"""Offline verification of live multi-emulator input/frame/audio receipts.

Replayable raw controller vectors remain user-owned local JSON. This verifier
checks every hash link including reset generations, input vector hashes,
step counters, and source/core lineage. It does not certify native hardware,
legal rights, gameplay quality or independently signed execution.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .game_comparison_schema import digest
from .game_emulator_host import _controls

SCHEMA="skeleton.game.live_evidence_verification.v1"
EXPORT="skeleton.game.live_evidence_export.v1"


class LiveEvidenceError(ValueError):
    """Native step/reset receipts or replay input have changed or are incomplete."""


def verify_live_evidence(packet: Mapping[str,Any]) -> dict[str,Any]:
    if not isinstance(packet,dict) or packet.get("schema_version")!=EXPORT:
        raise LiveEvidenceError("Live evidence requires a canonical exported native session")
    lanes=packet.get("lanes")
    if not isinstance(lanes,dict) or not 2<=len(lanes)<=10:
        raise LiveEvidenceError("Live evidence requires 2–10 actually selected native lanes")
    rows=[]
    for game_id,lane in lanes.items():
        if type(game_id) is not str or not isinstance(lane,dict) or lane.get("game_id")!=game_id:
            raise LiveEvidenceError("Native evidence source game IDs differ")
        source=lane.get("source_media_sha256")
        native_source=lane.get("native_content_digest",source)
        core_sha=lane.get("core_sha256")
        if (type(core_sha) is not str or len(core_sha)!=64
            or any(ch not in "0123456789abcdef" for ch in core_sha)):
            raise LiveEvidenceError("Native core binary SHA-256 is absent or invalid")
        if (type(source) is not str or len(source)!=64 or
            type(native_source) is not str or len(native_source)!=64 or
            any(ch not in "0123456789abcdef" for ch in native_source)):
            raise LiveEvidenceError("Original game source or native bundle digest is not recorded")
        initial=lane.get("initial_chain_sha256")
        env_sha=lane.get("native_environment_sha256")
        seed=lane.get("seed")
        if type(env_sha) is not str or len(env_sha)!=64 or type(seed) is not int:
            raise LiveEvidenceError("Native worker and reset-seed identity is not recorded")
        expect=digest([
            "skeleton.game.live_comparison.v1",packet["study_digest"],game_id,
            source,env_sha,packet["registry_digest"],"reset",seed,
        ])
        if initial!=expect:
            raise LiveEvidenceError("First native state hash differs from the initial approved environment")
        events=lane.get("native_events")
        if not isinstance(events,list) or len(events)>292:
            raise LiveEvidenceError("Native event recording exceeds the 256-step + 4-reset lifetime cap")
        reset_generation=0
        disc_changes=0
        disc_image=None
        host_disc_chain=digest(["native_disc_control",env_sha])
        episode_step=0
        steps=0
        previous=initial
        episodes=[[]]
        for row in events:
            if not isinstance(row,dict) or set(row)!={"event_kind","receipt","receipt_sha256"}:
                raise LiveEvidenceError("Unexpected live evidence event shape")
            payload=row["receipt"]
            if not isinstance(payload,dict):
                raise LiveEvidenceError("Native event has no immutable input/frame receipt")
            original={key:value for key,value in payload.items() if key!="receipt_sha256"}
            if digest(original)!=row["receipt_sha256"] or payload.get("receipt_sha256")!=row["receipt_sha256"]:
                raise LiveEvidenceError("Native event hash changed after capture")
            if payload.get("previous_chain_sha256")!=previous or payload.get("game_id")!=game_id:
                raise LiveEvidenceError("Native events are no longer chained to the correct game")
            if row["event_kind"]=="native_step":
                if (payload.get("schema_version")!="skeleton.game.live_native_step_receipt.v1"
                    or payload.get("index")!=steps+1
                    or payload.get("episode_step")!=episode_step+1
                    or payload.get("reset_generation")!=reset_generation
                    or payload.get("source_content_sha256")!=source
                    or payload.get("core_sha256")!=core_sha):
                    raise LiveEvidenceError("Actual native episode step index or source was modified")
                controls=payload.get("controller_ports")
                if not isinstance(controls,list) or not 1<=len(controls)<=4:
                    raise LiveEvidenceError("Replayable native controller tape is missing")
                try:
                    normalized=_controls(controls)
                except (ValueError,TypeError) as exc:
                    raise LiveEvidenceError("Native input vector violates bounded host schema") from exc
                if normalized!=controls or digest(controls)!=payload.get("input_vector_sha256"):
                    raise LiveEvidenceError("Native controller vector differs from actual captured digest")
                for sha_name in ("frame_sha256","pcm_sha256","transition_sha256"):
                    value=payload.get(sha_name)
                    if type(value) is not str or len(value)!=64:
                        raise LiveEvidenceError("Native video/audio/transition evidence identity was removed")
                steps+=1
                episode_step+=1
                episodes[-1].append(controls)
            elif row["event_kind"]=="native_disc_swap":
                required={
                    "schema_version", "game_id", "index", "episode_step",
                    "reset_generation", "source_content_sha256", "native_content_digest", "core_sha256",
                    "native_host_disc_receipt_sha256", "native_host_disc_receipt",
                    "previous_image_index", "selected_image_index",
                    "registered_disc_count", "interface_version",
                    "previous_chain_sha256", "native_frame_advanced",
                    "receipt_sha256",
                }
                if (set(payload)!=required
                    or payload["schema_version"]!="skeleton.game.live_native_disc_swap_receipt.v1"
                    or payload["index"]!=disc_changes+1
                    or payload["episode_step"]!=episode_step
                    or payload["reset_generation"]!=reset_generation
                    or payload["source_content_sha256"]!=source
                    or payload["native_content_digest"]!=native_source
                    or payload["core_sha256"]!=core_sha
                    or payload["native_frame_advanced"] is not False):
                    raise LiveEvidenceError("Native disc event counters or source differ")
                count=payload["registered_disc_count"]
                old=payload["previous_image_index"]
                new=payload["selected_image_index"]
                if (type(count) is not int or not 2<=count<=32
                    or type(old) is not int or not 0<=old<count
                    or type(new) is not int or not 0<=new<count
                    or new==old
                    or (disc_image is not None and old!=disc_image)
                    or type(payload["interface_version"]) is not int
                    or payload["interface_version"] not in (0,1)):
                    raise LiveEvidenceError("Disc swap did not select a valid distinct preloaded image")
                host=payload["native_host_disc_receipt"]
                host_fields={
                    "schema_version", "core_sha256", "content_digest",
                    "environment_digest", "event_index", "episode_step_before_swap",
                    "previous_image_index", "selected_image_index", "registered_disc_count",
                    "interface_version", "previous_disc_chain_sha256",
                    "prior_game_transition_sha256", "rendered_frame_after_swap",
                    "receipt_sha256",
                }
                if not isinstance(host,dict) or set(host)!=host_fields:
                    raise LiveEvidenceError("Native host media provenance receipt is missing")
                host_data={k:v for k,v in host.items() if k!="receipt_sha256"}
                if (host["schema_version"]!="skeleton.game.native_disc_swap_receipt.v1"
                    or host["core_sha256"]!=core_sha
                    or host["content_digest"]!=native_source
                    or host["environment_digest"]!=env_sha
                    or host["event_index"]!=disc_changes+1
                    or host["episode_step_before_swap"]!=episode_step
                    or host["previous_image_index"]!=old
                    or host["selected_image_index"]!=new
                    or host["registered_disc_count"]!=count
                    or host["interface_version"]!=payload["interface_version"]
                    or host["previous_disc_chain_sha256"]!=host_disc_chain
                    or host["rendered_frame_after_swap"] is not False
                    or digest(host_data)!=host["receipt_sha256"]
                    or host["receipt_sha256"]!=payload["native_host_disc_receipt_sha256"]):
                    raise LiveEvidenceError("Native disc host receipt chain diverged")
                disc_changes+=1
                if disc_changes>32:
                    raise LiveEvidenceError("Native disc swap lifetime exceeded 32 events")
                disc_image=new
                host_disc_chain=host["receipt_sha256"]
            elif row["event_kind"]=="native_reset":
                if (payload.get("schema_version")!="skeleton.game.live_native_reset_receipt.v1"
                    or payload.get("reset_generation")!=reset_generation+1
                    or payload.get("source_content_sha256")!=source):
                    raise LiveEvidenceError("Native reset generation was mutated")
                reset_generation+=1
                disc_image=None
                episode_step=0
                episodes.append([])
            else:
                raise LiveEvidenceError("Unknown native event kind")
            previous=row["receipt_sha256"]
        if (lane.get("final_chain_sha256")!=previous
            or lane.get("step_count")!=steps
            or lane.get("reset_count")!=reset_generation
            or lane.get("disc_change_count",0)!=disc_changes):
            raise LiveEvidenceError("Final native evidence count/root differs from committed events")
        rows.append({
            "game_id":game_id,"core_id":lane["core_id"],
            "core_sha256":core_sha,"target_id":lane["target_id"],
            "native_events_verified":len(events),
            "native_input_steps_verified":steps,
            "native_resets_verified":reset_generation,
            "native_disc_swaps_verified":disc_changes,
            "last_native_disc_chain_sha256":host_disc_chain,
            "episode_tape_lengths":[len(ep) for ep in episodes],
            "initial_chain_sha256":initial,
            "final_chain_sha256":previous,
            "replayable_controller_tapes":episodes,
            "locally_verified":True,
            "independently_attested_native_run":False,
        })
    result={
        "schema_version":SCHEMA,
        "study_id":packet["study_id"],
        "study_digest":packet["study_digest"],
        "registry_digest":packet["registry_digest"],
        "game_count":len(rows),
        "total_real_reported_native_steps":sum(x["native_input_steps_verified"] for x in rows),
        "total_native_reset_events":sum(x["native_resets_verified"] for x in rows),
        "total_native_disc_swaps_verified":sum(x["native_disc_swaps_verified"] for x in rows),
        "games":rows,
        "correctness_claim":"Checks a self-contained hash chain and exact raw controller records, not independently signed hardware execution",
        "model_weights_changed":False,
    }
    result["verification_sha256"]=digest(result)
    return result
