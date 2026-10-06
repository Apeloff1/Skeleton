#!/usr/bin/env python3
"""Fail-closed structural validation for the canonical AI-chat turn runtime."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "machine" / "ai_chat_runtime_contract.json"
EXPECTED_SCHEMA = "ai-chat-runtime/v1"
EXPECTED_STATUS = "implemented_candidate"
FORBIDDEN_MARKERS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "api.openai.com",
    "from openai import",
    "import openai",
    "from anthropic import",
    "import anthropic",
)
REQUIRED_RUNTIME_MARKERS = (
    "_ALLOWED_TRANSITIONS",
    "previous_event_digest",
    "has_ambiguous_external_effect",
    "RECONCILE_TOOL",
    "child budget amplifies remaining authority",
    "BudgetGovernor.require_within",
)
REQUIRED_INVARIANTS = (
    "streamed client output is never authoritative completion state",
    "child budgets cannot exceed remaining parent authority",
    "ambiguous consequential tool effects require receipt reconciliation before retry or continuation",
    "turn persistence stores operation state only and never duplicates canonical transcript authority",
    "portable and production persistence decode the canonical runtime wire schema",
    "Mongo event persistence uses prepare, atomic snapshot advance, and committed-marker recovery",
    "public stream projection excludes arbitrary model, prompt, retrieval, and tool payload content",
    "stream reconnect is bound to operation identity, exact sequence, and prior event digest",
    "live product chat persists durable turn state around canonical conversation and engine milestones",
    "product replay heals existing durable turn completion without synthesizing historical turn journals",
    "public reconnect transport requires operation, sequence, and digest continuity",
    "same-operation retries preserve the original durable conversation binding while revalidating request digest and causal user identity",
    "transient engine or provider unavailability leaves the durable turn resumable instead of fabricating terminal completion",
    "cancellation request acknowledgement is non-terminal until the engine confirms a terminal cancelled state",
)


def _read_json(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _enum_members(tree: ast.AST, class_name: str) -> set[str]:
    for node in getattr(tree, "body", ()):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.targets[0].id
                for item in node.body
                if isinstance(item, ast.Assign)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
            }
    return set()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> list[str]:
    errors: list[str] = []
    if not CONTRACT.is_file():
        return ["missing machine/ai_chat_runtime_contract.json"]
    try:
        contract = _read_json(CONTRACT)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse AI chat runtime contract: {exc}"]

    if contract.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("AI chat runtime schema_version drifted")
    if contract.get("status") != EXPECTED_STATUS:
        errors.append("AI chat runtime must remain implemented_candidate before signoff")
    if contract.get("canonical_module") != "skeleton/ai/assistant/turn_runtime.py":
        errors.append("canonical AI chat runtime path drifted")

    files = contract.get("files")
    if not isinstance(files, dict):
        errors.append("AI chat runtime contract files must be an object")
        files = {}
    expected_roles = {
        "runtime",
        "focused_tests",
        "structural_validator",
        "exact_head_verifier",
        "independent_tests",
        "workflow",
        "plan",
        "portable_repository",
        "mongo_authority",
        "persistence_tests",
        "mongo_tests",
        "streaming",
        "streaming_tests",
        "live_lifecycle",
        "live_route",
        "live_route_tests",
    }
    if set(files) != expected_roles:
        errors.append("AI chat runtime contract file roles drifted")
    for role, raw in files.items():
        if not isinstance(raw, str) or not raw.strip():
            errors.append(f"AI chat runtime file path is invalid: {role}")
            continue
        if not (ROOT / raw).is_file():
            errors.append(f"AI chat runtime file missing: {role}: {raw}")

    invariants = contract.get("invariants")
    if not isinstance(invariants, list):
        errors.append("AI chat runtime invariants must be a list")
        invariants = []
    invariant_set = {str(item) for item in invariants}
    for required in REQUIRED_INVARIANTS:
        if required not in invariant_set:
            errors.append(f"AI chat runtime invariant missing: {required}")

    runtime_path = ROOT / "skeleton" / "ai" / "assistant" / "turn_runtime.py"
    if not runtime_path.is_file():
        errors.append("canonical AI chat runtime module is missing")
        return errors
    try:
        source = runtime_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        errors.append(f"cannot parse canonical AI chat runtime: {exc}")
        return errors

    forbidden = [marker for marker in FORBIDDEN_MARKERS if marker in source]
    if forbidden:
        errors.append(
            "AI chat runtime crossed provider boundary: " + ", ".join(forbidden)
        )
    missing = [marker for marker in REQUIRED_RUNTIME_MARKERS if marker not in source]
    if missing:
        errors.append(
            "AI chat runtime lost fail-closed markers: " + ", ".join(missing)
        )

    persistence_checks = {
        "portable_repository": (
            "BEGIN IMMEDIATE",
            "TurnJournal.verify",
            "snapshot_digest",
            "assert_assistant_message_binding",
        ),
        "mongo_authority": (
            "_commit_state",
            "prepared",
            "find_one_and_update",
            "_recover_prepared",
            "TurnJournal.verify",
        ),
    }
    for role, markers in persistence_checks.items():
        raw_path = files.get(role)
        if not isinstance(raw_path, str):
            errors.append(f"AI chat persistence role missing: {role}")
            continue
        path = ROOT / raw_path
        if not path.is_file():
            continue
        try:
            persistence_source = path.read_text(encoding="utf-8")
            ast.parse(persistence_source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"AI chat persistence module is invalid: {role}: {exc}")
            continue
        forbidden_hits = [
            marker for marker in FORBIDDEN_MARKERS
            if marker in persistence_source
        ]
        if forbidden_hits:
            errors.append(
                f"AI chat persistence crossed provider boundary: {role}: "
                + ", ".join(forbidden_hits)
            )
        missing_persistence = [
            marker for marker in markers
            if marker not in persistence_source
        ]
        if missing_persistence:
            errors.append(
                f"AI chat persistence lost fail-closed markers: {role}: "
                + ", ".join(missing_persistence)
            )

    streaming_path = files.get("streaming")
    if isinstance(streaming_path, str) and (ROOT / streaming_path).is_file():
        try:
            streaming_source = (ROOT / streaming_path).read_text(encoding="utf-8")
            ast.parse(streaming_source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"AI chat streaming module is invalid: {exc}")
        else:
            required_streaming = (
                "TurnStreamCursor",
                "last_event_digest",
                "stream journal contains a sequence gap",
                "stream journal digest chain is broken",
                "project_turn_event",
            )
            missing_streaming = [
                marker for marker in required_streaming
                if marker not in streaming_source
            ]
            if missing_streaming:
                errors.append(
                    "AI chat streaming lost reconnect/minimization markers: "
                    + ", ".join(missing_streaming)
                )

    live_checks = {
        "live_lifecycle": (
            "ChatTurnLifecycle",
            "finalize_existing_assistant",
            "existing durable turn does not match canonical retry identity",
            "conversation-assistant-already-committed",
        ),
        "live_route": (
            "chat_turn_lifecycle.begin",
            "TurnState.CONTEXT_COMPILING",
            "TurnState.MODEL_RUNNING",
            "TurnState.FINALIZING",
            "TurnState.COMPLETE",
            '"/chat/turns/{thread_id}/events"',
            "require_resume_cursor",
            "terminal_engine_state",
            "\"cancellation_requested\"",
        ),
    }
    for role, markers in live_checks.items():
        raw_path = files.get(role)
        if not isinstance(raw_path, str):
            errors.append(f"AI chat live route role missing: {role}")
            continue
        path = ROOT / raw_path
        if not path.is_file():
            continue
        try:
            live_source = path.read_text(encoding="utf-8")
            ast.parse(live_source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"AI chat live route module is invalid: {role}: {exc}")
            continue
        missing_live = [item for item in markers if item not in live_source]
        if missing_live:
            errors.append(
                f"AI chat live route lost durable cutover markers: {role}: "
                + ", ".join(missing_live)
            )

    live_route_path = files.get("live_route")
    if isinstance(live_route_path, str) and (ROOT / live_route_path).is_file():
        live_route_source = (ROOT / live_route_path).read_text(encoding="utf-8")
        if "retryable=True" in live_route_source:
            errors.append(
                "live AI chat route must not terminalize transient failures as FAILED_RETRYABLE"
            )

    required_states = contract.get("required_states")
    if not isinstance(required_states, list) or not required_states:
        errors.append("AI chat runtime required_states must be a non-empty list")
        required_states = []
    enum_states = _enum_members(tree, "TurnState")
    if set(str(item) for item in required_states) != enum_states:
        errors.append("TurnState enum does not exactly match contract required_states")

    terminal_states = contract.get("terminal_states")
    if not isinstance(terminal_states, list) or not terminal_states:
        errors.append("AI chat runtime terminal_states must be a non-empty list")
    elif not set(map(str, terminal_states)) <= enum_states:
        errors.append("AI chat runtime terminal_states contains unknown state")

    recovery = contract.get("recovery_rules")
    if not isinstance(recovery, dict) or len(recovery) < 10:
        errors.append("AI chat runtime recovery_rules are incomplete")
    else:
        if recovery.get("tool_executing_consequential_ambiguous") != "reconcile_tool":
            errors.append("ambiguous tool recovery must remain reconcile_tool")
        if recovery.get("terminal") != "noop_terminal":
            errors.append("terminal recovery must remain noop_terminal")

    budget_dimensions = contract.get("budget_dimensions")
    expected_budget = {
        "wall_seconds",
        "input_tokens",
        "output_tokens",
        "model_calls",
        "tool_calls",
        "agent_depth",
        "parallel_workers",
        "retrieval_queries",
        "external_writes",
        "cost_usd",
    }
    if not isinstance(budget_dimensions, list) or set(map(str, budget_dimensions)) != expected_budget:
        errors.append("AI chat runtime budget dimensions drifted")

    promotion = contract.get("promotion_rule")
    if not isinstance(promotion, str) or "no completion" not in promotion:
        errors.append("AI chat runtime promotion rule must not fabricate completion")

    return errors


def evidence(head_sha: str) -> dict[str, object]:
    errors = validate()
    contract = _read_json(CONTRACT)
    files = contract.get("files") or {}
    digests = {
        str(role): _sha256(ROOT / str(path))
        for role, path in sorted(files.items())
        if isinstance(path, str) and (ROOT / path).is_file()
    }
    payload: dict[str, object] = {
        "schema_version": EXPECTED_SCHEMA,
        "verifier": "ai-chat-runtime-structural-v1",
        "head_sha": str(head_sha).strip(),
        "valid": not errors,
        "errors": errors,
        "digests": digests,
        "contract_digest": _sha256(CONTRACT),
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args()

    if args.head_sha:
        result = evidence(args.head_sha)
        if args.evidence_out:
            Path(args.evidence_out).write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_evidence:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1

    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("AI chat runtime contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
