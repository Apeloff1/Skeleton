"""Software contracts for typed-frame GPS, era chunk evidence, edits, telemetry, and recorder."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from skeleton.frontier_evidence import (
    ChunkTouch,
    EvidenceRejected,
    RecorderSessionError,
    SourceRef,
    TelemetryAdapter,
    TelemetryRejected,
    WorldEdit,
    adapter_for,
    adapters_for_era,
    content_digest,
    feed_typed_frames,
    ingest_sample,
    registered_adapters,
    registered_era_lanes,
    seal_world_edit,
    start,
    verify_edit_chain,
    verify_world_edit,
)
from skeleton.frontier_nav import (
    FrameFix,
    FrameGPSHub,
    GPSRejected,
    NavigationCursor,
    TypedFrame,
)
from skeleton.jeeves.game_engine_lab import ERA_PROFILES, EngineEra, list_engine_eras
from skeleton.jeeves.game_frontier_frame_coherence import (
    FrameChunk,
    FrameObject,
    advance_frame,
    bind_signed_gdd,
    digest,
)
from skeleton.jeeves.game_frontier_production import Vec3
from tests.test_game_frontier_position_frames import gdd


class _Frames:
    def __init__(self, frames):
        self._frames = tuple(frames)

    def frames(self):
        return iter(self._frames)


def _typed(frame: int, x: float, chunk: tuple[int, int]) -> TypedFrame:
    return TypedFrame(
        "snes",
        "16bit",
        frame,
        (FrameFix("hero", x, 0.0, 0.0, chunk_xy=chunk),),
    )


def _hub() -> FrameGPSHub:
    return FrameGPSHub(lanes=frozenset({("snes", "16bit")}))


def _signed():
    return bind_signed_gdd(gdd())


def _objects():
    return (
        FrameObject("hero", Vec3(1, 2, 0), Vec3(0, 0, 0), "a" * 64),
        FrameObject("island", Vec3(65, 0, 3), Vec3(0, 0, 0), "b" * 64),
    )


def _tamper_actor(frame):
    chunk = frame.chunks[0]
    obj = chunk.objects[0]
    moved = replace(obj, position=Vec3(obj.position.x + 100, obj.position.y, obj.position.z))
    objects = (moved, *chunk.objects[1:])
    partial = FrameChunk(chunk.frame, chunk.chunk_key, objects, "")
    updated = FrameChunk(chunk.frame, chunk.chunk_key, objects, digest(partial.payload()))
    candidate = replace(frame, chunks=(updated, *frame.chunks[1:]))
    return replace(candidate, receipt_digest=digest(candidate.payload()))


def _touch(chunk: tuple[int, int], shader: str = "void main(){}") -> ChunkTouch:
    return ChunkTouch(
        chunk,
        sources=(
            SourceRef("shader", "water", shader),
            SourceRef("light", "sun", {"lux": 1}),
            SourceRef("shadow", "blob", {"radius": 2}),
            SourceRef("terrain", "grass", "height"),
            SourceRef("weather", "rain", {"rate": 0.2}),
        ),
        vertices_before=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        vertices_after=((0.0, 0.0, 0.0), (1.0, 0.5, 0.0)),
    )


def test_position_outside_claimed_chunk_is_rejected():
    hub = _hub()
    with pytest.raises(GPSRejected, match="disagrees with chunk membership"):
        hub.accept_frames(_Frames([_typed(0, 40.0, (0, 0))]))
    assert hub.position("snes", "16bit", "hero") is None
    cursors = hub.accept_frames(_Frames([_typed(0, 10.0, (0, 0))]))
    assert cursors[0].frames == (0,)
    assert hub.position("snes", "16bit", "hero").x == 10.0


def test_streamed_navigation_cursor_is_ordered_and_gap_free():
    hub = _hub()
    cursors = hub.accept_frames(_Frames([_typed(0, 1.0, (0, 0)), _typed(1, 2.0, (0, 0)), _typed(2, 3.0, (0, 0))]))
    assert cursors[0].frames == (0, 1, 2)
    assert hub.stream_cursor("snes", "16bit").frames == (0, 1, 2)
    with pytest.raises(GPSRejected, match="navigation cursor"):
        NavigationCursor("snes", "16bit", (0, 2), "0" * 64)
    fresh = _hub()
    with pytest.raises(GPSRejected, match="navigation cursor gap"):
        fresh.accept_frames(_Frames([_typed(0, 1.0, (0, 0)), _typed(2, 2.0, (0, 0))]))
    assert fresh.stream_cursor("snes", "16bit").frames == ()
    assert fresh.proofs("snes", "16bit") == ()
    with pytest.raises(GPSRejected, match="navigation cursor gap"):
        fresh.accept_frames(_Frames([_typed(1, 1.0, (0, 0))]))


def test_submit_frame_gap_behavior_is_unchanged():
    hub = _hub()
    hub.submit_frame("snes", "16bit", 0, [])
    hub.submit_frame("snes", "16bit", 3, [])
    assert [proof.frame for proof in hub.proofs("snes", "16bit")] == [0, 3]


def test_accept_frames_rolls_back_when_a_later_frame_teleports():
    lanes = frozenset({("snes", "16bit")})
    hub = FrameGPSHub(lanes=lanes, max_speed_per_frame=1.0)
    fresh = FrameGPSHub(lanes=lanes, max_speed_per_frame=1.0)
    with pytest.raises(GPSRejected, match="teleported"):
        hub.accept_frames(_Frames([_typed(0, 0.0, (0, 0)), _typed(1, 100.0, (3, 0))]))
    assert hub.proofs("snes", "16bit") == fresh.proofs("snes", "16bit") == ()
    assert hub.stream_cursor("snes", "16bit") == fresh.stream_cursor("snes", "16bit")
    assert hub.position("snes", "16bit", "hero") is None


def test_every_registered_era_has_an_adapter_and_unknown_era_is_rejected():
    signed = _signed()
    adapters = registered_adapters()
    assert set(adapters) == set(EngineEra)
    assert len(adapters) == len(list_engine_eras()) == len(ERA_PROFILES)
    assert set(registered_era_lanes()) == {("engine", era.value) for era in EngineEra}
    hub = FrameGPSHub(lanes=registered_era_lanes())
    for era in EngineEra:
        adapter = adapter_for(era)
        assert adapter.era is era
        assert adapters_for_era(era)[0].era == era.value
        frame = advance_frame(frame_index=0, fps=60, gdd=signed, objects=_objects())
        evidence = adapter.emit(frame, signed)
        assert evidence["verifier_a"] is True and evidence["verifier_b"] is True
        assert evidence["source_frame_digest"] == frame.receipt_digest
        assert evidence["era"] == era.value
        assert [row["chunk_xy"] for row in evidence["chunk_evidence"]["receipts"]] == [
            list(chunk.chunk_key) for chunk in frame.chunks
        ]
        cursors = feed_typed_frames(hub, era, [frame])
        assert cursors[0].frames == (0,)
        assert hub.position("engine", era.value, "hero").x == 1
    with pytest.raises(EvidenceRejected, match="unknown era"):
        adapter_for("not_a_registered_era")
    with pytest.raises(EvidenceRejected, match="missing frame"):
        adapter_for(EngineEra.MODERN).emit(None, signed)
    with pytest.raises(EvidenceRejected, match="missing frame"):
        feed_typed_frames(hub, EngineEra.MODERN, [None])


def test_verifier_b_fails_when_one_actor_leaves_its_chunk():
    signed = _signed()
    frame = advance_frame(frame_index=0, fps=60, gdd=signed, objects=_objects())
    adapter = adapter_for(EngineEra.MODERN)
    assert adapter.verify(frame, signed) == (True, True)
    tampered = _tamper_actor(frame)
    content_ok, topology_ok = adapter.verify(tampered, signed)
    assert content_ok is True
    assert topology_ok is False
    with pytest.raises(EvidenceRejected, match="topology=False"):
        adapter.emit(tampered, signed)


def test_edit_receipt_covers_only_the_touched_chunk():
    edit = WorldEdit("move-origin", (_touch((0, 0)),))
    receipt = seal_world_edit(edit)
    assert receipt["chunk_ids"] == [[0, 0]]
    assert [row["chunk_id"] for row in receipt["receipts"]] == [[0, 0]]
    assert all(row["chunk_id"] != [3, 3] for row in receipt["receipts"])
    covered = receipt["receipts"][0]
    for kind in ("shader", "light", "shadow", "terrain", "weather", "vertex_diff"):
        assert kind in covered
    assert covered["vertex_diff"]["moved"] == [1]
    assert verify_world_edit(receipt, edit) is True


def test_chained_edit_receipt_rejects_a_forged_predecessor():
    first_edit = WorldEdit("first", (_touch((0, 0)),))
    first = seal_world_edit(first_edit)
    second_edit = WorldEdit("second", (_touch((0, 0), shader="void next(){}"),))
    second = seal_world_edit(second_edit, previous=first)
    forged = copy.deepcopy(first)
    forged["previous_edit_id"] = "injected"
    body = {key: value for key, value in forged.items() if key != "receipt_digest"}
    forged["receipt_digest"] = content_digest(body)
    assert forged["receipt_digest"] != first["receipt_digest"]
    assert verify_world_edit(second, second_edit, predecessor=forged) is False
    assert verify_world_edit(second, second_edit, predecessor=first) is True
    other = seal_world_edit(WorldEdit("elsewhere", (_touch((3, 3)),)))
    assert verify_edit_chain([other, second], [WorldEdit("elsewhere", (_touch((3, 3)),)), second_edit]) is False
    assert verify_edit_chain([first, second], [first_edit, second_edit]) is True
    assert [3, 3] not in second["chunk_ids"]


def test_telemetry_schema_rejects_extra_fields_and_missing_frame_index():
    collision = TelemetryAdapter("collision", EngineEra.SHADER)
    good = {
        "chunk_id": (0, 0),
        "frame_index": 4,
        "normal": [0.0, 1.0, 0.0],
        "force": [0.0, 9.0, 0.0],
    }
    sealed = ingest_sample(collision, good)
    assert sealed["chunk_id"] == [0, 0]
    assert sealed["frame_index"] == 4
    extra = dict(good)
    extra["surprise"] = 1
    with pytest.raises(TelemetryRejected, match="unknown fields"):
        ingest_sample(collision, extra)
    missing = {key: value for key, value in good.items() if key != "frame_index"}
    with pytest.raises(TelemetryRejected, match="missing frame index"):
        ingest_sample(collision, missing)
    lighting = ingest_sample(
        TelemetryAdapter("lighting", EngineEra.HD),
        {"chunk_id": [1, 2], "frame_index": 1, "luminance": 12.0, "light_ids": ["sun"]},
    )
    audio = ingest_sample(
        TelemetryAdapter("audio", EngineEra.OPEN_WORLD),
        {"chunk_id": [1, 2], "frame_index": 1, "rms_db": -12.0, "bus": "sfx"},
    )
    lod = ingest_sample(
        TelemetryAdapter("mesh_lod", EngineEra.MODERN),
        {"chunk_id": [1, 2], "frame_index": 1, "lod": 2, "triangles": 400},
    )
    assert lighting["channel"] == "lighting"
    assert audio["parameters"]["bus"] == "sfx"
    assert lod["parameters"]["lod"] == 2
    with pytest.raises(TelemetryRejected, match="unknown era"):
        TelemetryAdapter("audio", "unregistered-era")


def test_recorder_start_requires_save_slot_and_signed_scene():
    scene = "ab" * 32
    with pytest.raises(RecorderSessionError):
        start(save_slot_id=None, signed_scene_id=scene)
    with pytest.raises(RecorderSessionError):
        start(save_slot_id="slot-1", signed_scene_id=None)
    with pytest.raises(RecorderSessionError):
        start()
    for bad_scene in ("", "ab", "AB" * 32):
        with pytest.raises(RecorderSessionError):
            start(save_slot_id="slot-1", signed_scene_id=bad_scene)
    session = start(save_slot_id="slot-1", signed_scene_id=scene)
    manifest = session.manifest()
    assert manifest["save_slot_id"] == "slot-1"
    assert manifest["signed_scene_id"] == scene
    assert manifest["state"] == "recording"
    assert manifest["installer_and_hardware_activation"] == "open"
    assert session.stop()["state"] == "stopped"
    resumed = session.resume()
    assert resumed["state"] == "recording"
    assert resumed["events"] == ["start", "stop", "resume"]
