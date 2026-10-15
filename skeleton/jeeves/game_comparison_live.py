"""Explicit operator-owned, loopback-only live comparative libretro sessions.

Only pre-approved game rows from a validated 30-game study may be started.
Two to ten live lanes; actual native screen frames; <=4096 steps/lane,
independent errors, bounded receipt history, no ROM bytes in HTTP responses.
No model weights/Dragon custody are changed. Browser controls never execute code.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Mapping

from .game_comparison_schema import ComparativeStudyError, digest, plan_study, validate_study
from .game_comparison_controllers import controller_layout_for_target
from .game_comparison_media import prepare_comparison_media
from .game_comparison_studio import _storage_waves
from .game_emulator_host import _controls, create_emulator_environment
from .game_emulator_timing import normalize_timing, native_execution_budget
from .game_emulator_catalog import GameEmulatorRegistry

SCHEMA = "skeleton.game.live_comparison.v1"
MAX_LANES = 10
MAX_STEPS_PER_LANE = 4096
MAX_RESET_PER_LANE = 4
MAX_CHECKPOINTS_PER_LANE = 2
MAX_REWINDS_PER_LANE = 2
MAX_REQUEST_LANES = 10
MAX_BURST_STEPS = 8
MAX_TIMING_EVENTS = 32
MAX_INSPECTION_EVENTS = 24
MAX_IMAGE_URI = 320_000
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


class LiveComparisonError(ValueError):
    """Invalid authorization, bounded execution or telemetry state."""


def _preview(env: Any) -> dict[str, Any]:
    frame = env._frame
    if not isinstance(frame, dict):
        raise LiveComparisonError("Native libretro has no actual video/audio frame")
    preview = env.preview()
    uri = preview.get("data_uri") if isinstance(preview, dict) else None
    if not isinstance(uri, str) or not uri.startswith("data:image/png;base64,") or len(uri) > MAX_IMAGE_URI:
        uri = None
    audio=preview.get("audio") if isinstance(preview,dict) else None
    pcm=None
    if isinstance(audio,dict):
        sample=audio.get("samples_base64")
        frames=audio.get("sample_frames")
        rate=audio.get("sample_rate")
        channels=audio.get("channels")
        if (type(sample) is str and len(sample)<=100000
            and type(frames) is int and 0<=frames<=16384
            and type(rate) in (int,float) and 8000<=rate<=384000
            and channels==2):
            pcm={
                "format":"s16le_stereo","sample_frames":frames,
                "sample_rate":rate,"samples_base64":sample,
                "sample_sha256":audio.get("sample_digest"),
                "source_native_pcm_sha256":audio.get("source_digest"),
                "sample_duration_seconds":round(frames/rate,4),
                "actual_native_audio_not_original_music":True,
            }
    return {
        "image_data_uri": uri,
        "image_unavailable": uri is None,
        "recent_native_pcm_preview":pcm,
        "frame_sha256": frame["pixel_sha256"],
        "audio_sha256": frame["audio_sha256"],
        "audio_frames": frame["audio_frames"],
        "frame_calls": frame["runs"],
        "native_fps": frame.get("fps"),
        "video_callbacks": frame["video_callbacks"],
        "width": frame["width"],
        "height": frame["height"],
        "rotation": frame["rotation"],
        "note": "Actual installed libretro native frame; image omitted if >320000 URI chars",
    }


@dataclass
class _Lane:
    game: dict[str, Any]
    env: Any
    content_digest: str
    native_content_digest: str
    controls_digest: str
    chain: str
    first_chain: str
    step_count: int = 0
    total_steps: int = 0
    reset_count: int = 0
    disc_change_count: int = 0
    timing_change_count: int = 0
    inspection_count: int = 0
    timing_mode: str = "normal"
    timing_factor: int = 1
    last_burst_wall_ms: float | None = None
    last_burst_native_fps: float | None = None
    last_burst_receipted_frames: int = 0
    receipts: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    checkpoint: dict[str, Any] | None = None
    checkpoint_id: int = 0
    checkpoint_episode_step: int = 0
    checkpoint_reset_generation: int = 0
    rewind_count: int = 0
    status: str = "running"
    error_class: str | None = None


class LiveComparison:
    """Own actual native workers, never a pretend HTML-only gameplay state."""

    def __init__(
        self, manifest: Mapping[str, Any], *,
        batch_index: int, game_ids: list[str] | None = None,
        max_steps: int = MAX_STEPS_PER_LANE,
        timeout_seconds: float = 5.0,
    ):
        if type(batch_index) is not int or type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS_PER_LANE:
            raise LiveComparisonError("Live session requires one bounded selected 30-game study cohort")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0.1 <= timeout_seconds <= 30:
            raise LiveComparisonError("Native command timeout is outside approved bounds")
        self.model = validate_study(dict(manifest))
        self.plan = plan_study(self.model)
        if batch_index < 0 or batch_index >= len(self.plan["batches"]):
            raise LiveComparisonError("Selected comparative study cohort does not exist")
        self.registry = GameEmulatorRegistry.from_environment()
        rows = {g["id"]: g for g in self.model["games"]}
        batch = self.plan["batches"][batch_index]
        allowed = batch["game_ids"]
        if game_ids is None:
            selected = list(allowed)
        else:
            if (not isinstance(game_ids, list) or not 2 <= len(game_ids) <= MAX_LANES
                or len(set(game_ids)) != len(game_ids)
                or any(type(identity) is not str or identity not in allowed for identity in game_ids)):
                raise LiveComparisonError("Live selection must contain distinct games from one permitted batch")
            selected = list(game_ids)
        if not 2 <= len(selected) <= min(MAX_LANES, self.model["max_active"]):
            raise LiveComparisonError("Live comparison requires 2–10 games, no more than study max_active")
        games = [rows[x] for x in selected]
        for game in games:
            core = self.registry.resolve_core(game["core_id"])
            if game["target_id"] not in core.target_ids:
                raise LiveComparisonError("Installed approved core does not allow declared target")
        free = shutil.disk_usage(tempfile.gettempdir()).free
        waves, self.disk_budget = _storage_waves(
            games, requested_slots=len(games), free_temp_bytes=free
        )
        if len(waves) != 1:
            raise LiveComparisonError(
                "Live comparison cannot fit all selected games concurrently; choose fewer games or free TMPDIR space"
            )
        self._lock = threading.RLock()
        self._closed = False
        self._max_steps = max_steps
        self._lanes: dict[str, _Lane] = {}
        self.batch_index = batch_index
        self.study_digest = digest(self.model)
        try:
            for game in games:
                content_kwargs, content_digest = prepare_comparison_media(game)
                env = create_emulator_environment(
                    game["target_id"], core_id=game["core_id"],
                    expected_registry_digest=self.registry.registry_digest,
                    **content_kwargs,
                    controller_devices=game["controller_devices"],
                    max_steps=max_steps,
                    frames_per_step=game["frames_per_step"],
                    timeout_seconds=timeout_seconds,
                )
                try:
                    env.reset(game["seed"])
                    _preview(env)  # Reject unusable native initialization early.
                except BaseException:
                    env.close()
                    raise
                chain = digest([
                    SCHEMA, self.study_digest, game["id"],
                    content_digest, env.spec.environment_digest,
                    self.registry.registry_digest, "reset", game["seed"],
                ])
                self._lanes[game["id"]] = _Lane(
                    game=game, env=env, content_digest=content_digest,
                    native_content_digest=(
                        getattr(env, "descriptor", {}).get("content_digest", content_digest)
                    ),
                    controls_digest=digest(game["controller_devices"]), chain=chain,
                    first_chain=chain,
                )
        except BaseException:
            self.close()
            raise

    def _check(self) -> None:
        if self._closed:
            raise LiveComparisonError("Operator closed the comparative live session")

    def _lane_report(self, lane: _Lane, *, include_image: bool = True) -> dict[str, Any]:
        result = {
            "game_id": lane.game["id"], "title": lane.game["title"],
            "series_id": lane.game["series_id"],
            "core_id": lane.game["core_id"], "target_id": lane.game["target_id"],
            "content_sha256": lane.content_digest,
            "native_content_digest": lane.native_content_digest,
            "controller_layout": controller_layout_for_target(
                lane.game["target_id"], lane.game["controller_devices"],
                core_input_descriptors=(
                    getattr(lane.env,"_system_info",{}).get("core_input_descriptors",[])
                ),
            ),
            "core_input_descriptors_reported":len(
                getattr(lane.env,"_system_info",{}).get("core_input_descriptors",[])
            ),
            "status": lane.status, "error_class": lane.error_class,
            "episode_steps": lane.step_count, "lifetime_steps": lane.total_steps,
            "reset_count": lane.reset_count,
            "native_disc_change_count": lane.disc_change_count,
            "timing_mode": lane.timing_mode,
            "timing_factor": lane.timing_factor,
            "last_burst_wall_ms": lane.last_burst_wall_ms,
            "last_burst_native_fps": lane.last_burst_native_fps,
            "last_burst_receipted_frames": lane.last_burst_receipted_frames,
            "speed_measurement_scope": "host_monotonic_wall_time_per_burst_not_hardware_accuracy",
            "timing_change_count": lane.timing_change_count,
            "inspection_count": lane.inspection_count,
            "native_frames_per_step": native_execution_budget(lane.timing_mode, lane.timing_factor, lane.game["frames_per_step"])[0],
            "max_inspections": MAX_INSPECTION_EVENTS,
            "max_timing_changes": MAX_TIMING_EVENTS,
            "native_disc_status": (
                lane.env.disc_status()
                if lane.status != "native_execution_failed" and hasattr(lane.env, "disc_status")
                else {"supported": False, "image_count": 0}
            ),
            "checkpoint_count":lane.checkpoint_id,
            "has_private_checkpoint":lane.checkpoint is not None,
            "rewind_count":lane.rewind_count,
            "max_checkpoints":MAX_CHECKPOINTS_PER_LANE,
            "max_rewinds":MAX_REWINDS_PER_LANE,
            "max_lifetime_steps": self._max_steps,
            "initial_chain_sha256": lane.first_chain,
            "latest_event_chain_sha256": lane.chain,
            "native_receipts": list(lane.receipts[-64:]),
            "recent_native_events": list(lane.events[-64:]),
            "all_native_receipt_count": len(lane.receipts),
            "all_native_event_count": len(lane.events),
            "model_weights_updated": False,
        }
        if lane.status in ("running", "episode_complete") and include_image:
            result["native_preview"] = _preview(lane.env)
        return result

    def state(self, *, images: bool = True) -> dict[str, Any]:
        with self._lock:
            self._check()
            result = {
                "schema_version": SCHEMA,
                "study_id": self.model["study_id"],
                "study_digest": self.study_digest,
                "registry_digest": self.registry.registry_digest,
                "batch_index": self.batch_index,
                "max_concurrent_native_games": len(self._lanes),
                "native_game_ids": list(self._lanes),
                "lanes": {
                    key: self._lane_report(lane, include_image=images)
                    for key, lane in self._lanes.items()
                },
                "all_native_frames_real": True,
                "independent_core_and_gameplay_accuracy_verified": False,
                "model_training_or_promotion": False,
            }
            if len(json.dumps(result,allow_nan=False).encode()) > MAX_RESPONSE_BYTES:
                raise LiveComparisonError("Live report exceeds 64 MiB; reset session or reduce lane count")
            return result

    def _execute_one(
        self, lane: _Lane, controls: list[dict[str, Any]], *,
        native_frames: int, include_preview: bool = True,
    ) -> dict[str, Any]:
        try:
            previous_frame=(
                dict(lane.env._frame)
                if isinstance(lane.env._frame,dict) else None
            )
            previous_pixels=getattr(lane.env,"_pixels",None)
            if hasattr(lane.env, "input_frame_step"):
                step = lane.env.input_frame_step(controls, frames=native_frames)
            elif native_frames == lane.game["frames_per_step"]:
                step = lane.env.input_step(controls)  # Legacy synthetic test workers only.
            else:
                raise LiveComparisonError("Native worker lacks precise frame scheduling")
            frame = lane.env._frame
            if not isinstance(frame, dict):
                raise LiveComparisonError("Native worker omitted actual step video evidence")
            if (previous_frame is not None and type(frame.get("runs")) is int
                and type(previous_frame.get("runs")) is int
                and frame["runs"] - previous_frame["runs"] != native_frames):
                raise LiveComparisonError("Native core reported an unexpected frame-advance count")
            from .game_comparison_multispectral import native_step_multispectral_receipt

            rgb=getattr(lane.env,"_pixels",None)
            pcm=getattr(lane.env,"_audio",None)
            if type(rgb) is bytes and type(pcm) is bytes:
                multi=native_step_multispectral_receipt(
                    previous_frame,previous_pixels,frame,rgb,pcm,
                )
            else:
                # Fake test workers never claim measured native spectra.
                multi=None
            evidence = {
                "schema_version": "skeleton.game.live_native_step_receipt.v1",
                "game_id": lane.game["id"],
                "index": lane.total_steps + 1,
                "episode_step": lane.step_count + 1,
                "reset_generation": lane.reset_count,
                "input_vector_sha256": digest(controls),
                "controller_ports": json.loads(json.dumps(controls)),
                "action_mode": "actual_native_controller_input",
                "frame_sha256": frame["pixel_sha256"],
                "pcm_sha256": frame["audio_sha256"],
                "native_frame_calls": frame["runs"],
                "requested_native_frames": native_frames,
                "timing_mode": lane.timing_mode,
                "timing_factor": lane.timing_factor,
                "native_audio_frames": frame["audio_frames"],
                "transition_sha256": step.transition_digest,
                "objective_observations": {
                    k: float(step.observation[k])
                    for k in ("screen_mean", "visual_change", "audio_rms", "step_fraction")
                },
                "native_multispectral": multi,
                "source_content_sha256": lane.content_digest,
                "core_sha256": lane.env.core.library_sha256,
                "previous_chain_sha256": lane.chain,
            }
            lane.chain = digest(evidence)
            evidence["receipt_sha256"] = lane.chain
            lane.receipts.append(evidence)
            lane.events.append({"event_kind":"native_step",
                                "receipt":evidence,
                                "receipt_sha256":lane.chain})
            lane.total_steps += 1
            lane.step_count += 1
            if lane.env.done:
                lane.status = "episode_complete"
            return {"game_id": lane.game["id"], "status": lane.status,
                    "receipt": evidence,
                    "native_preview": _preview(lane.env) if include_preview else None}
        except BaseException as exc:
            lane.status = "native_execution_failed"
            lane.error_class = type(exc).__name__
            lane.env.close()
            return {"game_id": lane.game["id"], "status": lane.status,
                    "error_class": lane.error_class, "native_receipt_created": False}

    def _execute_burst(
        self, lane: _Lane, controls: list[dict[str, Any]], repeat: int, native_frames: int
    ) -> dict[str, Any]:
        """Advance 1–8 actually executed steps; encode only final native PNG."""
        started = time.perf_counter()
        receipts=[]
        last=None
        for index in range(repeat):
            last=self._execute_one(
                lane,controls,native_frames=native_frames,include_preview=(index==repeat-1),
            )
            if last["status"]=="native_execution_failed":
                break
            receipts.append(last["receipt"])
            if last["status"]=="episode_complete":
                # The native core reached the episode boundary. Never send a
                # second step to an inactive environment or relabel success as
                # worker failure. An early terminal frame still needs a preview.
                if last.get("native_preview") is None:
                    last["native_preview"]=_preview(lane.env)
                break
        elapsed = max(1e-9, time.perf_counter() - started)
        fully_receipted_frames = len(receipts) * native_frames
        lane.last_burst_wall_ms = round(elapsed * 1000, 3)
        lane.last_burst_native_fps = round(fully_receipted_frames / elapsed, 2)
        lane.last_burst_receipted_frames = fully_receipted_frames
        return {
            "game_id":lane.game["id"],
            "status":last["status"] if last is not None else lane.status,
            "measured_wall_ms": lane.last_burst_wall_ms,
            "observed_native_frames_per_wall_second": lane.last_burst_native_fps,
            "fully_receipted_native_frames": fully_receipted_frames,
            "timing_semantics": "measured_per_host_burst_not_guaranteed_realtime_speed",
            "attempted_native_steps":repeat,
            "native_frames_per_step":native_frames,
            "completed_native_steps":len(receipts),
            "receipts":receipts,
            "last_receipt_sha256":receipts[-1]["receipt_sha256"] if receipts else None,
            "native_preview":(
                last.get("native_preview") if last is not None and last["status"]!="native_execution_failed"
                else None
            ),
            "error_class":last.get("error_class") if last is not None else None,
            "complete":len(receipts)==repeat,
            "stopped_on_episode_boundary":(
                last is not None and last["status"]=="episode_complete"
            ),
        }

    @staticmethod
    def _device_controls_match(device: str, value: Mapping[str, Any]) -> bool:
        """Never translate one peripheral's payload into another device's ABI."""
        buttons=bool(value["buttons"])
        axes=any(value["axes"])
        keys=bool(value["keys"])
        mouse=any(value["mouse"])
        pointer=any(value["pointer"])
        if device=="none":
            return not (buttons or axes or keys or mouse or pointer)
        if device=="joypad":
            return not (axes or keys or mouse or pointer)
        if device=="analog":
            return not (keys or mouse or pointer)
        if device=="keyboard":
            return not (buttons or axes or mouse or pointer)
        if device=="mouse":
            return not (buttons or axes or keys or pointer)
        if device=="pointer":
            return not (buttons or axes or keys or mouse)
        return False

    def step(self, raw: object) -> dict[str, Any]:
        with self._lock:
            self._check()
            if not isinstance(raw, dict) or set(raw) != {"steps"}:
                raise LiveComparisonError("Step request requires exact bounded steps list")
            rows=raw["steps"]
            if not isinstance(rows,list) or not 1 <= len(rows) <= MAX_REQUEST_LANES:
                raise LiveComparisonError("One through ten game updates required")
            prepared=[]
            seen=set()
            for row in rows:
                if (not isinstance(row,dict)
                    or set(row) not in ({"game_id","controls"}, {"game_id","controls","repeat"})):
                    raise LiveComparisonError("Step item requires game_id, controls and optional bounded repeat")
                identity = row["game_id"]
                if type(identity) is not str or identity not in self._lanes or identity in seen:
                    raise LiveComparisonError("Step must address a unique existing active game lane")
                lane=self._lanes[identity]
                if lane.timing_mode == "paused":
                    raise LiveComparisonError("Paused emulator rejects all native frame advances")
                native_frames, default_burst = native_execution_budget(
                    lane.timing_mode, lane.timing_factor, lane.game["frames_per_step"]
                )
                repeat=row.get("repeat",default_burst)
                if type(repeat) is not int or not 1<=repeat<=MAX_BURST_STEPS:
                    raise LiveComparisonError("Native input repeat must be a positive integer <=8")
                if lane.status!="running" or lane.total_steps+repeat>self._max_steps:
                    raise LiveComparisonError("Native burst exceeds this lane's remaining lifetime step budget")
                controls = _controls(row["controls"])
                if len(controls) > len(lane.game["controller_devices"]):
                    raise LiveComparisonError("Controller vector exceeds selected native topology")
                # Reject malformed cross-device payloads before launching ANY
                # core in the requested multi-game batch.
                for i,control in enumerate(controls):
                    device=lane.game["controller_devices"][i]
                    if not self._device_controls_match(device,control):
                        raise LiveComparisonError(
                            "Native input is incompatible with declared "+device+" device on port "+str(i)
                        )
                prepared.append((lane,controls,repeat,native_frames))
                seen.add(identity)
            # First validate ALL lanes, then execute at most 10 actual cores.
            with ThreadPoolExecutor(max_workers=len(prepared)) as executor:
                futures=[executor.submit(self._execute_burst,lane,controls,repeat,native_frames)
                         for lane,controls,repeat,native_frames in prepared]
                results=[f.result() for f in futures]
            return {"schema_version":"skeleton.game.live_step_batch.v1",
                    "results":results,"parallel_native_lanes_attempted":len(results),
                    "all_succeeded":all(x["complete"] and x["status"]!="native_execution_failed" for x in results),
                    "model_training_performed":False}

    def set_timing(self, raw: object) -> dict[str, Any]:
        """Core-independent speed profile, with native-frame-free audit receipt."""
        with self._lock:
            self._check()
            if not isinstance(raw, dict) or set(raw) != {"game_id", "mode", "factor"}:
                raise LiveComparisonError("Timing request needs exact game_id, mode and factor")
            identity = raw["game_id"]
            if type(identity) is not str or identity not in self._lanes:
                raise LiveComparisonError("Unknown native game for timing control")
            mode, factor = normalize_timing(raw["mode"], raw["factor"])
            lane = self._lanes[identity]
            if lane.status == "native_execution_failed":
                raise LiveComparisonError("Cannot control failed native emulator")
            if mode == lane.timing_mode and factor == lane.timing_factor:
                return {"game_id": identity, "changed": False, "timing_mode": mode,
                        "timing_factor": factor, "native_frame_advanced": False}
            if lane.timing_change_count >= MAX_TIMING_EVENTS:
                raise LiveComparisonError("Native timing event budget exhausted")
            frame = getattr(lane.env, "_frame", None)
            if not isinstance(frame, dict):
                raise LiveComparisonError("Native frame missing before timing change")
            receipt = {
                "schema_version": "skeleton.game.live_native_timing_receipt.v1",
                "game_id": identity, "index": lane.timing_change_count + 1,
                "episode_step": lane.step_count, "reset_generation": lane.reset_count,
                "previous_mode": lane.timing_mode, "previous_factor": lane.timing_factor,
                "mode": mode, "factor": factor,
                "native_frame_sha256": frame["pixel_sha256"],
                "native_run_cursor": frame["runs"],
                "source_content_sha256": lane.content_digest,
                "core_sha256": lane.env.core.library_sha256,
                "previous_chain_sha256": lane.chain,
                "native_frame_advanced": False,
            }
            lane.chain = digest(receipt)
            receipt["receipt_sha256"] = lane.chain
            lane.events.append({"event_kind": "native_timing_change", "receipt": receipt,
                                "receipt_sha256": lane.chain})
            lane.timing_mode, lane.timing_factor = mode, factor
            lane.timing_change_count += 1
            return {"game_id": identity, "changed": True, "timing_mode": mode,
                    "timing_factor": factor, "receipt": receipt,
                    "native_frame_advanced": False, "model_training_performed": False}

    def inspect(self, raw: object) -> dict[str, Any]:
        """Snapshot native RGB tiles only while frozen. A pause is not retro_run."""
        with self._lock:
            self._check()
            if not isinstance(raw, dict) or set(raw) != {"game_id"}:
                raise LiveComparisonError("Inspection requires an exact game_id")
            identity = raw["game_id"]
            if type(identity) is not str or identity not in self._lanes:
                raise LiveComparisonError("Unknown native game for frame inspection")
            lane = self._lanes[identity]
            if lane.timing_mode != "paused" or lane.status == "native_execution_failed":
                raise LiveComparisonError("Pause the native emulator before high fidelity inspection")
            if lane.inspection_count >= MAX_INSPECTION_EVENTS:
                raise LiveComparisonError("Native inspection receipt budget exhausted")
            if not hasattr(lane.env, "inspect_frame"):
                raise LiveComparisonError("Real libretro pixel inspection unavailable")
            inspected = lane.env.inspect_frame()
            if (inspected.get("native_frames_executed_for_inspection") != 0
                or inspected.get("total_tiles", 0) > 256):
                raise LiveComparisonError("Native inspection exceeded immutable frame scope")
            receipt = {
                "schema_version": "skeleton.game.live_native_inspection_receipt.v1",
                "game_id": identity, "index": lane.inspection_count + 1,
                "episode_step": lane.step_count, "reset_generation": lane.reset_count,
                "native_frame_sha256": inspected["pixel_sha256"],
                "native_run_cursor": inspected["native_run_cursor"],
                "inspection_sha256": digest(inspected),
                "tile_count": inspected["total_tiles"],
                "source_content_sha256": lane.content_digest,
                "core_sha256": lane.env.core.library_sha256,
                "previous_chain_sha256": lane.chain, "native_frame_advanced": False,
            }
            lane.chain = digest(receipt)
            receipt["receipt_sha256"] = lane.chain
            lane.events.append({"event_kind": "native_frame_inspection", "receipt": receipt,
                                "receipt_sha256": lane.chain})
            lane.inspection_count += 1
            return {"game_id": identity, "inspection": inspected,
                    "receipt": receipt, "native_frame_advanced": False,
                    "model_training_performed": False}

    def swap_disc(self, raw: object) -> dict[str, Any]:
        """Operator-selected preloaded disc, never dynamic source file injection."""
        with self._lock:
            self._check()
            if not isinstance(raw, dict) or set(raw) != {"game_id", "image_index"}:
                raise LiveComparisonError("Disc change requires exact game ID and bounded index")
            game_id, index = raw["game_id"], raw["image_index"]
            if type(game_id) is not str or game_id not in self._lanes:
                raise LiveComparisonError("Unknown approved live game lane")
            if type(index) is not int or not 0 <= index <= 31:
                raise LiveComparisonError("Native disc index must be 0–31")
            lane = self._lanes[game_id]
            if lane.status != "running" or lane.timing_mode == "paused" or lane.disc_change_count >= 32:
                raise LiveComparisonError("Native disc changes are unavailable or exhausted")
            if not hasattr(lane.env, "swap_disc"):
                raise LiveComparisonError("This native lane has no disc switching capability")
            try:
                operation = lane.env.swap_disc(index)
                if not operation["changed"]:
                    return {
                        "game_id": game_id, "changed": False,
                        "disc_status": operation["disc_status"],
                        "native_frame_advanced": False,
                        "receipt_chain_sha256": lane.chain,
                    }
                status = operation["disc_status"]
                receipt = {
                    "schema_version": "skeleton.game.live_native_disc_swap_receipt.v1",
                    "game_id": game_id,
                    "index": lane.disc_change_count + 1,
                    "episode_step": lane.step_count,
                    "reset_generation": lane.reset_count,
                    "source_content_sha256": lane.content_digest,
                    "native_content_digest": lane.native_content_digest,
                    "core_sha256": lane.env.core.library_sha256,
                    "native_host_disc_receipt_sha256": operation["receipt"]["receipt_sha256"],
                    "native_host_disc_receipt": dict(operation["receipt"]),
                    "previous_image_index": operation["receipt"]["previous_image_index"],
                    "selected_image_index": status["image_index"],
                    "registered_disc_count": status["image_count"],
                    "interface_version": status["interface_version"],
                    "previous_chain_sha256": lane.chain,
                    "native_frame_advanced": False,
                }
                lane.chain = digest(receipt)
                receipt["receipt_sha256"] = lane.chain
                lane.events.append({
                    "event_kind": "native_disc_swap", "receipt": receipt,
                    "receipt_sha256": lane.chain,
                })
                lane.disc_change_count += 1
                return {
                    "game_id": game_id, "changed": True,
                    "disc_status": status,
                    "receipt": receipt,
                    "receipt_chain_sha256": lane.chain,
                    "native_frame_advanced": False,
                    "model_training_performed": False,
                }
            except BaseException as exc:
                lane.status = "native_execution_failed"
                lane.error_class = type(exc).__name__
                lane.env.close()
                return {
                    "game_id": game_id, "status": lane.status,
                    "error_class": lane.error_class,
                    "native_receipt_created": False,
                }

    def checkpoint(self, game_id: str) -> dict[str, Any]:
        """Save a bounded, private native state; export only hash evidence."""
        with self._lock:
            self._check()
            lane=self._lanes.get(game_id)
            if (lane is None or lane.status!="running"
                or lane.checkpoint_id>=MAX_CHECKPOINTS_PER_LANE):
                raise LiveComparisonError("Cannot checkpoint a stopped or exhausted native lane")
            try:
                saved=lane.env.snapshot()
                if (not isinstance(saved,dict)
                    or type(saved.get("snapshot_digest")) is not str
                    or type(saved.get("state_sha256")) is not str
                    or len(saved["snapshot_digest"])!=64
                    or len(saved["state_sha256"])!=64
                    or saved.get("steps")!=lane.step_count):
                    raise LiveComparisonError("Native checkpoint is malformed or differs from active episode cursor")
                checkpoint_id=lane.checkpoint_id+1
                entry={
                    "schema_version":"skeleton.game.live_native_checkpoint_receipt.v1",
                    "game_id":game_id,"checkpoint_id":checkpoint_id,
                    "episode_step":lane.step_count,
                    "reset_generation":lane.reset_count,
                    "source_content_sha256":lane.content_digest,
                    "core_sha256":lane.env.core.library_sha256,
                    "native_state_sha256":saved["state_sha256"],
                    "private_snapshot_digest":saved["snapshot_digest"],
                    "frame_sha256":lane.env._frame["pixel_sha256"],
                    "previous_chain_sha256":lane.chain,
                    "private_native_state_exported":False,
                }
                signed=digest(entry)
                entry["receipt_sha256"]=signed
                lane.checkpoint=saved
                lane.checkpoint_id=checkpoint_id
                lane.checkpoint_episode_step=lane.step_count
                lane.checkpoint_reset_generation=lane.reset_count
                lane.chain=signed
                lane.events.append({
                    "event_kind":"native_checkpoint",
                    "receipt":entry,"receipt_sha256":signed,
                })
                return {
                    "game_id":game_id,"status":lane.status,
                    "checkpoint_id":checkpoint_id,
                    "episode_step":lane.step_count,
                    "state_sha256":saved["state_sha256"],
                    "receipt_chain_sha256":signed,
                    "private_savestate_bytes_returned":False,
                }
            except (ValueError,RuntimeError,OSError,KeyError,TypeError) as exc:
                # Snapshot failure does not alter an otherwise working emulator.
                raise LiveComparisonError("Native checkpoint rejected: "+type(exc).__name__) from exc

    def rewind(self, game_id: str) -> dict[str, Any]:
        """Restore operator's last private checkpoint with new chained lineage."""
        with self._lock:
            self._check()
            lane=self._lanes.get(game_id)
            if (lane is None or lane.status not in ("running","episode_complete")
                or lane.checkpoint is None
                or lane.rewind_count>=MAX_REWINDS_PER_LANE
                or lane.checkpoint_reset_generation!=lane.reset_count):
                raise LiveComparisonError("Native rewind requires a valid same-episode private checkpoint")
            if lane.total_steps>=self._max_steps:
                raise LiveComparisonError("Native rewind cannot extend the lifetime native step budget")
            try:
                lane.env.restore(lane.checkpoint)
                preview=_preview(lane.env)
                if preview["frame_sha256"]!=lane.checkpoint["frame"]["pixel_sha256"]:
                    raise LiveComparisonError("Actual restored frame differs from committed checkpoint")
                lane.step_count=lane.checkpoint_episode_step
                lane.status="running"
                lane.rewind_count+=1
                entry={
                    "schema_version":"skeleton.game.live_native_rewind_receipt.v1",
                    "game_id":game_id,
                    "checkpoint_id":lane.checkpoint_id,
                    "rewind_generation":lane.rewind_count,
                    "reset_generation":lane.reset_count,
                    "restored_episode_step":lane.step_count,
                    "source_content_sha256":lane.content_digest,
                    "core_sha256":lane.env.core.library_sha256,
                    "private_snapshot_digest":lane.checkpoint["snapshot_digest"],
                    "native_state_sha256":lane.checkpoint["state_sha256"],
                    "frame_sha256":preview["frame_sha256"],
                    "previous_chain_sha256":lane.chain,
                    "private_native_state_exported":False,
                }
                lane.chain=digest(entry)
                entry["receipt_sha256"]=lane.chain
                lane.events.append({
                    "event_kind":"native_rewind","receipt":entry,
                    "receipt_sha256":lane.chain,
                })
                return {
                    "game_id":game_id,
                    "status":"running",
                    "rewind_count":lane.rewind_count,
                    "restored_episode_step":lane.step_count,
                    "checkpoint_id":lane.checkpoint_id,
                    "receipt_chain_sha256":lane.chain,
                    "native_preview":preview,
                    "private_savestate_bytes_returned":False,
                }
            except (ValueError,RuntimeError,OSError,KeyError,TypeError) as exc:
                lane.status="native_execution_failed"
                lane.error_class=type(exc).__name__
                lane.env.close()
                raise LiveComparisonError("Native rewind failed; lane closed") from exc

    def reset(self, game_id: str) -> dict[str, Any]:
        with self._lock:
            self._check()
            lane=self._lanes.get(game_id)
            if lane is None or lane.status=="native_execution_failed":
                raise LiveComparisonError("Cannot reset an unknown or failed native lane")
            if lane.timing_mode == "paused":
                raise LiveComparisonError("Resume the paused emulator before a native reset")
            if lane.reset_count >= MAX_RESET_PER_LANE or lane.total_steps >= self._max_steps:
                raise LiveComparisonError("Live session reset or lifetime step budget exhausted")
            try:
                lane.env.reset(lane.game["seed"])
                preview=_preview(lane.env)
                lane.reset_count += 1
                lane.step_count=0
                lane.checkpoint=None  # reset invalidates the old episode state
                lane.status="running"
                reset_receipt={
                    "schema_version":"skeleton.game.live_native_reset_receipt.v1",
                    "game_id":game_id,
                    "reset_generation":lane.reset_count,
                    "previous_chain_sha256":lane.chain,
                    "frame_sha256":preview["frame_sha256"],
                    "audio_sha256":preview["audio_sha256"],
                    "source_content_sha256":lane.content_digest,
                    "seed_is_label_only":True,
                }
                lane.chain=digest(reset_receipt)
                reset_receipt["receipt_sha256"]=lane.chain
                lane.events.append({"event_kind":"native_reset",
                                    "receipt":reset_receipt,
                                    "receipt_sha256":lane.chain})
                return {"game_id":game_id,"status":"running",
                        "reset_count":lane.reset_count,
                        "receipt_chain_sha256":lane.chain,
                        "native_preview":preview}
            except BaseException as exc:
                lane.status="native_execution_failed"
                lane.error_class=type(exc).__name__
                lane.env.close()
                return {"game_id":game_id,"status":lane.status,
                        "error_class":lane.error_class}

    def export_evidence(self) -> dict[str, Any]:
        """Export complete finite step/reset history, never game source data."""
        with self._lock:
            self._check()
            result={
                "schema_version":"skeleton.game.live_evidence_export.v1",
                "study_id":self.model["study_id"],
                "study_digest":self.study_digest,
                "registry_digest":self.registry.registry_digest,
                "batch_index":self.batch_index,
                "lanes":{
                    game_id:{
                        "game_id":game_id,
                        "core_id":lane.game["core_id"],
                        "target_id":lane.game["target_id"],
                        "source_media_sha256":lane.content_digest,
                        "native_content_digest":lane.native_content_digest,
                        "core_sha256":lane.env.core.library_sha256,
                        "native_environment_sha256":lane.env.spec.environment_digest,
                        "configured_frames_per_step":lane.game["frames_per_step"],
                        "seed":lane.game["seed"],
                        "initial_chain_sha256":lane.first_chain,
                        "final_chain_sha256":lane.chain,
                        "step_count":lane.total_steps,
                        "reset_count":lane.reset_count,
                        "disc_change_count":lane.disc_change_count,
                        "timing_change_count":lane.timing_change_count,
                        "inspection_count":lane.inspection_count,
                        "checkpoint_count":lane.checkpoint_id,
                        "rewind_count":lane.rewind_count,
                        "native_events":list(lane.events),
                        "source_game_assets_included":False,
                    }
                    for game_id,lane in self._lanes.items()
                },
                "all_native_frames_real":True,
                "private_savestates_exported":False,
                "independent_hardware_accuracy_verified":False,
                "learning_or_production_weight_promoted":False,
            }
            if len(json.dumps(result,sort_keys=True,allow_nan=False).encode())>MAX_RESPONSE_BYTES:
                raise LiveComparisonError("Full live native receipts exceed the bounded 64-MiB export")
            return result

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed=True
            for lane in self._lanes.values():
                try: lane.env.close()
                except Exception: pass
            self._lanes.clear()

    def __enter__(self) -> "LiveComparison":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
