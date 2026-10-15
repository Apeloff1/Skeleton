"""Explicit operator-owned, loopback-only live comparative libretro sessions.

Only pre-approved game rows from a validated 30-game study may be started.
Two to ten live lanes; actual native screen frames; <=256 steps/lane,
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Mapping

from .game_comparison_schema import ComparativeStudyError, digest, plan_study, validate_study
from .game_comparison_controllers import controller_layout_for_target
from .game_comparison_media import prepare_comparison_media
from .game_comparison_studio import _storage_waves
from .game_emulator_host import _controls, create_emulator_environment
from .game_emulator_catalog import GameEmulatorRegistry

SCHEMA = "skeleton.game.live_comparison.v1"
MAX_LANES = 10
MAX_STEPS_PER_LANE = 256
MAX_RESET_PER_LANE = 4
MAX_REQUEST_LANES = 10
MAX_BURST_STEPS = 8
MAX_IMAGE_URI = 320_000
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


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
    controls_digest: str
    chain: str
    first_chain: str
    step_count: int = 0
    total_steps: int = 0
    reset_count: int = 0
    receipts: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
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
                raise LiveComparisonError("Live report exceeds five MiB; reset session or reduce lane count")
            return result

    def _execute_one(self, lane: _Lane, controls: list[dict[str, Any]], *, include_preview: bool = True) -> dict[str, Any]:
        try:
            step = lane.env.input_step(controls)
            frame = lane.env._frame
            if not isinstance(frame, dict):
                raise LiveComparisonError("Native worker omitted actual step video evidence")
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
                "native_audio_frames": frame["audio_frames"],
                "transition_sha256": step.transition_digest,
                "objective_observations": {
                    k: float(step.observation[k])
                    for k in ("screen_mean", "visual_change", "audio_rms", "step_fraction")
                },
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
        self, lane: _Lane, controls: list[dict[str, Any]], repeat: int
    ) -> dict[str, Any]:
        """Advance 1–8 actually executed steps; encode only final native PNG."""
        receipts=[]
        last=None
        for index in range(repeat):
            last=self._execute_one(
                lane,controls,include_preview=(index==repeat-1),
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
        return {
            "game_id":lane.game["id"],
            "status":last["status"] if last is not None else lane.status,
            "attempted_native_steps":repeat,
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
                repeat=row.get("repeat",1)
                if type(repeat) is not int or not 1<=repeat<=MAX_BURST_STEPS:
                    raise LiveComparisonError("Native input repeat must be a positive integer <=8")
                identity = row["game_id"]
                if type(identity) is not str or identity not in self._lanes or identity in seen:
                    raise LiveComparisonError("Step must address a unique existing active game lane")
                lane=self._lanes[identity]
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
                prepared.append((lane,controls,repeat))
                seen.add(identity)
            # First validate ALL lanes, then execute at most 10 actual cores.
            with ThreadPoolExecutor(max_workers=len(prepared)) as executor:
                futures=[executor.submit(self._execute_burst,lane,controls,repeat)
                         for lane,controls,repeat in prepared]
                results=[f.result() for f in futures]
            return {"schema_version":"skeleton.game.live_step_batch.v1",
                    "results":results,"parallel_native_lanes_attempted":len(results),
                    "all_succeeded":all(x["complete"] and x["status"]!="native_execution_failed" for x in results),
                    "model_training_performed":False}

    def reset(self, game_id: str) -> dict[str, Any]:
        with self._lock:
            self._check()
            lane=self._lanes.get(game_id)
            if lane is None or lane.status=="native_execution_failed":
                raise LiveComparisonError("Cannot reset an unknown or failed native lane")
            if lane.reset_count >= MAX_RESET_PER_LANE or lane.total_steps >= self._max_steps:
                raise LiveComparisonError("Live session reset or lifetime step budget exhausted")
            try:
                lane.env.reset(lane.game["seed"])
                preview=_preview(lane.env)
                lane.reset_count += 1
                lane.step_count=0
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
                        "core_sha256":lane.env.core.library_sha256,
                        "native_environment_sha256":lane.env.spec.environment_digest,
                        "seed":lane.game["seed"],
                        "initial_chain_sha256":lane.first_chain,
                        "final_chain_sha256":lane.chain,
                        "step_count":lane.total_steps,
                        "reset_count":lane.reset_count,
                        "native_events":list(lane.events),
                        "source_game_assets_included":False,
                    }
                    for game_id,lane in self._lanes.items()
                },
                "all_native_frames_real":True,
                "independent_hardware_accuracy_verified":False,
                "learning_or_production_weight_promoted":False,
            }
            if len(json.dumps(result,sort_keys=True,allow_nan=False).encode())>MAX_RESPONSE_BYTES:
                raise LiveComparisonError("Full live native receipts exceed the bounded five-MiB export")
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
