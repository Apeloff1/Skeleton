"""Runtime game-map GPS from durable *observed* physics frame receipts.

This is the bridge from Godot/native actor observations to a fictional game's
beacon navigation and GDD-linked positioning. It never reads phone GPS,
system location or Earth geodetic coordinates. The source journal must replay
successfully before this report can be produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .game_frontier_frame_coherence import digest, FrameReceipt
from .game_frontier_native_capture import NativeObservationError
from .game_frontier_production import Vec3
from .game_frontier_receipt_journal import FrameReceiptJournal, FrameJournalError
from .game_frontier_virtual_navigation import (
    GameMap, VirtualBeacon, VirtualSurveyControl, VirtualSurveySighting,
    VirtualNavigationRequest, compose_virtual_navigation, VirtualPositionError,
)


class RuntimeGameNavigationError(ValueError):
    pass


def _actor(frame: FrameReceipt, actor_id: str) -> Vec3:
    matched=[o.position for ch in frame.chunks for o in ch.objects
             if o.entity_id==actor_id]
    if len(matched)!=1:
        raise RuntimeGameNavigationError("authoritative frame missing actor")
    return matched[0]


def _candidate(request: VirtualNavigationRequest,
               position: Vec3) -> VirtualNavigationRequest:
    from dataclasses import replace
    return replace(request, actor_truth=position)


def inspect_runtime_virtual_gps(
    journal: FrameReceiptJournal, request: VirtualNavigationRequest, *,
    frame_index: int,
) -> dict:
    """Replay signed journal then triangulate fully fictional current position.

    Uses exact source frame actor, not a user's actual device location. A/B
    frame checks, native sample contents and independent chunk source proof
    are required; if the engine hasn't supplied a sample, refuse to label
    this output runtime positioning.
    """
    if (not isinstance(journal,FrameReceiptJournal) or
        not isinstance(request,VirtualNavigationRequest) or
        type(frame_index) is not int or frame_index<0 or
        request.world.world_id!=journal.gdd.project_id):
        raise RuntimeGameNavigationError("valid same-project game runtime positioning required")
    try:
        receipt=journal.replay(through=frame_index)
        frame,chunk_evidence=journal.load(frame_index)
        native=journal.native_sample(frame_index)
        native_chunks=journal.native_chunk_evidence(frame_index)
        if not isinstance(native,dict) or not isinstance(native_chunks,dict):
            raise RuntimeGameNavigationError("native physics sample not available for game map GPS")
        if not any(o.get("id")==request.actor_id for o in native["actors"]):
            raise RuntimeGameNavigationError("selected avatar absent from native observation")
        previous=journal.load(frame_index-1)[0] if frame_index else None
        before_prior=journal.load(frame_index-2)[0] if frame_index>1 else None
        previous_native=journal.native_sample(frame_index-1) if frame_index else None
        previous_navigation=None
        if previous is not None:
            if previous_native is None:
                raise RuntimeGameNavigationError("previous runtime GPS native sample absent")
            previous_navigation=compose_virtual_navigation(
                _candidate(request,_actor(previous,request.actor_id)),
                frame=previous,gdd=journal.gdd,previous_frame=before_prior)
        current=compose_virtual_navigation(
            _candidate(request,_actor(frame,request.actor_id)),
            frame=frame,gdd=journal.gdd,previous_frame=previous,
            previous_navigation=previous_navigation)
    except (FrameJournalError,NativeObservationError,VirtualPositionError,
            KeyError,ValueError) as error:
        if isinstance(error,RuntimeGameNavigationError):
            raise
        raise RuntimeGameNavigationError(
            "runtime GPS requires fully replayable native and GDD source frames"
        ) from error
    result={
        "schema":"skeleton.game.runtime_virtual_gps.v1",
        "frame":frame_index,
        "world_id":request.world.world_id,
        "realm_id":request.world.realm_id,
        "actor_id":request.actor_id,
        "simulated_position":current,
        "signed_gdd_digest":journal.gdd.source_digest,
        "verified_frame_digest":frame.receipt_digest,
        "frame_chunk_evidence_digest":chunk_evidence["receipt_digest"],
        "native_physics_digest":digest(native),
        "native_chunk_evidence_digest":native_chunks["receipt_digest"],
        "previous_frame_verified":previous is None or (
            previous_navigation is not None),
        "verified_replay_frames":receipt["verified_frames"],
        "device_location_used":False,
        "authority":"observed_game_actor_fictional_navigation_candidate",
    }
    result["receipt_digest"]=digest(result)
    return result
