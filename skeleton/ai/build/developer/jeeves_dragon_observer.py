"""Consented, metadata-only Dragon witness for the EXISTING Jeeves game pipeline.

A durable projection of canonical production receipts and explicitly submitted
instrumentation fingerprints. It is neither a camera/screen recorder nor a
second execution, memory, training, or quality authority. No raw prompts, video,
chat, tool arguments, model reasoning, passwords or asset bytes are stored.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skeleton.developer import jeeves_game_production as production

SCHEMA = "skeleton.jeeves.dragon_builder_witness.v1"
EVENT_SCHEMA = "skeleton.jeeves.dragon_builder_witness_event.v1"
ACTORS = frozenset({"jeeves", "builder", "dragon", "director", "engine", "reviewer", "operator"})
PHASES = frozenset({
    "vision", "story", "canon", "world", "characters", "quests", "dialogue",
    "assets", "animation", "audio", "camera", "assembly", "runtime",
    "playthrough", "review", "learning", "release",
})
ACTIONS = frozenset({
    "plan", "propose", "review", "authorize", "apply", "tool_call",
    "tool_result", "build", "evaluate", "quality_gate", "playtest",
    "frame_sample", "checkpoint", "recover", "rollback", "study",
})
OUTCOMES = frozenset({"passed", "failed", "blocked", "in_progress", "cancelled"})
HEX = production.HASH
MAX_SYNC_PER_CALL = 256

_GATE_PHASE = {
    "world_and_lore": "world", "characters_and_npcs": "characters",
    "story_continuity": "canon", "quests_and_dialogue": "quests",
    "scenes_and_level_design": "world", "gameplay_and_mechanics": "runtime",
    "original_assets": "assets", "animations_and_vfx": "animation",
    "cinematics_and_camera": "camera", "music_and_ambience": "audio",
    "user_interface": "assembly", "localization": "assembly",
    "accessibility": "review", "market_quality": "review",
    "source_integrity": "assembly", "runtime_boot": "runtime",
    "full_playthrough": "playthrough", "performance_and_release": "release",
}


class WitnessError(production.ProductionError):
    """Invalid consent, untrusted observation or corrupt witness chain."""


def _folder(root: Path, *, create: bool = False) -> Path:
    parent = production._safe_folder(root, create=False)
    if (parent / "dragon_observer_revoked.json").exists():
        raise WitnessError("Dragon observation consent revoked for this workspace")
    folder = parent / "dragon_observer"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise WitnessError("unsafe Dragon observer directory")
    if create:
        folder.mkdir(exist_ok=True)
    return folder


def _policy(root: Path) -> dict[str, Any]:
    folder = _folder(root)
    try:
        import json
        obj = json.loads(production._read(folder / "policy.json", maximum=8192))
    except (ValueError, UnicodeError) as exc:
        raise WitnessError("Dragon recording requires explicit consented observer-start") from exc
    expected = _policy_object(production.status(root)["policy_sha256"])
    if obj != expected:
        raise WitnessError("observer consent policy or production identity changed")
    return obj


def _policy_object(production_sha: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "production_policy_sha256": production_sha,
        "capture_consent": True,
        "recording": "explicit_metadata_fingerprints_only",
        "raw_screen_audio_video_or_chat": False,
        "model_training_or_weight_promotion": False,
        "evidence_promotion": "independent_review_required",
    }


def start(root: Path, *, consent: bool = False) -> dict[str, Any]:
    """Operator opts in; never assume consent from a CLI invocation."""
    if consent is not True:
        raise WitnessError("start requires explicit --consent")
    base = _folder(root)
    expected = _policy_object(production.status(root)["policy_sha256"])
    path = base / "policy.json"
    if path.exists():
        _policy(root)
        return {"ok": True, "action": "dragon-observe-start", "existing": True,
                "policy_sha256": production._digest(expected)}
    base = _folder(root, create=True)
    production._publish(base / "policy.json", expected)
    return {"ok": True, "action": "dragon-observe-start", "existing": False,
            "policy_sha256": production._digest(expected),
            "capture": "explicit instrumented metadata; no screen recording"}


def _source_events(root: Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    return list(production._events(root, policy["production_policy_sha256"]))


def _observations(root: Path, policy: dict[str, Any],
                  source: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Verify both own chain and every cross-ledger source reference."""
    folder = _folder(root) / "events"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise WitnessError("unsafe Dragon witness event directory")
    if not folder.exists():
        return []
    import json
    previous = production._digest(policy)
    events: list[dict[str, Any]] = []
    for path in sorted(folder.iterdir()):
        if path.name.startswith(".jeeves-production-"):
            continue  # Crash before atomic publication; never authoritative.
        index = len(events) + 1
        if path.name != f"{index:012d}.json":
            raise WitnessError("Dragon witness event missing or reordered")
        try:
            event = json.loads(production._read(path, maximum=8192))
        except (ValueError, UnicodeError) as exc:
            raise WitnessError("Dragon witness event unreadable") from exc
        fields = {
            "schema", "sequence", "previous_sha256", "policy_sha256",
            "actor", "phase", "action", "outcome", "evidence_sha256",
            "source_sequence", "source_event_sha256", "gate", "trust",
            "at_utc", "digest",
        }
        if not isinstance(event, dict) or set(event) != fields:
            raise WitnessError("unsupported Dragon witness event fields")
        if (event["schema"] != EVENT_SCHEMA or event["sequence"] != index
            or event["policy_sha256"] != production._digest(policy)
            or event["previous_sha256"] != previous
            or not isinstance(event["actor"], str)
            or not isinstance(event["phase"], str)
            or not isinstance(event["action"], str)
            or not isinstance(event["outcome"], str)
            or event["actor"] not in ACTORS or event["phase"] not in PHASES
            or event["action"] not in ACTIONS or event["outcome"] not in OUTCOMES
            or not isinstance(event["evidence_sha256"], str)
            or HEX.fullmatch(event["evidence_sha256"]) is None
            or not isinstance(event["trust"], str)
            or not isinstance(event["at_utc"], str)
            or len(event["at_utc"]) > 64
            or production._digest({k: v for k, v in event.items() if k != "digest"})
                != event["digest"]):
            raise WitnessError("Dragon witness event identity/hash mismatch")
        if event["trust"] == "canonical_production_receipt":
            seq = event["source_sequence"]
            if (type(seq) is not int or not 1 <= seq <= len(source)
                or event["source_event_sha256"] != source[seq - 1]["digest"]
                or event["evidence_sha256"] != source[seq - 1]["evidence_sha256"]
                or not isinstance(event["gate"], str)
                or event["gate"] not in _GATE_PHASE
                or event["gate"] != source[seq - 1]["gate"]
                or event["outcome"] != source[seq - 1]["outcome"]
                or event["action"] != "quality_gate"
                or event["phase"] != _GATE_PHASE[event["gate"]]
                or event["actor"] != _gate_actor(event["gate"])):
                raise WitnessError("Dragon witness no longer matches canonical production evidence")
        elif event["trust"] in {"unverified_operator_telemetry", "observed_cli_result"}:
            if (event["source_sequence"] is not None
                or event["source_event_sha256"] is not None
                or event["gate"] is not None):
                raise WitnessError("operator telemetry cannot impersonate verified evidence")
        else:
            raise WitnessError("unknown Dragon witness trust class")
        previous = event["digest"]
        events.append(event)
    return events


def _gate_actor(gate: str) -> str:
    if gate in {"runtime_boot", "full_playthrough", "gameplay_and_mechanics"}:
        return "engine"
    if gate in {"market_quality", "performance_and_release", "accessibility"}:
        return "reviewer"
    if gate in {"story_continuity", "quests_and_dialogue", "world_and_lore"}:
        return "jeeves"
    return "builder"


def _append(root: Path, policy: dict[str, Any], current: list[dict[str, Any]],
            *, actor: str, phase: str, action: str, outcome: str,
            evidence_sha256: str, trust: str, source_sequence: int | None = None,
            source_event_sha256: str | None = None, gate: str | None = None) -> dict[str, Any]:
    if (not all(isinstance(value, str) for value in (actor, phase, action, outcome))
        or actor not in ACTORS or phase not in PHASES or action not in ACTIONS
        or outcome not in OUTCOMES or not isinstance(evidence_sha256, str)
        or HEX.fullmatch(evidence_sha256) is None):
        raise WitnessError("instrumentation requires allowed actor, phase, action, outcome, SHA-256")
    seq = len(current) + 1
    event = {
        "schema": EVENT_SCHEMA, "sequence": seq,
        "previous_sha256": current[-1]["digest"] if current else production._digest(policy),
        "policy_sha256": production._digest(policy), "actor": actor, "phase": phase,
        "action": action, "outcome": outcome, "evidence_sha256": evidence_sha256,
        "source_sequence": source_sequence, "source_event_sha256": source_event_sha256,
        "gate": gate, "trust": trust, "at_utc": datetime.now(timezone.utc).isoformat(),
    }
    event["digest"] = production._digest(event)
    folder = _folder(root, create=True) / "events"
    if folder.is_symlink():
        raise WitnessError("unsafe event directory")
    folder.mkdir(exist_ok=True)
    production._publish(folder / f"{seq:012d}.json", event)
    current.append(event)
    return event


def record_action(root: Path, *, actor: str, phase: str, action: str,
                  outcome: str, evidence_sha256: str) -> dict[str, Any]:
    """Accept a hashed external action witness; NEVER assert it was executed.

    Hosts may bind this to actual committed tool/operation receipts later;
    command-line operator claims remain explicitly unverified.
    """
    policy = _policy(root)
    current = _observations(root, policy, _source_events(root, policy))
    event = _append(root, policy, current, actor=actor, phase=phase, action=action,
                    outcome=outcome, evidence_sha256=evidence_sha256,
                    trust="unverified_operator_telemetry")
    return {"ok": True, "action": "dragon-observe-action",
            "event_sha256": event["digest"], "sequence": event["sequence"],
            "independently_verified": False, "training_performed": False}


def sync(root: Path, *, limit: int = MAX_SYNC_PER_CALL) -> dict[str, Any]:
    """Idempotently follow canonical quality checks; recover interrupted sync."""
    if type(limit) is not int or not 1 <= limit <= MAX_SYNC_PER_CALL:
        raise WitnessError("observer sync limit must be 1..256 per slice")
    policy = _policy(root)
    source = _source_events(root, policy)
    current = _observations(root, policy, source)
    seen = {e["source_sequence"] for e in current if e["source_sequence"] is not None}
    appended = []
    for src in source:
        if src["sequence"] in seen:
            continue
        event = _append(
            root, policy, current, actor=_gate_actor(src["gate"]),
            phase=_GATE_PHASE[src["gate"]], action="quality_gate",
            outcome=src["outcome"], evidence_sha256=src["evidence_sha256"],
            trust="canonical_production_receipt",
            source_sequence=src["sequence"], source_event_sha256=src["digest"],
            gate=src["gate"],
        )
        seen.add(src["sequence"])
        appended.append(event["digest"])
        if len(appended) >= limit:
            break
    return {
        "ok": True, "action": "dragon-observe-sync", "appended": len(appended),
        "source_total": len(source), "source_observed": len(seen),
        "pending_source_events": len(source) - len(seen),
        "observer_events": len(current), "last_observer_sha256": current[-1]["digest"]
            if current else production._digest(policy),
        "actual_screen_capture": False, "model_training_performed": False,
    }


def cycle(root: Path, *, passes: int = 1, gate: str | None = None,
          repair_generated: bool = False) -> dict[str, Any]:
    """Run the existing bounded production slice, then reconcile Dragon.

    If observing fails after a successful production write, the existing
    authoritative receipt survives and a later sync repairs the projection.
    """
    _policy(root)
    before = sync(root)
    if before["pending_source_events"]:
        raise WitnessError("drain pending Dragon observations before running another cycle")
    result = production.cycle(root, passes=passes, gate=gate,
                              repair_generated=repair_generated)
    observed = sync(root)
    return {
        "ok": True, "action": "dragon-observe-cycle", "production": result,
        "witness": observed, "project_complete": result["project_complete"],
        "new_learning_weights": False,
    }


def status(root: Path) -> dict[str, Any]:
    policy = _policy(root)
    source = _source_events(root, policy)
    events = _observations(root, policy, source)
    by_actor = Counter(e["actor"] for e in events)
    by_phase = Counter(e["phase"] for e in events)
    by_outcome = Counter(e["outcome"] for e in events)
    observed = {e["source_sequence"] for e in events if e["source_sequence"] is not None}
    actual = production.status(root)
    return {
        "ok": True, "action": "dragon-observe-status",
        "records": len(events), "actor_counts": dict(sorted(by_actor.items())),
        "phase_counts": dict(sorted(by_phase.items())),
        "outcome_counts": dict(sorted(by_outcome.items())),
        "canonical_production_observations": len(observed),
        "unverified_action_observations": len(events) - len(observed),
        "instrumented_cli_observations": sum(
            e["trust"] == "observed_cli_result" for e in events),
        "operator_claims": sum(
            e["trust"] == "unverified_operator_telemetry" for e in events),
        "pending_source_events": len(source) - len(observed),
        "last_observer_sha256": events[-1]["digest"] if events else production._digest(policy),
        "production": {
            "passed_gates": actual["passed_gates"],
            "remaining_gates": actual["remaining_gates"],
            "project_complete": actual["project_complete"],
            "policy_sha256": actual["policy_sha256"],
        },
        "raw_recording_active": False, "trained_checkpoints": 0,
    }


def lessons(root: Path, *, page: int = 0, page_size: int = 64) -> dict[str, Any]:
    """Reproducible failure/recovery candidates; never automatic promotion."""
    if type(page) is not int or page < 0 or type(page_size) is not int or not 1 <= page_size <= 256:
        raise WitnessError("lesson pagination requires nonnegative page and 1..256 size")
    policy = _policy(root)
    source = _source_events(root, policy)
    events = _observations(root, policy, source)
    failures: dict[str, dict[str, Any]] = {}
    candidates = []
    for event in events:
        if event["trust"] != "canonical_production_receipt":
            continue
        gate = event["gate"]
        if event["outcome"] == "failed":
            failures[gate] = event
        elif event["outcome"] == "passed" and gate in failures:
            failed = failures.pop(gate)
            if failed["evidence_sha256"] != event["evidence_sha256"]:
                candidates.append({
                    "gate": gate, "actor": event["actor"], "phase": event["phase"],
                    "failure_sha256": failed["digest"], "recheck_sha256": event["digest"],
                    "evidence_changed": True, "actual_causal_learning_proven": False,
                    "eligible_for_weights": False, "review_required": True,
                })
    begin = page * page_size
    return {
        "ok": True, "action": "dragon-observe-lessons",
        "page": page, "page_size": page_size, "total": len(candidates),
        "candidates": candidates[begin:begin + page_size],
        "next_page": page + 1 if begin + page_size < len(candidates) else None,
        "promotion_performed": False, "review_required": True,
    }


def revoke(root: Path) -> dict[str, Any]:
    """Terminal revocation: leave a minimal tombstone, erase observer projection.

    Original canonical production receipts belong to the game producer, not
    the Dragon observer, and are intentionally not altered.
    """
    parent = production._safe_folder(root, create=False)
    tombstone = parent / "dragon_observer_revoked.json"
    if tombstone.is_symlink():
        raise WitnessError("unsafe consent revocation tombstone")
    if not tombstone.exists():
        production._publish(tombstone, {"schema": SCHEMA, "capture_consent": False})
    folder = parent / "dragon_observer"
    if folder.is_symlink():
        raise WitnessError("unsafe observer projection at revoke")
    if folder.exists():
        for node in folder.iterdir():
            if node.name == "events" and node.is_dir() and not node.is_symlink():
                for item in node.iterdir():
                    if item.is_symlink() or not item.is_file():
                        raise WitnessError("unsafe derived observer event")
                    item.unlink()
                node.rmdir()
            elif node.name == "policy.json" and node.is_file() and not node.is_symlink():
                node.unlink()
            else:
                raise WitnessError("unrecognized observer projection; manual review required")
        folder.rmdir()
    return {"ok": True, "action": "dragon-observe-revoke",
            "derived_observer_data_erased": True, "production_ledger_preserved": True,
            "observation_can_resume": False}

def observe_cli_result(root: Path, *, command: str, result: dict[str, Any]) -> dict[str, Any] | None:
    """Observe actual Jeeves/Builder CLI returns when prior opt-in exists.

    Only the SHA-256 of the returned object is retained. We neither intercept
    message bodies nor claim that a successful return proves the side effect.
    If consent has been revoked the witness remains permanently silent.
    """
    if not isinstance(command, str) or not isinstance(result, dict):
        raise WitnessError("a typed Jeeves action and result are required")
    if command.startswith("dragon-observe-"):
        return None
    parent = production._safe_folder(root, create=False)
    if (parent / "dragon_observer_revoked.json").exists():
        return None
    policy_path = parent / "dragon_observer" / "policy.json"
    if not policy_path.exists():
        return None
    policy = _policy(root)
    original = _source_events(root, policy)
    current = _observations(root, policy, original)
    if command.startswith("dragon-"):
        actor, phase = "dragon", "learning"
    elif command.startswith("director-"):
        actor, phase = "director", "world"
    elif command in {"propose", "plan", "context", "queue"}:
        actor, phase = "jeeves", "vision"
    elif command in {"review", "benchmark", "benchmark-matrix", "asset-gate"}:
        actor, phase = "reviewer", "review"
    else:
        actor, phase = "builder", "assembly"
    action = (
        command if command in ACTIONS else
        "playtest" if "playthrough" in command or "smoke" in command else
        "evaluate" if "audit" in command or "verify" in command else
        "tool_result"
    )
    outcome = "failed" if result.get("ok") is False else (
        "passed" if result.get("ok") is True else "in_progress")
    event = _append(
        root, policy, current, actor=actor, phase=phase, action=action,
        outcome=outcome, evidence_sha256=production._digest(result),
        trust="observed_cli_result",
    )
    return {"ok": True, "sequence": event["sequence"],
            "event_sha256": event["digest"],
            "actual_cli_return_observed": True,
            "side_effect_independently_verified": False,
            "raw_content_retained": False}


def trace(root: Path, *, page: int = 0, page_size: int = 64,
          actor: str | None = None, phase: str | None = None) -> dict[str, Any]:
    """Browse a redacted, versioned, hash-checked Jeeves/Dragon action trail."""
    if (type(page) is not int or page < 0 or type(page_size) is not int
        or not 1 <= page_size <= 256):
        raise WitnessError("observer trace requires nonnegative page and 1..256 size")
    if actor is not None and actor not in ACTORS:
        raise WitnessError("unknown observer actor filter")
    if phase is not None and phase not in PHASES:
        raise WitnessError("unknown observer phase filter")
    policy = _policy(root)
    events = _observations(root, policy, _source_events(root, policy))
    eligible = [e for e in events if (actor is None or e["actor"] == actor)
                and (phase is None or e["phase"] == phase)]
    start_at = page * page_size
    items = [{
        "sequence": e["sequence"], "at_utc": e["at_utc"],
        "actor": e["actor"], "phase": e["phase"], "action": e["action"],
        "outcome": e["outcome"], "trust": e["trust"],
        "evidence_sha256": e["evidence_sha256"], "event_sha256": e["digest"],
        "canonical_source_sequence": e["source_sequence"],
    } for e in eligible[start_at:start_at + page_size]]
    return {
        "ok": True, "action": "dragon-observe-trace",
        "page": page, "page_size": page_size,
        "filter": {"actor": actor, "phase": phase},
        "total": len(eligible), "items": items,
        "next_page": page + 1 if start_at + page_size < len(eligible) else None,
        "raw_prompts_or_media_included": False,
    }


def coverage(root: Path) -> dict[str, Any]:
    """Explain every quality gate and independent verifier still missing.

    This report is observation ABOUT the game pipeline, not new authority
    to pass an unimplemented validator or evidence to release a game.
    """
    policy = _policy(root)
    source = _source_events(root, policy)
    observations = _observations(root, policy, source)
    producer = production.status(root)
    observed = {e["source_sequence"] for e in observations
                if e["source_sequence"] is not None}
    by_gate = {name: [] for name in production.REQUIRED_GATES}
    for event in source:
        by_gate[event["gate"]].append(event)
    records = []
    for gate in production.REQUIRED_GATES:
        history = by_gate[gate]
        latest = history[-1] if history else None
        expected = production.EXPECTED_EVIDENCE_OWNERS[gate]
        qualified = bool(latest and latest["outcome"] == "passed"
                         and latest["evidence_kind"] == expected)
        independently_implemented = gate in production.AUTOMATED_GATES
        if qualified:
            next_action = "continue independent regression/replay scrutiny"
        elif independently_implemented:
            next_action = "run canonical verifier, inspect failure and restore prerequisites"
        else:
            next_action = "implement and connect independent discipline-specific evaluator"
        records.append({
            "gate": gate, "phase": _GATE_PHASE[gate],
            "expected_evidence_owner": expected,
            "canonical_checks": len(history),
            "dragon_observed_checks": sum(e["sequence"] in observed for e in history),
            "latest_outcome": latest["outcome"] if latest else "not_evaluated",
            "latest_owner": latest["evidence_kind"] if latest else None,
            "qualified": qualified,
            "automated_checker_registered": independently_implemented,
            "next_action": next_action,
        })
    unqualified = [r for r in records if not r["qualified"]]
    return {
        "ok": True, "action": "dragon-observe-coverage",
        "required_gates": len(records),
        "qualified_gates": len(records) - len(unqualified),
        "remaining_gates": len(unqualified),
        "unwitnessed_canonical_checks": len(source) - len(observed),
        "unimplemented_independent_evaluators": [
            r["gate"] for r in unqualified
            if not r["automated_checker_registered"]
        ],
        "records": records,
        "project_complete": producer["project_complete"],
        "automatic_pass_or_release": False, "training_performed": False,
    }
