"""Persistent Jeeves boomerang simulation queue with bounded randomized returns.

Pass 1 is a previously completed, audited adaptive campaign.
Pass 2 revisits it with bounded, controlled counterfactual probes.
Pass 3 analyzes the newly collected failures and revisits again.
An explicitly enabled randomized scheduler resurfaces completed old sources
for bounded later return visits, shuffled alongside new queue entries. Each
visit performs novel effective-control probes and retires on plateau or budget.

The original simulation is NOT restarted. Completed queue snapshots are
immutable, chained, and source-pinned; each advancement executes only new
scenarios. All discoveries are deterministic simulation/proxy evidence, NOT
claims of SGD exposure, learned capability, or independent model evaluation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import os
import sys
import time
from random import Random
from typing import Any

from .jeeves_cinematic_simulation import (
    CinematicSimError, _bounded_int, _hash, _json, _read_json,
    _write_new, _write_new_bytes, validate_scene,
)
from .jeeves_adaptive_sim_training import (
    _execute, _controls, _environment, _targeted, draft_scenarios,
    verify_campaign, validate_scenario,
)

SCHEMA = "skeleton.jeeves.boomerang_queue.v1"
MAX_ENTRIES = 32
MAX_REVISITS = 2
MAX_PROBES = 24
MAX_QUEUE_BYTES = 16 * 1024 * 1024
RESHUFFLE_SCHEMA = "skeleton.jeeves.boomerang_queue.v2"
MAX_RETURN_VISITS = 16
MAX_PLATEAU = 10
MAX_RETURN_INTERVAL = 30 * 86400
BASE_KEYS = {"schema_version", "generation", "parent_queue_sha256", "entries",
             "source_projects", "serving_weights_modified", "optimizer_updates",
             "automatic_model_promotion", "queue_sha256"}
ENTRY_KEYS = {"queue_id", "source", "revisits_completed", "max_revisits",
              "status", "initial_case_count", "initial_risk_families",
              "initial_scenario_ids", "initial_trace_count", "passes"}
RETURN_KEYS = {"next_due_epoch", "last_scheduled_epoch", "return_visits",
               "plateau_streak", "last_discovery_context_count"}


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise CinematicSimError("Jeeves boomerang queue: " + message)


def _receipt(queue: dict[str, Any]) -> dict[str, Any]:
    copy = {key: value for key, value in queue.items() if key != "queue_sha256"}
    return {**copy, "queue_sha256": _hash(copy)}


def _checked_file(path: Path, max_bytes: int) -> dict:
    _require(isinstance(path, Path) and not path.is_symlink() and path.is_file(),
             "source and archived campaign must be regular immutable files")
    _require(32 <= path.stat().st_size <= max_bytes,
             "source or prior evidence file outside size limit")
    return _read_json(path, max_bytes)


def _effective_identity(case: dict) -> str:
    """Same real controls/situation/environment = one experiment, even with another seed."""
    controls = {key: value for key, value in _controls(case).items() if key != "seed"}
    return _hash({"situation": case["situation"],
                  "environment": _environment(case), "controls": controls})


def _policy(seed: int, min_delay: int, max_delay: int,
            max_visits: int, plateau_limit: int) -> dict:
    _bounded_int(seed, 0, 2**31-1, "randomized-return seed")
    _bounded_int(min_delay, 1, MAX_RETURN_INTERVAL, "minimum return delay")
    _bounded_int(max_delay, min_delay, MAX_RETURN_INTERVAL, "maximum return delay")
    _bounded_int(max_visits, 1, MAX_RETURN_VISITS, "maximum later visits")
    _bounded_int(plateau_limit, 1, MAX_PLATEAU, "consecutive zero-discovery ceiling")
    return {"shuffle_seed": seed, "min_delay_seconds": min_delay,
            "max_delay_seconds": max_delay,
            "max_return_visits": max_visits,
            "plateau_limit": plateau_limit}


def _clock(now_epoch: int | None) -> int:
    timestamp = int(time.time()) if now_epoch is None else now_epoch
    return _bounded_int(timestamp, 0, 4102444800, "UTC queue epoch")


def _due(policy: dict, identity: str, last_receipt: str,
         next_visit: int, from_epoch: int) -> int:
    """Deterministic PRNG for auditability, with a real interval in seconds."""
    entropy = _hash({"source": identity, "prior_pass": last_receipt,
                     "return_number": next_visit,
                     "seed": policy["shuffle_seed"]})
    rng = Random(int(entropy, 16))
    return from_epoch + rng.randint(policy["min_delay_seconds"],
                                    policy["max_delay_seconds"])


def _status(entry: dict, policy: dict | None) -> str:
    if entry["revisits_completed"] == 0:
        return "awaiting_second_pass"
    if entry["revisits_completed"] == 1:
        return "awaiting_third_pass"
    if policy is None:
        return "complete"
    if (entry["return_visits"] >= policy["max_return_visits"] or
            entry["plateau_streak"] >= policy["plateau_limit"]):
        return "retired"
    return "scheduled_return"


def _return_entry(entry: dict, policy: dict, now: int) -> dict:
    result = deepcopy(entry)
    result.update({"next_due_epoch": None, "last_scheduled_epoch": None,
                   "return_visits": 0, "plateau_streak": 0,
                   "last_discovery_context_count": 0})
    if result["revisits_completed"] >= MAX_REVISITS:
        result["last_scheduled_epoch"] = now
        result["next_due_epoch"] = _due(
            policy, result["queue_id"], result["passes"][-1]["pass_sha256"], 1, now)
    result["status"] = _status(result, policy)
    return result


def enable_reshuffle(queue: dict, *, seed: int = 19,
                     min_delay_seconds: int = 3600,
                     max_delay_seconds: int = 86400,
                     max_return_visits: int = 16, plateau_limit: int = 10,
                     now_epoch: int | None = None) -> dict:
    """Migrate existing v1 queue, including completed 3-pass simulations."""
    verify_queue(queue, verify_sources=True)
    _require(queue["schema_version"] == SCHEMA,
             "randomized returns already configured for this queue")
    now = _clock(now_epoch)
    policy = _policy(seed, min_delay_seconds, max_delay_seconds,
                     max_return_visits, plateau_limit)
    upgraded = {**queue, "schema_version": RESHUFFLE_SCHEMA,
                "reshuffle_policy": policy, "last_tick_epoch": now,
                "generation": queue["generation"]+1,
                "parent_queue_sha256": queue["queue_sha256"],
                "entries": [_return_entry(e, policy, now) for e in queue["entries"]]}
    updated = _receipt(upgraded)
    verify_queue(updated, verify_sources=True)
    return updated


def _context_signatures(rows: list[dict]) -> set[str]:
    """Novel risk contexts, not seed changes or arbitrary raw frame hashes."""
    found = set()
    for row in rows:
        case = row["scenario"]
        # Weather/lighting/situation/attack are distinct controlled settings.
        # Changing only camera micro-parameters cannot make the same discovery.
        for family in row["risk_counts"]:
            found.add(_hash({
                "family": family, "situation": case["situation"],
                "weather": case["weather"], "lighting": case["lighting"],
                "attack": case["attack"],
            }))
    return found


def _due_work(queue: dict, now: int) -> list[int]:
    """Seeded due-work shuffle, combining queued new and overdue past simulations."""
    policy = queue["reshuffle_policy"]
    ready = []
    for i, entry in enumerate(queue["entries"]):
        if entry["status"] in ("awaiting_second_pass", "awaiting_third_pass"):
            ready.append((queue["last_tick_epoch"], i))
        elif entry["status"] == "scheduled_return" and entry["next_due_epoch"] <= now:
            ready.append((entry["next_due_epoch"], i))
    # Aging promotes long-waiting tickets; a deterministic randomized tie-break
    # mixes new and returned work in the same age bucket. No random starvation.
    def order(item):
        due, index = item
        wait_hours = max(0, now - due) // 3600
        salt = _hash({"source": queue["entries"][index]["queue_id"],
                      "generation": queue["generation"],
                      "seed": policy["shuffle_seed"],
                      "clock_hour": now // 3600})
        return (-wait_hours, salt)
    return [index for _due_at, index in sorted(ready, key=order)]


def _source_record(scene_file: Path, campaign_file: Path) -> dict:
    scene = _checked_file(scene_file, 128 * 1024)
    archive = _checked_file(campaign_file, 16 * 1024 * 1024)
    validation = validate_scene(scene)
    verify_campaign(archive)
    _require(archive["source_digest"] == validation["source_digest"]
             and archive["source_project_id"] == validation["project"],
             "archived campaign does not belong to the rights-reviewed original scene")
    original = {
        "scene_file": str(scene_file.resolve()),
        "campaign_file": str(campaign_file.resolve()),
        "scene_sha256": sha256(scene_file.read_bytes()).hexdigest(),
        "campaign_sha256": sha256(campaign_file.read_bytes()).hexdigest(),
        "source_digest": validation["source_digest"],
        "project_id": validation["project"],
        "archive_receipt_sha256": archive["receipt_sha256"],
    }
    identity = _hash({"project": original["project_id"],
                      "source": original["source_digest"],
                      "archive": original["archive_receipt_sha256"]})
    return {
        "queue_id": identity, "source": original,
        "revisits_completed": 0, "max_revisits": MAX_REVISITS,
        "status": "awaiting_second_pass",
        "initial_case_count": archive["budget_requested"],
        "initial_risk_families": archive["risk_families_observed"],
        "initial_scenario_ids": sorted({
            row["scenario"]["scenario_id"] for row in archive["cases"]}),
        "initial_trace_count": archive["unique_controlled_trace_digests"],
        "passes": [],
    }


def create_queue(scene_file: Path, campaign_file: Path) -> dict:
    """Enqueue an ALREADY-RUN original campaign without rerunning its frames."""
    entry = _source_record(scene_file, campaign_file)
    return _receipt({
        "schema_version": SCHEMA, "generation": 0, "parent_queue_sha256": None,
        "entries": [entry], "source_projects": [entry["source"]["project_id"]],
        "serving_weights_modified": False, "optimizer_updates": 0,
        "automatic_model_promotion": False,
    })


def enqueue(queue: dict, scene_file: Path, campaign_file: Path) -> dict:
    """Append a separately pinned source to a new immutable queue generation."""
    verify_queue(queue, verify_sources=True)
    _require(len(queue["entries"]) < MAX_ENTRIES, "queue is full")
    entry = _source_record(scene_file, campaign_file)
    ids = {e["queue_id"] for e in queue["entries"]}
    _require(entry["queue_id"] not in ids, "duplicate archived simulation source")
    # Never coalesce independent projects into the same training source group.
    new = {
        **queue, "generation": queue["generation"] + 1,
        "parent_queue_sha256": queue["queue_sha256"],
        "entries": [*deepcopy(queue["entries"]), entry],
    }
    new["source_projects"] = sorted({e["source"]["project_id"] for e in new["entries"]})
    if queue["schema_version"] == RESHUFFLE_SCHEMA:
        new["entries"][-1] = _return_entry(
            entry, queue["reshuffle_policy"], queue["last_tick_epoch"])
    updated = _receipt(new)
    verify_queue(updated)
    return updated


def _load_source(entry: dict) -> tuple[dict, dict]:
    src = entry["source"]
    path = Path(src["scene_file"])
    archive_path = Path(src["campaign_file"])
    scene = _checked_file(path, 128 * 1024)
    archive = _checked_file(archive_path, 16 * 1024 * 1024)
    _require(sha256(path.read_bytes()).hexdigest() == src["scene_sha256"]
             and sha256(archive_path.read_bytes()).hexdigest() == src["campaign_sha256"],
             "archived files changed after queue admission")
    original = _source_record(path, archive_path)
    _require(original["queue_id"] == entry["queue_id"] and
             original["source"] == src and
             archive["receipt_sha256"] == src["archive_receipt_sha256"],
             "queue provenance differs from verified original")
    return scene, archive


def verify_queue(queue: dict, *, verify_sources: bool = False) -> dict:
    """Validate structural chain and per-pass integrity without replaying frames."""
    _require(type(queue) is dict and queue.get("schema_version") in
             (SCHEMA, RESHUFFLE_SCHEMA), "queue schema changed")
    policy = None
    if queue["schema_version"] == RESHUFFLE_SCHEMA:
        _require(set(queue) == BASE_KEYS | {"reshuffle_policy", "last_tick_epoch"},
                 "unknown randomized queue fields")
        policy = queue["reshuffle_policy"]
        _require(type(policy) is dict and policy == _policy(
            policy["shuffle_seed"], policy["min_delay_seconds"],
            policy["max_delay_seconds"], policy["max_return_visits"],
            policy["plateau_limit"]), "reshuffle policy mutated")
        _clock(queue["last_tick_epoch"])
    else:
        _require(set(queue) == BASE_KEYS, "unknown original queue fields")
    _require(queue["queue_sha256"] == _hash({
        key: value for key, value in queue.items() if key != "queue_sha256"}),
        "queue content digest mismatch")
    _bounded_int(queue["generation"], 0, 100000, "generation")
    _require(type(queue["entries"]) is list and
             1 <= len(queue["entries"]) <= MAX_ENTRIES,
             "invalid queue depth")
    _require(queue["serving_weights_modified"] is False
             and queue["optimizer_updates"] == 0
             and queue["automatic_model_promotion"] is False,
             "simulation report falsely claims model training")
    ids = set()
    for entry in queue["entries"]:
        _require(type(entry) is dict and
                 set(entry) == (ENTRY_KEYS | (RETURN_KEYS if policy else set())),
                 "unrecognized queue entry fields")
        _require(entry["queue_id"] not in ids, "duplicate queue source")
        ids.add(entry["queue_id"])
        _require(entry["max_revisits"] == MAX_REVISITS and
                 type(entry["passes"]) is list and
                 len(entry["passes"]) == entry["revisits_completed"] and
                 0 <= entry["revisits_completed"] <=
                 MAX_REVISITS + (policy["max_return_visits"] if policy else 0),
                 "pass counters or cap drifted")
        _require(entry["status"] == _status(entry, policy),
                 "queue completion status drift")
        if policy:
            returns = _bounded_int(entry["return_visits"], 0,
                                   policy["max_return_visits"], "return count")
            _require(returns == max(0, entry["revisits_completed"] - MAX_REVISITS),
                     "return counter differs from actual passes")
            _bounded_int(entry["plateau_streak"], 0, MAX_PLATEAU,
                         "consecutive empty discovery returns")
            _bounded_int(entry["last_discovery_context_count"], 0, 100000,
                         "last unique discovery contexts")
            if entry["revisits_completed"] < MAX_REVISITS:
                _require(entry["next_due_epoch"] is None and
                         entry["last_scheduled_epoch"] is None,
                         "initial three passes must run without randomized delay")
            elif entry["status"] == "scheduled_return":
                _clock(entry["last_scheduled_epoch"])
                _clock(entry["next_due_epoch"])
                _require(entry["next_due_epoch"] == _due(
                    policy, entry["queue_id"], entry["passes"][-1]["pass_sha256"],
                    returns+1, entry["last_scheduled_epoch"]) and
                    entry["next_due_epoch"] > entry["last_scheduled_epoch"],
                    "random interval differs from attested schedule")
            else:
                _require(entry["next_due_epoch"] is None,
                         "retired queue source must not own a due ticket")
        seen = set(entry["initial_scenario_ids"])
        effective_seen = set()
        _require(len(seen) == len(entry["initial_scenario_ids"]),
                 "duplicate original experiment identity")
        known_families = set(entry["initial_risk_families"])
        past_rows: dict[str, dict] = {}
        for count, part in enumerate(entry["passes"], start=2):
            _require(part["pass_number"] == count and
                     part["pass_sha256"] == _hash({
                         k: v for k, v in part.items() if k != "pass_sha256"
                     }), "tampered or out-of-order boomerang pass")
            rows = part["results"]
            _require(type(rows) is list and rows and
                     part["scenarios_executed"] == len(rows) and
                     part["reverse_observations"] == part["forward_observations"] ==
                     sum(x["frames_executed"] for x in rows),
                     "boomerang pass observation counts changed")
            new_families = set().union(*(set(row["risk_counts"]) for row in rows))
            _require(part["distinct_effective_control_scenarios"] == len({
                _effective_identity(row["scenario"]) for row in rows}) and
                     part["distinct_effective_control_scenarios"] == len(rows) and
                     part["novel_failure_families"] ==
                     sorted(new_families - known_families) and
                     part["novel_family_count"] == len(new_families - known_families),
                     "claimed boomerang discoveries do not match observations")
            known_families.update(new_families)
            for row in rows:
                case = validate_scenario(row["scenario"])
                signature = _effective_identity(case)
                _require(row["source_digest"] == entry["source"]["source_digest"]
                         and row["reverse_audit_passed"] is True
                         and case["scenario_id"] not in seen
                         and signature not in effective_seen,
                         "duplicate effective controls, source splice or reverse audit failure")
                seen.add(case["scenario_id"])
                effective_seen.add(signature)
            for pair in part["comparisons"]:
                child = next((x for x in rows if
                              x["scenario"]["scenario_id"] == pair["child_scenario"]), None)
                parent = past_rows.get(pair["parent_scenario"])
                # Pass-two parent comes from the archived report and is checked
                # during verify_sources, without running its simulation again.
                if parent is not None and child is not None:
                    family = pair["target_failure_family"]
                    _require(pair["before"] == parent["risk_counts"].get(family, 0) and
                             pair["after"] == child["risk_counts"].get(family, 0) and
                             pair["observed_reduction"] == (pair["after"] < pair["before"]) and
                             pair["observed_regression"] == (pair["after"] > pair["before"]),
                             "counterfactual measurement does not match prior run")
            past_rows.update({row["scenario"]["scenario_id"]: row for row in rows})
        if verify_sources:
            _scene, source_archive = _load_source(entry)
            archived_by_id = {row["scenario"]["scenario_id"]: row
                              for row in source_archive["cases"]}
            for part in entry["passes"]:
                by_child = {r["scenario"]["scenario_id"]: r for r in part["results"]}
                for pair in part["comparisons"]:
                    parent = archived_by_id.get(pair["parent_scenario"])
                    child = by_child.get(pair["child_scenario"])
                    if parent is None:
                        parent = next((row for previous in entry["passes"]
                                       if previous["pass_number"] < part["pass_number"]
                                       for row in previous["results"]
                                       if row["scenario"]["scenario_id"] ==
                                          pair["parent_scenario"]), None)
                    _require(parent is not None and child is not None,
                             "counterfactual has no original parent/child receipt")
                    family = pair["target_failure_family"]
                    _require(pair["before"] == parent["risk_counts"].get(family, 0) and
                             pair["after"] == child["risk_counts"].get(family, 0) and
                             pair["observed_reduction"] == (pair["after"] < pair["before"]) and
                             pair["observed_regression"] == (pair["after"] > pair["before"]),
                             "counterfactual values changed since source re-analysis")
            if policy is not None:
                original_rows = list(source_archive["cases"])
                streak = 0
                discovered = 0
                for historical in entry["passes"]:
                    if historical["pass_number"] > 3:
                        contexts = _context_signatures(original_rows)
                        discovered = len(_context_signatures(
                            historical["results"]) - contexts)
                        streak = 0 if discovered else streak+1
                    original_rows.extend(historical["results"])
                _require(entry["last_discovery_context_count"] == discovered and
                         entry["plateau_streak"] == streak,
                         "source-derived discovery and plateau accounting diverged")
            archived_semantics = {_effective_identity(row["scenario"])
                                  for row in source_archive["cases"]}
            archived_semantics.add(_effective_identity(source_archive["baseline"]["scenario"]))
            _require(not (archived_semantics & effective_seen),
                     "boomerang revisited old effective controls without actual adjustment")
            _require(entry["initial_case_count"] == source_archive["budget_requested"] and
                     entry["initial_risk_families"] == source_archive["risk_families_observed"] and
                     entry["initial_scenario_ids"] == sorted({
                        row["scenario"]["scenario_id"] for row in source_archive["cases"]}) and
                     entry["initial_trace_count"] ==
                     source_archive["unique_controlled_trace_digests"],
                     "archived original counters changed in queue entry")
    _require(queue["source_projects"] == sorted({
        e["source"]["project_id"] for e in queue["entries"]}),
        "source-project groups changed")
    return {
        "verified": True, "generation": queue["generation"],
        "queued_sources": len(queue["entries"]),
        "pending_second_pass": sum(e["status"] == "awaiting_second_pass"
                                   for e in queue["entries"]),
        "pending_third_pass": sum(e["status"] == "awaiting_third_pass"
                                  for e in queue["entries"]),
        "complete_sources": sum(e["status"] in ("complete", "retired")
                                for e in queue["entries"]),
        "scheduled_returns": sum(e["status"] == "scheduled_return"
                                  for e in queue["entries"]),
        "overdue_returns": sum(e["status"] == "scheduled_return" and
                               e["next_due_epoch"] <= queue["last_tick_epoch"]
                               for e in queue["entries"]) if policy else 0,
        "next_return_epoch": min(
            (e["next_due_epoch"] for e in queue["entries"]
             if e["status"] == "scheduled_return"), default=None),
        "randomized_returns_enabled": policy is not None,
        "real_optimizer_updates": 0,
        "source_bytes_verified": verify_sources,
    }


def _previous_rows(entry: dict, archive: dict) -> list[dict]:
    rows = list(archive["cases"])
    rows.extend(row for part in entry["passes"] for row in part["results"])
    return rows


def _coverage_fill(scene: dict, used: set[str], effective: set[str],
                   chosen: list[dict], budget: int, prior_generation: int) -> None:
    for shift in range(1, 16):
        if len(chosen) >= budget:
            return
        seed = (prior_generation * 1871 + shift * 65537) % (2**31)
        for case in draft_scenarios(scene, budget=max(4, budget), seed=seed):
            identity = case["scenario_id"]
            signature = _effective_identity(case)
            if identity in used or signature in effective:
                continue
            chosen.append(case)
            used.add(identity)
            effective.add(signature)
            if len(chosen) >= budget:
                return


def _advance_entry(entry: dict, scene: dict, archive: dict, *,
                   budget: int, workers: int, frame_ms: int) -> dict:
    pass_number = entry["revisits_completed"] + 2
    _require(2 <= pass_number <= MAX_REVISITS + MAX_RETURN_VISITS + 1,
             "boomerang visit budget exhausted")
    latest = (archive["cases"] if pass_number == 2 else entry["passes"][-1]["results"])
    previous = _previous_rows(entry, archive)
    old_ids = {row["scenario"]["scenario_id"] for row in previous}
    old_families = set(archive["risk_families_observed"])
    for old_pass in entry["passes"]:
        for row in old_pass["results"]:
            old_families.update(row["risk_counts"])
    old_risk_signatures = {
        _hash({"family": risk, "control": row["scenario"],
               "trace": row["trace_digest"]})
        for row in previous for risk in row["risk_counts"]
    }
    _bounded_int(budget, 1, MAX_PROBES, "pass budget")
    _bounded_int(workers, 1, 8, "worker count")
    _bounded_int(frame_ms, 25, 250, "frame step")
    source_bounds = validate_scene(scene)
    per_sim = (source_bounds["total_ms"] + frame_ms - 1) // frame_ms + 1
    _require(budget * per_sim <= 180000, "boomerang aggregate frame quota exceeded")
    previous_families = set(archive["risk_families_observed"])
    if pass_number == 3:
        # On the third visit, newly exposed second-pass failures outrank
        # familiar high-volume problems already documented the first time.
        ordered = sorted(latest, key=lambda row: (
            -len(set(row["risk_counts"]) - previous_families),
            -len(row["risk_counts"]), -row["risk_severity"],
            row["scenario"]["scenario_id"]))
    else:
        ordered = sorted(latest, key=lambda row: (
            -row["risk_severity"], -len(row["risk_counts"]),
            row["scenario"]["scenario_id"]))
    proposals, parent_of, targeted = [], {}, {}
    used = set(old_ids)
    effective = {_effective_identity(row["scenario"]) for row in previous}
    effective.add(_effective_identity(archive["baseline"]["scenario"]))
    for iteration in range(1, 11):
        for row in ordered:
            if len(proposals) >= budget:
                break
            risks = sorted(row["risk_counts"],
                           key=lambda key: (-row["risk_counts"][key], key))
            signal = risks[(iteration - 1) % len(risks)] if risks else "coverage"
            # Odd runs attack, even runs repair. Both are grounded in risk counts.
            case = _targeted(row["scenario"], signal, iteration)
            signature = _effective_identity(case)
            if case["scenario_id"] in used or signature in effective:
                continue
            proposals.append(case)
            used.add(case["scenario_id"])
            effective.add(signature)
            parent_of[case["scenario_id"]] = row
            targeted[case["scenario_id"]] = signal
        if len(proposals) >= budget:
            break
    if len(proposals) < budget:
        # Honest exploration: no causal parent is invented for fallback probes.
        _coverage_fill(scene, used, effective, proposals, budget, pass_number)
    _require(len(proposals) == budget and len({x["scenario_id"] for x in proposals}) == budget,
             "no source-appropriate novel simulation controls left for this pass")
    results = _execute(scene, tuple(proposals), frame_ms, workers)
    _require(all(row["reverse_audit_passed"] for row in results),
             "reverse audit failed during revisit")
    new_families, new_signatures = set(), set()
    comparisons = []
    for row in results:
        new_families |= set(row["risk_counts"]) - old_families
        for family in row["risk_counts"]:
            signature = _hash({"family": family, "control": row["scenario"],
                               "trace": row["trace_digest"]})
            if signature not in old_risk_signatures:
                new_signatures.add(signature)
        parent = parent_of.get(row["scenario"]["scenario_id"])
        if parent is not None:
            family = targeted[row["scenario"]["scenario_id"]]
            before, after = parent["risk_counts"].get(family, 0), row["risk_counts"].get(family, 0)
            comparisons.append({
                "parent_scenario": parent["scenario"]["scenario_id"],
                "child_scenario": row["scenario"]["scenario_id"],
                "target_failure_family": family, "before": before, "after": after,
                "observed_reduction": after < before, "observed_regression": after > before,
                "counterfactual_not_independent_model_learning": True,
            })
    # A new parametrization need not be a new *camera* trace (environment proxy
    # changes alone can leave the camera unchanged). Count these separately.
    old_traces = {archive["baseline"]["trace_digest"]}
    old_traces.update(row["trace_digest"] for row in previous)
    new_traces = {row["trace_digest"] for row in results} - old_traces
    batch = {
        "schema_version": "skeleton.jeeves.boomerang_pass.v1",
        "pass_number": pass_number, "prior_evidence_reused": True,
        "original_simulation_reexecutions": 0,
        "scenarios_executed": len(results),
        "forward_observations": sum(row["frames_executed"] for row in results),
        "reverse_observations": sum(row["frames_executed"] for row in results),
        "novel_failure_families": sorted(new_families),
        "novel_family_count": len(new_families),
        "control_parse_policy": (
            "randomized_return_coverage_and_failure_priority" if pass_number > 3
            else "third_pass_new_failure_priority" if pass_number == 3
            else "second_pass_archived_failure_priority"),
        "novel_control_context_risk_signatures": len(new_signatures),
        "risk_signatures_not_independent_training_proof": True,
        "new_camera_trace_digests": len(new_traces),
        "distinct_effective_control_scenarios": len({
            _effective_identity(row["scenario"]) for row in results}),
        "random_seed_only_variants_excluded": True,
        "comparisons": comparisons, "results": results,
        "source_project_id": entry["source"]["project_id"],
        "source_digest": entry["source"]["source_digest"],
        "operator_worker_count": workers,
        "candidate_training_drafts_only": True,
        "actual_optimizer_updates": 0,
        "independent_game_design_quality_proven": False,
    }
    # Keep historic pass receipts within bounded queue storage.
    _require(len(_json(batch)) <= MAX_QUEUE_BYTES // 2,
             "boomerang pass artifact exceeds durable queue quota")
    batch["pass_sha256"] = _hash(batch)
    return batch


def advance_queue(queue: dict, *, max_entries: int = 1, probes: int = 8,
                  workers: int = 1, frame_ms: int = 100,
                  now_epoch: int | None = None) -> dict:
    """Execute only eligible work, mixing due old simulations into the queue.

    The caller initiates each tick. Persist the returned immutable generation;
    this function does not spin background timers or silently rerun old frames.
    """
    verify_queue(queue, verify_sources=True)
    _bounded_int(max_entries, 1, MAX_ENTRIES, "maximum processed queue entries")
    _bounded_int(probes, 1, MAX_PROBES, "probes per return")
    policy = queue.get("reshuffle_policy")
    if policy is None:
        pending = [i for i, entry in enumerate(queue["entries"])
                   if entry["revisits_completed"] < MAX_REVISITS]
        _require(bool(pending), "boomerang queue already completed all three passes")
        now = None
    else:
        now = _clock(now_epoch)
        _require(now >= queue["last_tick_epoch"],
                 "UTC queue clock rollback refused")
        pending = _due_work(queue, now)
        _require(bool(pending), "no boomerang source is due for a control parse; "
                 "consult next_return_epoch in --inspect")
    updated = deepcopy(queue)
    for index in pending[:max_entries]:
        previous = queue["entries"][index]
        scene, archive = _load_source(previous)
        result = _advance_entry(previous, scene, archive,
                                budget=probes, workers=workers, frame_ms=frame_ms)
        next_entry = updated["entries"][index]
        next_entry["passes"].append(result)
        next_entry["revisits_completed"] += 1
        if policy is not None:
            next_entry["return_visits"] = max(
                0, next_entry["revisits_completed"] - MAX_REVISITS)
            if result["pass_number"] > 3:
                history = _previous_rows(previous, archive)
                before = _context_signatures(history)
                after = _context_signatures(result["results"])
                newfound = len(after - before)
                next_entry["last_discovery_context_count"] = newfound
                next_entry["plateau_streak"] = (
                    0 if newfound else previous["plateau_streak"]+1)
            next_entry["status"] = _status(next_entry, policy)
            if next_entry["status"] == "scheduled_return":
                next_entry["last_scheduled_epoch"] = now
                next_entry["next_due_epoch"] = _due(
                    policy, next_entry["queue_id"], result["pass_sha256"],
                    next_entry["return_visits"]+1, now)
            else:
                next_entry["last_scheduled_epoch"] = None
                next_entry["next_due_epoch"] = None
        else:
            next_entry["status"] = ("awaiting_third_pass" if
                                   next_entry["revisits_completed"] == 1 else "complete")
    updated["parent_queue_sha256"] = queue["queue_sha256"]
    updated["generation"] += 1
    if policy is not None:
        updated["last_tick_epoch"] = now
    output = _receipt({k: v for k, v in updated.items() if k != "queue_sha256"})
    _require(len(_json(output)) <= MAX_QUEUE_BYTES,
             "queue snapshot exceeds durable bounded artifact size")
    verify_queue(output, verify_sources=True)
    return output

def retraining_review_drafts(queue: dict) -> tuple[dict, ...]:
    """Novel source-linked discoveries to be independently labeled, never SGD."""
    verify_queue(queue)
    cases = []
    seen = set()
    for entry in queue["entries"]:
        for part in entry["passes"]:
            for row in part["results"]:
                # Only newly discovered failure types, or measured worsening
                # relative to an explicitly recorded parent, merit review.
                novel = set(row["risk_counts"]) & set(part["novel_failure_families"])
                parent = next((c for c in part["comparisons"]
                               if c["child_scenario"] == row["scenario"]["scenario_id"]), None)
                regressed = bool(parent is not None and parent["observed_regression"])
                if not novel and not regressed:
                    continue
                signature = _hash({"source": entry["source"]["source_digest"],
                                   "trace": row["trace_digest"],
                                   "risks": sorted(novel)})
                if signature in seen:
                    continue
                seen.add(signature)
                for direction in ("forward_root_cause", "reverse_forensic",
                                  "minimize_and_retest"):
                    cases.append({
                        "schema_version": "skeleton.jeeves.boomerang_review_draft.v1",
                        "draft_id": _hash({"group": signature, "direction": direction}),
                        "source_project_id": entry["source"]["project_id"],
                        "source_evidence_group": signature,
                        "pass_number": part["pass_number"],
                        "scenario_id": row["scenario"]["scenario_id"],
                        "direction": direction,
                        "new_failure_families": sorted(novel),
                        "observed_parent_regression": regressed,
                        "first_observations": row["first_evidence"],
                        "review_status": "quarantined_needs_independent_labels",
                        "model_optimizer_eligible": False,
                        "independent_examples_added": 0,
                        "model_training_performed": False,
                    })
    return tuple(cases)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--create", action="store_true")
    modes.add_argument("--enqueue", action="store_true")
    modes.add_argument("--advance", action="store_true")
    modes.add_argument("--reshuffle", action="store_true",
                       help="activate reproducible randomized returns on an existing queue")
    modes.add_argument("--inspect", action="store_true")
    parser.add_argument("--queue", type=Path, help="existing immutable queue snapshot")
    parser.add_argument("--scene", type=Path, help="original rights-reviewed scene")
    parser.add_argument("--archive", type=Path, help="existing verified adaptive campaign")
    parser.add_argument("--output", type=Path, help="new immutable queue generation")
    parser.add_argument("--draft-output", type=Path, help="new quarantined review JSONL")
    parser.add_argument("--max-entries", type=int, default=1)
    parser.add_argument("--probes", type=int, default=8)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--frame-ms", type=int, default=100)
    parser.add_argument("--now-epoch", type=int,
                        help="explicit UTC clock for controlled replay or scheduling")
    parser.add_argument("--shuffle-seed", type=int, default=19)
    parser.add_argument("--min-return-seconds", type=int, default=3600)
    parser.add_argument("--max-return-seconds", type=int, default=86400)
    parser.add_argument("--max-return-visits", type=int, default=16)
    parser.add_argument("--plateau-limit", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        if args.create:
            _require(args.scene is not None and args.archive is not None
                     and args.queue is None and args.output is not None,
                     "--create requires source scene, finished archive and new output")
            result = create_queue(args.scene, args.archive)
        else:
            _require(args.queue is not None, "existing queue snapshot required")
            prior = _checked_file(args.queue, MAX_QUEUE_BYTES)
            verify_queue(prior, verify_sources=True)
            if args.enqueue:
                _require(args.scene is not None and args.archive is not None
                         and args.output is not None,
                         "--enqueue needs archived scene, report and new output")
                result = enqueue(prior, args.scene, args.archive)
            elif args.advance:
                _require(args.scene is None and args.archive is None
                         and args.output is not None,
                         "--advance only accepts the existing anchored queue")
                result = advance_queue(prior, max_entries=args.max_entries,
                                       probes=args.probes, workers=args.workers,
                                       frame_ms=args.frame_ms,
                                       now_epoch=args.now_epoch)
            elif args.reshuffle:
                _require(args.scene is None and args.archive is None
                         and args.output is not None,
                         "--reshuffle only accepts a pinned existing queue")
                result = enable_reshuffle(
                    prior, seed=args.shuffle_seed,
                    min_delay_seconds=args.min_return_seconds,
                    max_delay_seconds=args.max_return_seconds,
                    max_return_visits=args.max_return_visits,
                    plateau_limit=args.plateau_limit,
                    now_epoch=args.now_epoch)
            else:
                _require(args.scene is None and args.archive is None
                         and args.output is None,
                         "--inspect does not create new simulation artifacts")
                print(json.dumps(verify_queue(prior, verify_sources=True), sort_keys=True))
                return 0
        verify_queue(result, verify_sources=True)
        if args.draft_output is not None:
            drafts = retraining_review_drafts(result)
            _write_new_bytes(args.draft_output, b"".join(
                _json(draft) + b"\n" for draft in drafts))
        _write_new(args.output, result)
        print(json.dumps({**verify_queue(result), "queue_sha256": result["queue_sha256"],
                          "new_queue_file": str(args.output),
                          "weights_trained": False}, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:450],
                          "weights_trained": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
