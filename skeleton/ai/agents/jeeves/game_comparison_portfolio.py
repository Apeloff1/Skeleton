"""Combine successive rights-cleared native comparison batches for a 30-game study.

Each cohort is independently hash-verified before joining. Two games from
different batches are compared by receipt-derived aggregate descriptors only;
never pretend frames or controller actions happened simultaneously.
"""
from __future__ import annotations

import json
from itertools import combinations
from typing import Any, Mapping, Sequence

from .game_comparison_pairwise import (
    MAX_EVIDENCE_BYTES, PairwiseObservationError, analyze_live_comparison_evidence)
from .game_comparison_schema import digest, plan_study, validate_study

SCHEMA = "skeleton.game.comparative_30_game_portfolio.v1"
MAX_COHORT_EXPORTS = 15


class GameComparisonPortfolioError(ValueError):
    """Cohort export cannot be joined to this pinned 30-game study."""


def combine_comparison_cohorts(
    study: Mapping[str, Any],
    exports: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    model = validate_study(dict(study))
    plan = plan_study(model)
    if (not isinstance(exports, (list, tuple)) or not 1 <= len(exports)
        <= min(MAX_COHORT_EXPORTS, len(plan["batches"]))):
        raise GameComparisonPortfolioError("Expected one to fifteen selected native cohorts")

    game_index = {row["id"]: row for row in model["games"]}
    indexed_batches: dict[int, dict[str, Any]] = {}
    joined: dict[str, dict[str, Any]] = {}
    registry_digest = None
    for packet in exports:
        if not isinstance(packet, dict):
            raise GameComparisonPortfolioError("Cohort must be a complete native JSON export")
        batch = packet.get("batch_index")
        if (type(batch) is not int or not 0 <= batch < len(plan["batches"])
            or batch in indexed_batches):
            raise GameComparisonPortfolioError("Cohort index is outside study plan or repeated")
        if (packet.get("study_id") != model["study_id"]
            or packet.get("study_digest") != plan["study_digest"]):
            raise GameComparisonPortfolioError("Native cohort belongs to another study revision")
        if registry_digest is None:
            registry_digest = packet.get("registry_digest")
        elif packet.get("registry_digest") != registry_digest:
            raise GameComparisonPortfolioError("Approved emulator core registry changed between cohorts")
        allowed = set(plan["batches"][batch]["game_ids"])
        lane_ids = set(packet.get("lanes", ()))
        if not lane_ids <= allowed:
            raise GameComparisonPortfolioError("A native lane is not in its selected study batch")
        if len(lane_ids) > model["max_active"]:
            raise GameComparisonPortfolioError("Native cohort exceeds approved active emulator capacity")

        try:
            analysis = analyze_live_comparison_evidence(packet)
        except (PairwiseObservationError, KeyError, TypeError, ValueError) as exc:
            raise GameComparisonPortfolioError("Cohort has invalid native receipt integrity") from exc
        for lane in analysis["lanes"]:
            gid = lane["game_id"]
            source = game_index[gid]
            if (gid in joined or lane["target_id"] != source["target_id"]
                or lane["core_id"] != source["core_id"]
                or packet["lanes"][gid]["seed"] != source["seed"]):
                raise GameComparisonPortfolioError("Recorded emulator lane does not match pinned game/core/seed")
            joined[gid] = {**lane, "batch_index": batch}
        indexed_batches[batch] = {
            "batch_index": batch, "recorded_game_count": analysis["lane_count"],
            "captured_input_steps": analysis["total_input_steps"],
            "export_sha256": analysis["source_export_sha256"],
            "cohort_analysis_sha256": analysis["analysis_sha256"],
        }

    recorded = [joined[game["id"]] for game in model["games"] if game["id"] in joined]
    pairs = []
    for left, right in combinations(recorded, 2):
        ga, gb = game_index[left["game_id"]], game_index[right["game_id"]]
        differences = {}
        for key in ("screen_mean", "visual_change", "audio_rms", "step_fraction"):
            a, b = left["mean_signals"][key], right["mean_signals"][key]
            differences[key] = round(abs(a - b), 8) if a is not None and b is not None else None
        together = left["batch_index"] == right["batch_index"]
        pairs.append({
            "game_a": left["game_id"], "game_b": right["game_id"],
            "batch_a": left["batch_index"], "batch_b": right["batch_index"],
            "series_a": ga["series_id"], "series_b": gb["series_id"],
            "phase_a": ga["series_phase"], "phase_b": gb["series_phase"],
            "same_series": ga["series_id"] == gb["series_id"],
            "co_recorded_in_single_live_batch": together,
            "absolute_difference_of_episode_aggregated_means": differences,
            "gameplay_or_emulator_fidelity_winner": None,
            "note": (
                "Within batch: aggregate summaries of separate native games; no synchronized state"
                if together else
                "Across batches: historical aggregate receipt summaries, not a simultaneous replay"
            ),
        })

    remaining = [game["id"] for game in model["games"] if game["id"] not in joined]
    result = {
        "schema_version": SCHEMA, "study_id": model["study_id"],
        "canonical_study_sha256": plan["study_digest"],
        "approved_registry_sha256": registry_digest,
        "planned_game_count": len(model["games"]),
        "recorded_game_count": len(recorded),
        "missing_game_ids": remaining,
        "planned_batch_count": len(plan["batches"]),
        "recorded_batch_count": len(indexed_batches),
        "batches": [indexed_batches[key] for key in sorted(indexed_batches)],
        "maximum_live_concurrent_games": model["max_active"],
        "pair_count": len(pairs), "maximum_thirty_game_pairs": 435,
        "games": recorded, "pairs": pairs,
        "complete_native_cohort_coverage": not remaining,
        "new_native_emulator_runs": 0, "cross_batch_frames_synchronized": False,
        "independent_hardware_accuracy_verified": False,
        "model_weight_updates": 0, "operator_review_required": True,
    }
    result["portfolio_sha256"] = digest(result)
    return result


def render_comparison_portfolio_dashboard(report: Mapping[str, Any]) -> str:
    if (not isinstance(report, dict) or report.get("schema_version") != SCHEMA
        or report.get("portfolio_sha256") != digest({k: v for k, v in report.items() if k != "portfolio_sha256"})):
        raise GameComparisonPortfolioError("Portfolio report is not hash intact")
    data = json.dumps(report, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    data = data.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
    html = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skeleton 30-game native emulator study</title>
<style>:root{color-scheme:dark;background:#111b2b;color:#e7f0fc;font:14px system-ui}
body{max-width:1300px;margin:auto;padding:20px}h1{font-size:23px}
section{background:#1d2b3f;padding:16px;border-radius:12px;margin:16px 0}
table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #465973;text-align:left;font-size:12px}
.scroll{max-height:610px;overflow:auto}input{width:100%;padding:10px;background:#0c1725;color:white;border:1px solid #738ba7}
small{color:#aebed2}</style></head><body>
<h1>30-game, 10-at-a-time native comparison portfolio</h1>
<p>Every recorded cohort passed self-contained native receipt verification. Across-batch values compare historical means, not synchronized game states or emulation accuracy. No AI weights changed.</p>
<section><h2>Study coverage</h2><p id="status"></p><p id="missing"></p>
<div class="scroll"><table><thead><tr><th>Batch</th><th>Games</th><th>Native input steps</th><th>Export hash</th></tr></thead><tbody id="batches"></tbody></table></div></section>
<section><h2>Cross-version comparisons · up to 435 pairs</h2>
<input id="filter" aria-label="Filter by game ID, series or phase" placeholder="Filter game, series or earlier / middle / after">
<div class="scroll"><table><thead><tr><th>Games</th><th>Series / phase</th><th>Capture type</th><th>Δ visual mean</th><th>Δ screen mean</th><th>Δ audio RMS</th></tr></thead><tbody id="pairs"></tbody></table></div></section>
<small id="provenance"></small><script id="data" type="application/json">__DATA__</script>
<script>"use strict";
const data=JSON.parse(document.getElementById("data").textContent),E=id=>document.getElementById(id);
const cell=(r,value)=>{const t=document.createElement("td");t.textContent=String(value??"n/a");r.append(t)};
const v=x=>x===null?"No data":Number(x).toFixed(5);
E("status").textContent=data.recorded_game_count+" / "+data.planned_game_count+" games · "+data.recorded_batch_count+" / "+data.planned_batch_count+" batches · "+data.pair_count+" pairwise comparisons";
E("missing").textContent="Unrecorded game IDs: "+(data.missing_game_ids.join(", ")||"none");
for(const b of data.batches){const r=document.createElement("tr");[b.batch_index,b.recorded_game_count,b.captured_input_steps,b.export_sha256].forEach(x=>cell(r,x));E("batches").append(r)}
const draw=()=>{const q=E("filter").value.toLowerCase().trim();E("pairs").replaceChildren();
for(const p of data.pairs){const s=p.game_a+" "+p.game_b+" "+p.series_a+" "+p.series_b+" "+p.phase_a+" "+p.phase_b;if(q&&!s.toLowerCase().includes(q))continue;
const r=document.createElement("tr"),m=p.absolute_difference_of_episode_aggregated_means;
[p.game_a+" / "+p.game_b,p.series_a+" "+p.phase_a+" → "+p.series_b+" "+p.phase_b,p.co_recorded_in_single_live_batch?"same live batch":"separate batches",v(m.visual_change),v(m.screen_mean),v(m.audio_rms)].forEach(x=>cell(r,x));E("pairs").append(r)}};
E("filter").addEventListener("input",draw);draw();E("provenance").textContent="Portfolio SHA-256: "+data.portfolio_sha256;
</script></body></html>"""
    return html.replace("__DATA__", data)
