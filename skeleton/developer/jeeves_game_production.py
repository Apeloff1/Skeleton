"""Resumable Jeeves game-studio completion workledger.

There is no lifetime attempt counter, hard project deadline, auto-truncation
or silent "give up" transition. Each invocation is resource-bounded; the
operator/scheduler can resume indefinitely using an append-only CAS journal.
Only independently executed evaluators can claim a passed technical check.
The tracker never treats a static preview as a completed playable game.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

SCHEMA = "skeleton.jeeves.game_production_policy.v1"
EVENT_SCHEMA = "skeleton.jeeves.game_production_event.v1"
QUALITY_FLOOR = 90
REQUIRED_GATES = (
    "world_and_lore", "characters_and_npcs", "story_continuity",
    "quests_and_dialogue", "scenes_and_level_design", "gameplay_and_mechanics",
    "original_assets", "animations_and_vfx", "cinematics_and_camera",
    "music_and_ambience", "user_interface", "localization",
    "accessibility", "market_quality", "source_integrity",
    "runtime_boot", "full_playthrough", "performance_and_release",
)
AUTOMATED_GATES = frozenset(("market_quality", "source_integrity", "runtime_boot"))
# A terminal success requires a real domain verifier for every discipline.
# Mere JSON receipts or an observed Godot boot are never enough.
EXPECTED_EVIDENCE_OWNERS = {
    "market_quality": "independent_market_audit",
    "source_integrity": "canonical_source",
    "runtime_boot": "godot_boot",
    "full_playthrough": "verified_end_to_end_run",
    "performance_and_release": "verified_hardware_and_release",
    **{name: "qualified_" + name for name in REQUIRED_GATES if name not in {
        "market_quality", "source_integrity", "runtime_boot",
        "full_playthrough", "performance_and_release"}},
}
HASH = re.compile(r"^[0-9a-f]{64}$")


class ProductionError(ValueError):
    pass


def _bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def _digest(value: object) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _safe_folder(root: Path, *, create: bool) -> Path:
    from skeleton.developer.game_cli import _load
    _load(root)
    folder = root
    for name in (".jeeves", "production"):
        folder = folder / name
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise ProductionError("unsafe Jeeves production evidence directory")
        if create:
            folder.mkdir(exist_ok=True)
    return folder


def _read(path: Path, *, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ProductionError("production evidence file missing, unsafe or too large")
    data = path.read_bytes()
    if len(data) > maximum:
        raise ProductionError("production evidence file exceeds bound")
    return data


def _publish(path: Path, value: object) -> None:
    """Atomic create-only file, no silent overwrites or replacement authority."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        raise ProductionError("production receipt already exists; concurrent write or attempt replay")
    content = _bytes(value) + b"\n"
    fd, temp = tempfile.mkstemp(prefix=".jeeves-production-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def init(root: Path, *, target: str, genre: str, period: str) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _ident, _period
    from skeleton.developer.game_cli import _load
    from skeleton.jeeves.game_console_catalog import resolve_console
    cfg = _load(root)
    target = resolve_console(target)
    _ident(genre, "genre")
    _period(period)
    folder = _safe_folder(root, create=True)
    policy = {
        "schema": SCHEMA, "workspace_sha256": _digest(cfg), "era": cfg["era"],
        "target": target.target_id, "genre": genre, "period": period,
        "gates": list(REQUIRED_GATES), "asset_qa_floor": QUALITY_FLOOR,
        "market_min_critic_score": 85, "market_dual_top_quartile": True,
        "asset_quality_policy": "all_dimensions_at_least_90",
        "completion_rule": "every_gate_independently_verified",
        "relaxation_allowed": False,
        "total_attempt_cap": None, "project_deadline": None,
        "evidence_retention": "append_only_no_automatic_deletion",
    }
    path = folder / "policy.json"
    if path.exists():
        actual = _read_policy(root)
        if actual != policy:
            raise ProductionError("existing production policy cannot be relaxed or retargeted")
        return {"ok": True, "action": "production-init", "existing": True,
                "policy_sha256": _digest(actual), "gates": list(REQUIRED_GATES)}
    _publish(path, policy)
    return {"ok": True, "action": "production-init", "existing": False,
            "policy_sha256": _digest(policy), "gates": list(REQUIRED_GATES)}


def _read_policy(root: Path) -> dict[str, Any]:
    from skeleton.developer.game_cli import _load
    from skeleton.developer.jeeves_game_quality import _period, _ident
    from skeleton.jeeves.game_console_catalog import resolve_console
    folder = _safe_folder(root, create=False)
    try:
        policy = json.loads(_read(folder / "policy.json", maximum=16 * 1024))
    except (ValueError, UnicodeError) as exc:
        raise ProductionError("invalid production policy JSON") from exc
    if not isinstance(policy, dict) or policy.get("schema") != SCHEMA:
        raise ProductionError("unsupported production policy")
    cfg = _load(root)
    if policy.get("workspace_sha256") != _digest(cfg) or policy.get("era") != cfg["era"]:
        raise ProductionError("game workspace changed; existing production policy needs reconciliation")
    if policy.get("gates") != list(REQUIRED_GATES) or policy.get("asset_qa_floor") != QUALITY_FLOOR:
        raise ProductionError("production quality gates were relaxed or changed")
    if policy.get("market_min_critic_score") != 85 or policy.get("market_dual_top_quartile") is not True:
        raise ProductionError("market success requirements were changed")
    if policy.get("asset_quality_policy") != "all_dimensions_at_least_90":
        raise ProductionError("asset quality requirement changed")
    if policy.get("completion_rule") != "every_gate_independently_verified":
        raise ProductionError("completion predicate changed")
    if policy.get("relaxation_allowed") is not False or policy.get("total_attempt_cap") is not None or policy.get("project_deadline") is not None:
        raise ProductionError("unapproved production plan limits/relaxation")
    if policy.get("evidence_retention") != "append_only_no_automatic_deletion":
        raise ProductionError("evidence retention was weakened")
    if resolve_console(policy["target"]).target_id != policy["target"]:
        raise ProductionError("production console target no longer registered")
    _ident(policy["genre"], "genre")
    _period(policy["period"])
    if set(policy) != {
        "schema", "workspace_sha256", "era", "target", "genre", "period",
        "gates", "asset_qa_floor", "market_min_critic_score",
        "market_dual_top_quartile", "asset_quality_policy", "completion_rule",
        "relaxation_allowed", "total_attempt_cap", "project_deadline",
        "evidence_retention",
    }:
        raise ProductionError("unrecognized production policy fields")
    return policy


def _events(root: Path, policy_sha: str):
    """Stream unbounded historical events, checking every hash-chain link."""
    folder = _safe_folder(root, create=False) / "events"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ProductionError("unsafe production event ledger")
    if not folder.exists():
        return
    previous = policy_sha
    index = 0
    for path in sorted(folder.iterdir()):
        if path.name.startswith(".jeeves-production-"):
            # Interrupted pre-commit scratch has no durable event authority.
            continue
        if path.suffix != ".json" or path.name != f"{index + 1:012d}.json":
            raise ProductionError("ledger entry number missing, duplicated or out of order")
        try:
            item = json.loads(_read(path, maximum=32 * 1024))
        except (ValueError, UnicodeError) as exc:
            raise ProductionError("corrupt production event") from exc
        if not isinstance(item, dict) or set(item) != {
            "schema", "sequence", "policy_sha256", "previous_sha256", "gate",
            "outcome", "evidence_sha256", "evidence_kind", "reason",
            "pass_number", "at_utc", "novel_evidence", "digest"
        }:
            raise ProductionError("invalid event fields")
        if (item["schema"] != EVENT_SCHEMA or item["sequence"] != index + 1
            or item["previous_sha256"] != previous or item["policy_sha256"] != policy_sha
            or item["gate"] not in REQUIRED_GATES
            or item["outcome"] not in ("passed", "failed", "blocked")
            or not isinstance(item["evidence_sha256"], str)
            or HASH.fullmatch(item["evidence_sha256"]) is None
            or type(item["pass_number"]) is not int or item["pass_number"] < 1
            or type(item["novel_evidence"]) is not bool
            or not isinstance(item["reason"], str) or len(item["reason"]) > 2000
            or not isinstance(item["at_utc"], str)):
            raise ProductionError("invalid event identity")
        if item["evidence_kind"] not in (
            "canonical_source", "market_operator_evidence", "godot_boot",
            "operator_observation", *EXPECTED_EVIDENCE_OWNERS.values()
        ):
            raise ProductionError("unsupported evidence owner")
        calculated = _digest({k: v for k, v in item.items() if k != "digest"})
        if calculated != item["digest"]:
            raise ProductionError("production event hash mismatch")
        previous = item["digest"]
        index += 1
        yield item


def status(root: Path) -> dict[str, Any]:
    policy = _read_policy(root)
    digest = _digest(policy)
    latest: dict[str, dict[str, Any]] = {}
    counts = {key: 0 for key in REQUIRED_GATES}
    total = 0
    last_digest = digest
    for event in _events(root, digest):
        total += 1
        last_digest = event["digest"]
        latest[event["gate"]] = event
        counts[event["gate"]] += 1
    gates = []
    for gate in REQUIRED_GATES:
        current = latest.get(gate)
        gates.append({
            "gate": gate, "attempts": counts[gate],
            "outcome": current["outcome"] if current else "not_evaluated",
            "last_reason": current["reason"] if current else "no validator output",
            "last_evidence_kind": current["evidence_kind"] if current else None,
            "needs_more_work": current is None or current["outcome"] != "passed",
        })
    # NOT just an "all green" count: require exactly the designated
    # independent/engine-backed evidence owner for each disciplinary gate.
    # Most owners are not yet implemented, so incomplete studios remain open.
    qualified = all(
        gate in latest and latest[gate]["outcome"] == "passed"
        and latest[gate]["evidence_kind"] == EXPECTED_EVIDENCE_OWNERS[gate]
        for gate in REQUIRED_GATES
    )
    return {
        "ok": True, "action": "production-status", "schema": SCHEMA,
        "policy_sha256": digest, "last_event_sha256": last_digest,
        "recorded_events": total, "gates": gates,
        "passed_gates": sum(x["outcome"] == "passed" for x in gates),
        "remaining_gates": sum(x["needs_more_work"] for x in gates),
        "project_complete": qualified, "production_qualified": qualified,
        "model_training_complete": False,
        "no_lifetime_attempt_limit": True, "no_automatic_evidence_pruning": True,
        "next_work": [x["gate"] for x in gates if x["needs_more_work"]],
        "quality_floor": QUALITY_FLOOR,
    }


def _probe(root: Path, policy: dict[str, Any], gate: str) -> tuple[str, str, str, str]:
    """Run an actual existing checker; unimplemented validators stay BLOCKED."""
    if gate == "source_integrity":
        from skeleton.developer.game_cli import _read_forge
        try:
            _, files, receipt = _read_forge(root)
            return "passed", receipt["sha256"], "canonical_source", f"{len(files)} source files hash-verified"
        except (ValueError, OSError) as exc:
            return "failed", _digest({"gate": gate, "error": str(exc)}), "canonical_source", str(exc)[:2000]
    if gate == "market_quality":
        from skeleton.developer.jeeves_game_quality import rank_cohort
        try:
            ranking = rank_cohort(root, console=policy["target"],
                                  genre=policy["genre"], period=policy["period"])
            if ranking["eligible_for_inspiration"]:
                # Evidence is operator-reported and is NOT independent pass.
                return ("blocked", ranking["profile_sha256"], "market_operator_evidence",
                        "top-tier rank computed, independent sales/review corroboration required")
            return ("failed", ranking["profile_sha256"], "market_operator_evidence",
                    "no dual-axis top-tier reference titles")
        except (ValueError, OSError) as exc:
            return "failed", _digest({"gate": gate, "error": str(exc)}), "market_operator_evidence", str(exc)[:2000]
    if gate == "runtime_boot":
        from skeleton.developer.game_cli import _read_forge
        from skeleton.forge.playtest import playtest
        try:
            _, files, receipt = _read_forge(root)
            outcome = playtest(files, frames=300, timeout=120)
            digest = _digest({"source_sha256": receipt["sha256"], "playtest": outcome})
            if outcome.get("passed") is True:
                return "passed", digest, "godot_boot", "actual headless Godot boot passed, NOT a full playthrough"
            return "failed", digest, "godot_boot", f"headless Godot boot: {outcome.get('status', 'unknown')}"
        except (ValueError, OSError) as exc:
            return "failed", _digest({"gate": gate, "error": str(exc)}), "godot_boot", str(exc)[:2000]
    return "blocked", _digest({"gate":gate,"unavailable":True}), "operator_observation", "independent stage-specific evaluator not connected"


def cycle(root: Path, *, passes: int = 1, gate: str | None = None,
          repair_generated: bool = False) -> dict[str, Any]:
    """One explicit bounded execution slice; total project lifetime is uncapped."""
    if type(passes) is not int or not 1 <= passes <= 8:
        raise ProductionError("a single cycle accepts 1-8 scrutiny passes, resumable without lifetime cap")
    if gate is not None and gate not in REQUIRED_GATES:
        raise ProductionError("unknown immutable completion gate")
    if type(repair_generated) is not bool:
        raise ProductionError("repair_generated must be bool")
    policy = _read_policy(root)
    folder = _safe_folder(root, create=True) / "events"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ProductionError("unsafe event directory")
    folder.mkdir(exist_ok=True)
    state = status(root)
    seq = state["recorded_events"]
    previous = state["last_event_sha256"]
    latest: dict[str, dict[str, Any]] = {}
    for entry in _events(root, state["policy_sha256"]):
        latest[entry["gate"]] = entry
    observations = []
    repaired_gates: set[str] = set()
    # Only true evaluators consume budget. Missing subsystem tooling is never
    # classified as a successful test or retried pointlessly in a tight loop.
    selected = (gate,) if gate is not None else tuple(sorted(AUTOMATED_GATES))
    for iteration in range(1, passes + 1):
        for name in selected:
            result, evidence, owner, reason = _probe(root, policy, name)
            if (repair_generated and result == "failed"
                and name in {"source_integrity", "runtime_boot"}
                and name not in repaired_gates):
                repaired_gates.add(name)
                from types import SimpleNamespace
                from skeleton.developer.game_cli import _build
                try:
                    outcome = _build(root, SimpleNamespace(
                        overwrite=True, playtest="off", repair_mode="apply"))
                    repair_detail = "existing canonical GameForge repair attempted; build succeeded" if outcome.get("ok") else "existing canonical GameForge repair reported failure"
                except (ValueError, OSError) as exc:
                    repair_detail = "canonical GameForge repair failed: " + str(exc)[:500]
                # Quality bar remains identical; re-run ORIGINAL test.
                result, evidence, owner, reason = _probe(root, policy, name)
                reason = (repair_detail + "; rechecked: " + reason)[:2000]
            current = latest.get(name)
            # Record EVERY parse, including identical observations, forever.
            # Duplicated hashes are not independent quality evidence.
            novelty = not (current and all((
                current["outcome"] == result,
                current["evidence_sha256"] == evidence,
                current["reason"] == reason,
            )))
            seq += 1
            payload = {
                "schema": EVENT_SCHEMA, "sequence": seq,
                "policy_sha256": state["policy_sha256"],
                "previous_sha256": previous,
                "gate": name, "outcome": result,
                "evidence_sha256": evidence, "evidence_kind": owner,
                "reason": reason, "pass_number": iteration,
                "at_utc": datetime.now(timezone.utc).isoformat(),
                "novel_evidence": bool(novelty),
            }
            payload["digest"] = _digest(payload)
            _publish(folder / f"{seq:012d}.json", payload)
            latest[name] = payload
            previous = payload["digest"]
            observations.append({"gate": name, "outcome": result,
                                 "new_evidence": bool(novelty), "reason": reason})
    after = status(root)
    return {"ok": True, "action": "production-cycle", "passes_in_this_slice": passes,
            "observations": observations,
            "recorded_events": after["recorded_events"],
            "total_attempt_cap": None,
            "project_deadline": None,
            "quality_threshold_lowered": False,
            "project_complete": after["project_complete"],
            "pending_gates": after["next_work"],
            "repair_generated_requested": repair_generated,
            "repairs_attempted": sorted(repaired_gates),
            "next_step": "repair failed prerequisites, gather independent evidence and run another resumable cycle"}
