"""Offline descriptive A/B statistics from real native comparison receipts.

Validates each input/frame/audio/reset hash chain first. Shared episode ordinals
are NOT shared wall-clock time or proof of game/hardware fidelity. No emulator
is launched, no game source is loaded, and no model weights are updated.
"""
from __future__ import annotations
import json
import math
from itertools import combinations
from typing import Any, Mapping
from .game_comparison_live_evidence import verify_live_evidence
from .game_comparison_schema import canonical, digest

SCHEMA = "skeleton.game.live_pairwise_observation.v1"
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
SIGNALS = ("screen_mean", "visual_change", "audio_rms", "step_fraction")

class PairwiseObservationError(ValueError):
    """Invalid, tampered, or unusable native evidence."""

def _signals(value: object) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(SIGNALS):
        raise PairwiseObservationError("Exactly four native observation signals required")
    values = {}
    for key in SIGNALS:
        n = value[key]
        if type(n) not in (int, float) or not math.isfinite(n) or abs(n) > 1_000_000:
            raise PairwiseObservationError("Nonfinite or unbounded native signal")
        values[key] = float(n)
    return values

def _input_activity(ports: list[dict[str, Any]]) -> int:
    return sum(
        row["buttons"].bit_count() + len(row["keys"]) +
        sum(v != 0 for key in ("axes", "mouse", "pointer") for v in row[key])
        for row in ports
    )

def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 8) if values else None

def analyze_live_comparison_evidence(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Audit all 2-10 lane chains, then compute at most 45 unordered pairs."""
    if not isinstance(packet, dict):
        raise PairwiseObservationError("Native evidence must be one JSON object")
    try:
        if len(canonical(packet)) > MAX_EVIDENCE_BYTES:
            raise PairwiseObservationError("Native evidence exceeds five MiB")
        verified = verify_live_evidence(packet)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        if isinstance(exc, PairwiseObservationError):
            raise
        raise PairwiseObservationError("Native hash-chain validation failed") from exc

    lanes = []
    vectors = {}
    for attested in verified["games"]:
        gid = attested["game_id"]
        lane = packet["lanes"][gid]
        rows = {}
        signals = {name: [] for name in SIGNALS}
        frames, audio = set(), set()
        generation, previous_frame, previous_audio = 0, None, None
        changed_frames = changed_audio = active_input_steps = 0
        episodes = []
        episode = {"generation": 0, "steps": 0, "frame_changes": 0, "audio_changes": 0}
        for event in lane["native_events"]:
            p = event["receipt"]
            if event["event_kind"] == "native_reset":
                episodes.append(episode)
                generation += 1
                episode = {"generation": generation, "steps": 0, "frame_changes": 0, "audio_changes": 0}
                previous_frame = previous_audio = None
                continue
            observed = _signals(p.get("objective_observations"))
            active = _input_activity(p["controller_ports"])
            key = (generation, p["episode_step"])
            if key in rows:
                raise PairwiseObservationError("Duplicate episode-step ordinal")
            rows[key] = {"signals": observed, "activity": active}
            for name in SIGNALS:
                signals[name].append(observed[name])
            frame, pcm = p["frame_sha256"], p["pcm_sha256"]
            frame_change = previous_frame is not None and frame != previous_frame
            audio_change = previous_audio is not None and pcm != previous_audio
            changed_frames += int(frame_change)
            changed_audio += int(audio_change)
            episode["frame_changes"] += int(frame_change)
            episode["audio_changes"] += int(audio_change)
            episode["steps"] += 1
            active_input_steps += int(active > 0)
            frames.add(frame)
            audio.add(pcm)
            previous_frame, previous_audio = frame, pcm
        episodes.append(episode)
        vectors[gid] = rows
        lanes.append({
            "game_id": gid, "target_id": lane["target_id"], "core_id": lane["core_id"],
            "source_media_sha256": lane["source_media_sha256"],
            "core_sha256": attested["core_sha256"],
            "native_input_steps": attested["native_input_steps_verified"],
            "native_resets": attested["native_resets_verified"],
            "active_input_steps": active_input_steps,
            "distinct_frame_hashes": len(frames),
            "distinct_audio_hashes": len(audio),
            "within_episode_frame_changes": changed_frames,
            "within_episode_audio_changes": changed_audio,
            "mean_signals": {name: _mean(values) for name, values in signals.items()},
            "episodes": episodes, "native_evidence_root_sha256": attested["final_chain_sha256"],
        })
    pairs = []
    for left, right in combinations(lanes, 2):
        a, b = left["game_id"], right["game_id"]
        matches = sorted(vectors[a].keys() & vectors[b].keys())
        differences = {name: [] for name in SIGNALS}
        inputs = []
        for ordinal in matches:
            x, y = vectors[a][ordinal], vectors[b][ordinal]
            for name in SIGNALS:
                differences[name].append(abs(x["signals"][name] - y["signals"][name]))
            inputs.append(abs(x["activity"] - y["activity"]))
        pairs.append({
            "game_a": a, "game_b": b, "overlapping_episode_step_ordinals": len(matches),
            "mean_absolute_signal_difference": {
                name: _mean(values) for name, values in differences.items()},
            "mean_absolute_input_activity_difference": _mean(inputs),
            "frame_novelty_count_difference": abs(left["distinct_frame_hashes"] - right["distinct_frame_hashes"]),
            "hardware_accuracy_winner": None, "same_game_timebase_inferred": False,
            "interpretation": "Descriptive ordinal comparison only: game states and clocks are not synchronized",
        })
    report = {
        "schema_version": SCHEMA, "study_id": packet["study_id"],
        "study_digest": packet["study_digest"], "registry_digest": packet["registry_digest"],
        "source_export_sha256": digest(packet),
        "verified_native_chain_digest": verified["verification_sha256"],
        "lane_count": len(lanes), "pair_count": len(pairs),
        "total_input_steps": sum(lane["native_input_steps"] for lane in lanes),
        "lanes": lanes, "pairs": pairs,
        "native_emulation_performed_by_this_analysis": False,
        "independently_attested_hardware_accuracy": False,
        "cross_game_clocks_synchronized": False, "model_weights_updated": False,
        "promotion_status": "operator_review_only",
    }
    report["analysis_sha256"] = digest(report)
    return report

def render_pairwise_observation_dashboard(report: Mapping[str, Any]) -> str:
    """Standalone searchable HTML using escaped data and textContent only."""
    if (not isinstance(report, dict) or report.get("schema_version") != SCHEMA
        or report.get("analysis_sha256") != digest({k: v for k, v in report.items() if k != "analysis_sha256"})):
        raise PairwiseObservationError("Pairwise analysis was changed after hashing")
    safe = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    safe = safe.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
    page = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skeleton · Native emulator comparisons</title><style>
:root{color-scheme:dark;background:#101928;color:#e7eef9;font:14px system-ui}
body{max-width:1300px;margin:auto;padding:20px}h1{font-size:22px}h2{font-size:17px}
section{background:#1c2a3d;border:1px solid #405773;border-radius:12px;padding:15px;margin:15px 0}
.scroll{overflow:auto;max-height:500px}table{width:100%;border-collapse:collapse}
th,td{padding:9px;text-align:left;border-bottom:1px solid #405773;font-size:12px}
input{padding:9px;background:#0e1929;color:#fff;border:1px solid #697e99;width:100%;border-radius:7px}
small{color:#aec2d8}code{overflow-wrap:anywhere}</style></head>
<body><h1>Multi-emulator A/B observations</h1>
<p>Hash-checked native input/video/audio receipts. Differences are descriptive; not hardware accuracy, quality rankings, identical game states or verified model-learning gains.</p>
<section><h2>Native receipt coverage</h2><p id="overview"></p><div class="scroll"><table>
<thead><tr><th>Game</th><th>Core / Target</th><th>Steps</th><th>Resets</th><th>Frames</th><th>Frame changes</th><th>Active inputs</th></tr></thead>
<tbody id="lanes"></tbody></table></div></section>
<section><h2>Pairwise signal differences · up to 45</h2>
<label>Filter games <input id="filter" autocomplete="off"></label><div class="scroll"><table>
<thead><tr><th>Compared games</th><th>Overlapping ordinals</th><th>Screen mean Δ</th><th>Visual Δ</th><th>Audio RMS Δ</th><th>Step fraction Δ</th><th>Input Δ</th></tr></thead>
<tbody id="pairs"></tbody></table></div></section>
<footer><small id="provenance"></small></footer>
<script type="application/json" id="payload">__DATA__</script>
<script>"use strict";
const d=JSON.parse(document.getElementById("payload").textContent);
const el=id=>document.getElementById(id);
const cell=(tr,v)=>{const td=document.createElement("td");td.textContent=String(v??"—");tr.append(td)};
const num=n=>n===null?"No overlap":Number(n).toFixed(5);
el("overview").textContent=d.lane_count+" lanes · "+d.total_input_steps+" captured inputs · "+d.pair_count+" pairs · zero new emulation executions";
for(const l of d.lanes){const tr=document.createElement("tr");[l.game_id,l.core_id+" / "+l.target_id,l.native_input_steps,l.native_resets,l.distinct_frame_hashes,l.within_episode_frame_changes,l.active_input_steps].forEach(v=>cell(tr,v));el("lanes").append(tr)}
const draw=()=>{const q=el("filter").value.toLowerCase().trim();el("pairs").replaceChildren();
for(const p of d.pairs){if(q&&!p.game_a.toLowerCase().includes(q)&&!p.game_b.toLowerCase().includes(q))continue;
const tr=document.createElement("tr"),m=p.mean_absolute_signal_difference;
[p.game_a+" / "+p.game_b,p.overlapping_episode_step_ordinals,num(m.screen_mean),num(m.visual_change),num(m.audio_rms),num(m.step_fraction),num(p.mean_absolute_input_activity_difference)].forEach(v=>cell(tr,v));el("pairs").append(tr)}};
el("filter").addEventListener("input",draw);draw();
el("provenance").textContent="Export SHA-256: "+d.source_export_sha256+" · analysis SHA-256: "+d.analysis_sha256;
</script></body></html>"""
    return page.replace("__DATA__", safe)
