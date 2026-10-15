"""Combine many <=30-title native comparative studies into a long-series ledger.

The lineage layer is read-only and never executes ROMs, asserts that missing
installments exist, or turns narrative similarity into a training label. A
series may span up to 128 separately bounded study reports (3840 variants).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .game_comparison_schema import digest

SCHEMA = "skeleton.game.comparative_series_ledger.v1"
MAX_STUDIES = 128
MAX_VARIANTS = 3840
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_LEDGER_BYTES = 16 * 1024 * 1024


class SeriesLedgerError(ValueError):
    """Cross-study series provenance or data bounds differ."""


def merge_comparative_series(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not isinstance(reports, (list, tuple)) or not 1 <= len(reports) <= MAX_STUDIES:
        raise SeriesLedgerError("Series ledger requires 1–128 complete study reports")
    seen = set()
    studies: list[dict[str, Any]] = []
    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    notes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_bytes = 0
    for raw in reports:
        if not isinstance(raw, dict) or raw.get("schema_version") != "skeleton.game.comparative_study_result.v1":
            raise SeriesLedgerError("Series ledger accepts only canonical native comparative reports")
        total_bytes += len(json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
        if total_bytes > MAX_SOURCE_BYTES:
            raise SeriesLedgerError("Series study inputs exceed 128 MiB evidence budget")
        study_id, saved_digest = raw.get("study_id"), raw.get("result_sha256")
        if type(study_id) is not str or not study_id or type(saved_digest) is not str:
            raise SeriesLedgerError("Study lacks unique source identity and complete SHA-256 receipt")
        computed = digest({k: v for k, v in raw.items() if k != "result_sha256"})
        if computed != saved_digest:
            raise SeriesLedgerError("Study result bytes differ from the hash-chained saved source")
        if study_id in seen:
            raise SeriesLedgerError("Duplicate study ID is not another observation")
        seen.add(study_id)
        studies.append({
            "study_id": study_id,
            "result_sha256": saved_digest,
            "planned_game_count": raw["planned_total_game_count"],
            "actual_game_sessions_attempted": raw["actual_game_sessions_attempted"],
            "actual_observations_complete": raw["game_observations_completed"],
        })
        games = raw["games"]
        if not isinstance(games, dict) or len(games) > 30:
            raise SeriesLedgerError("Source study exceeds its 30-game capacity")
        for game_id, game in games.items():
            if type(game_id) is not str or not isinstance(game, dict):
                raise SeriesLedgerError("Series game row is not an identified object")
            if game.get("status") != "actual_native_observations_captured":
                continue
            sid, order = game.get("series_id"), game.get("release_order")
            if type(sid) is not str or type(order) is not int or not 1 <= order <= 1000000:
                raise SeriesLedgerError("Series identity/release order is invalid")
            phases = game.get("phases")
            if not isinstance(phases, dict) or set(phases) != {"earlier", "middle", "after"}:
                raise SeriesLedgerError("Native series entry lacks all three actual observation receipts")
            receipts = {}
            for phase, stage in phases.items():
                sha = stage.get("evidence_sha256")
                if type(sha) is not str or len(sha) != 64 or stage.get("source") != "actual_isolated_libretro":
                    raise SeriesLedgerError("Series stage is missing actual native evidence identity")
                receipts[phase] = sha
            series[sid].append({
                "study_id": study_id, "game_id": game_id, "title": game["title"],
                "release_order": order, "release_year": game.get("release_year"),
                "series_phase": game["series_phase"],
                "core_id": game["core_id"], "core_sha256": game["core_sha256"],
                "target_id": game["target_id"],
                "rom_sha256": game["source_sha256"],
                "native_checkpoint_receipts": receipts,
                "mean_visual_change": game["metrics"]["mean_visual_change"],
                "mean_audio_rms": game["metrics"]["mean_audio_rms"],
                "mean_screen_brightness": game["metrics"]["mean_screen_brightness"],
                "offline_trace_sha256": game["canonical_offline_trace_sha256"],
                "model_parameter_gain_proven": False,
            })
        for card in raw.get("dragon_and_jeeves_knowledge_candidates", []):
            if not isinstance(card, dict) or card.get("knowledge_status") != "reviewed_observation_candidate":
                continue
            claimed_series = {
                games[id]["series_id"]
                for id in card.get("game_ids", [])
                if id in games and games[id].get("status") == "actual_native_observations_captured"
            }
            for sid in claimed_series:
                notes[sid].append({
                    "study_id": study_id,
                    "note_id": card["note_id"],
                    "author": card["author"],
                    "dimension": card["dimension"],
                    "claim_type": card["claim_type"],
                    "text": card["text"],
                    "exact_evidence": card["evidence"],
                    "parameter_hypothesis": card.get("build_parameter_candidate"),
                    "review_status": "local_review_only",
                    "eligible_for_automatic_model_training": False,
                })
    variants = sum(len(g) for g in series.values())
    if variants > MAX_VARIANTS:
        raise SeriesLedgerError("Long-series library exceeds 3840 native variants")
    ledgers = []
    for sid, variants_for_series in sorted(series.items()):
        variants_for_series.sort(key=lambda x: (x["release_order"], x["release_year"] or 0, x["study_id"], x["game_id"]))
        installments = defaultdict(list)
        for v in variants_for_series:
            installments[v["release_order"]].append(v)
        # Suggest chronology comparisons only. A new replay must be run for
        # direct scientific measurements across emulator/title environments.
        neighbor_pairs = []
        orders = sorted(installments)
        for a, b in zip(orders, orders[1:]):
            neighbor_pairs.append({
                "earlier_release_order": a,
                "later_release_order": b,
                "suggested_reference": [
                    installments[a][0]["study_id"] + ":" + installments[a][0]["game_id"],
                    installments[b][0]["study_id"] + ":" + installments[b][0]["game_id"],
                ],
                "native_pair_comparison_executed": False,
            })
        review_cards = notes.get(sid, [])
        parameters = [
            {
                "study_id": n["study_id"], "note_id": n["note_id"],
                "dimension": n["dimension"],
                "build_parameter": n["parameter_hypothesis"],
                "source_evidence": n["exact_evidence"],
                "adversarially_verified": False,
                "model_weights_promoted": False,
            }
            for n in review_cards if n["parameter_hypothesis"] is not None
        ]
        ledgers.append({
            "series_id": sid,
            "distinct_release_orders_observed": len(installments),
            "game_or_emulator_variants_observed": len(variants_for_series),
            "installments": [
                {"release_order": order, "versions": installments[order]}
                for order in orders
            ],
            "chronological_pair_research_queue": neighbor_pairs,
            "reviewed_observer_claim_candidates": review_cards,
            "proposed_build_parameter_hypotheses": parameters,
            "complete_series_canon_verified": False,
            "unseen_installments_cannot_be_inferred_from_gaps": True,
        })
    result = {
        "schema_version": SCHEMA,
        "studies": studies,
        "source_study_count": len(studies),
        "series_count": len(ledgers),
        "native_game_variant_count": variants,
        "series": ledgers,
        "largest_observed_series": [
            {"series_id": e["series_id"], "observed_versions": e["game_or_emulator_variants_observed"]}
            for e in sorted(ledgers, key=lambda x: -x["game_or_emulator_variants_observed"])[:12]
        ],
        "observer_integration": "Local reviewed notes are evidence-linked candidates, not Dragon Academy consent or verified facts",
        "series_continuity": "A record can span multiple 30-game studies; source series coverage is never claimed complete without external evidence",
        "all_observations_source_native": True,
        "new_native_emulator_runs_executed_by_this_merge": 0,
        "training_parameters_applied": False,
        "model_weights_changed": False,
    }
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_LEDGER_BYTES:
        raise SeriesLedgerError("Compact cross-study ledger exceeds 16 MiB")
    result["ledger_sha256"] = hashlib.sha256(encoded).hexdigest()
    return result
