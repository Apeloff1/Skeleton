#!/usr/bin/env python3
"""Verify Jeeves compatibility chat uses canonical conversation authority.

The legacy jeeves_chat collection is allowed only as one-way migration input.
New transcript writes, idempotency, replay and history must be owned by
ConversationThread/ConversationMessage authority.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
ROUTE = Path("backend/routes/jeeves_compose.py")
CONVERSATIONS = Path("backend/core/conversations.py")
CONTRACT = Path("skeleton/contracts/conversation.py")
WORKSPACE_TEST = Path("tests/test_jeeves_chat_workspace.py")
WORKSPACE_CONTROLLER = Path("frontend/features/Jeeves/WorkspaceController.ts")
WORKSPACE_MODEL = Path("frontend/features/Jeeves/workspace.ts")
CHAT_WORKSPACE = Path("frontend/features/Jeeves/ChatWorkspace.tsx")
WORKSPACE_CONTROLLER_TEST = Path("frontend/scripts/test-jeeves-workspace.cjs")
CONVERSATION_ROUTE = Path("backend/routes/conversations.py")
REGENERATION_ROUTE_TEST = Path("backend/tests/test_conversation_regeneration_route.py")

REQUIRED_ROUTE_TOKENS = (
    "_canonical_authority",
    "_ensure_canonical_thread",
    "_append_canonical_user_turn",
    "_commit_canonical_assistant_turn",
    "_canonical_existing_turn",
    "_load_canonical_history",
    "_import_legacy_rows_to_canonical",
    "ConversationThread/ConversationMessage is the only mutable",
)
REQUIRED_AUTHORITY_TOKENS = (
    "class MongoConversationAuthority",
    "append_user_message",
    "commit_assistant_message",
    "active_transcript",
    "idempotency_key",
)
FORBIDDEN_ROUTE_TOKENS = (
    "SKL_JEEVES_CANONICAL_CONVERSATIONS",
    "_chat_col().insert_one",
    "_chat_col().update_one",
    "_chat_col().delete_one",
    "_chat_col().replace_one",
    "_chat_col().find_one_and_update",
)
LEGACY_ALLOWED_FUNCTIONS = {"_legacy_complete_rows"}


class VerificationError(RuntimeError):
    """Jeeves conversation authority verification failed."""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _function_for_node(tree: ast.AST) -> dict[ast.AST, str]:
    owners: dict[ast.AST, str] = {}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.stack.append(node.name)
            owners[node] = node.name
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.stack.append(node.name)
            owners[node] = node.name
            self.generic_visit(node)
            self.stack.pop()

        def generic_visit(self, node: ast.AST) -> None:
            if self.stack:
                owners[node] = self.stack[-1]
            super().generic_visit(node)

    Visitor().visit(tree)
    return owners


def _verify_legacy_reads(route_source: str, errors: list[str]) -> int:
    try:
        tree = ast.parse(route_source, filename=str(ROUTE))
    except SyntaxError as exc:
        raise VerificationError(f"cannot parse {ROUTE}: {exc}") from exc

    owners = _function_for_node(tree)
    reads = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "_chat_col"):
            continue
        owner = owners.get(node, "")
        if owner not in LEGACY_ALLOWED_FUNCTIONS:
            errors.append(
                "legacy jeeves_chat access escaped migration reader: "
                + (owner or "<module>")
            )
        reads += 1

    if reads != 1:
        errors.append(
            "legacy jeeves_chat must have exactly one migration-read access "
            f"(found {reads})"
        )
    return reads


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    route_path = root / ROUTE
    authority_path = root / CONVERSATIONS
    contract_path = root / CONTRACT
    test_path = root / WORKSPACE_TEST

    controller_path = root / WORKSPACE_CONTROLLER
    workspace_model_path = root / WORKSPACE_MODEL
    chat_workspace_path = root / CHAT_WORKSPACE
    controller_test_path = root / WORKSPACE_CONTROLLER_TEST
    conversation_route_path = root / CONVERSATION_ROUTE
    regeneration_test_path = root / REGENERATION_ROUTE_TEST
    required = (
        route_path,
        authority_path,
        contract_path,
        test_path,
        controller_path,
        workspace_model_path,
        chat_workspace_path,
        controller_test_path,
        conversation_route_path,
        regeneration_test_path,
    )
    for path in required:
        if not path.is_file():
            errors.append(
                "required conversation cutover file is missing: "
                + str(path.relative_to(root))
            )

    if errors:
        return {
            "schema_version": 1,
            "verifier": "jeeves-conversation-cutover-v1",
            "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown",
            "legacy_read_accesses": 0,
            "digests": {},
            "errors": errors,
            "valid": False,
        }

    route = _read(route_path)
    authority = _read(authority_path)
    contract = _read(contract_path)
    tests = _read(test_path)
    controller = _read(controller_path)
    workspace_model = _read(workspace_model_path)
    chat_workspace = _read(chat_workspace_path)
    controller_tests = _read(controller_test_path)
    conversation_route = _read(conversation_route_path)
    regeneration_tests = _read(regeneration_test_path)

    for token in REQUIRED_ROUTE_TOKENS:
        if token not in route:
            errors.append(f"Jeeves route lost canonical authority token: {token}")
    for token in REQUIRED_AUTHORITY_TOKENS:
        if token not in authority:
            errors.append(f"conversation authority lost token: {token}")
    for token in FORBIDDEN_ROUTE_TOKENS:
        if token in route:
            errors.append(f"Jeeves route regained legacy authority token: {token}")

    for token in (
        "ConversationThread",
        "ConversationMessage",
        "ConversationAuthorType",
        "idempotency_key",
        "causal_user_message_id",
        "operation_id",
        "ai_result_id",
    ):
        if token not in contract:
            errors.append(f"conversation contract lost token: {token}")

    for token in (
        "test_jeeves_chat_legacy_collection_is_migration_read_only",
        "test_stable_client_message_id_replays_without_second_generation",
        "test_client_message_id_conflict_is_rejected",
        "test_canonical_jeeves_mode_migrates_legacy_then_owns_new_turns",
    ):
        if token not in tests:
            errors.append(f"Jeeves cutover regression is missing: {token}")

    for token in (
        "HistoryTransport",
        "projectCanonicalHistory",
        "rehydrateServerTranscripts",
        "refreshCanonical",
        "canonical conversation history unavailable",
        "response.canonical_message_id",
        "response.canonical_thread_id",
        "sessionUpdatedAt: Date.now()",
    ):
        if token not in controller:
            errors.append(
                f"WorkspaceController lost canonical reconstruction token: {token}"
            )
    for token in (
        "sessionIdentity",
        "sessionId,",
        "sessionUpdatedAt: sessionId ? sessionUpdatedAt : 0",
        "projectCanonicalHistory",
        "The browser cache never sends its transcript back as provider context",
    ):
        if token not in workspace_model:
            errors.append(
                f"workspace model lost durable session token: {token}"
            )
    if "sessionFresh" in workspace_model:
        errors.append("workspace model regained TTL-based canonical session expiry")
    build_start = workspace_model.find("export function buildChatBody(")
    projection_start = workspace_model.find(
        "function canonicalTurnText",
        build_start,
    )
    if build_start < 0 or projection_start < 0:
        errors.append("workspace model lost canonical buildChatBody boundary")
    elif "history:" in workspace_model[build_start:projection_start]:
        errors.append("Jeeves buildChatBody regained caller transcript authority")
    for token in (
        "ChatHistoryResponse",
        "/api/jeeves/chat/",
        "?limit=50",
        "controller.refreshCanonical()",
    ):
        if token not in chat_workspace:
            errors.append(
                f"ChatWorkspace lost canonical history transport token: {token}"
            )
    for token in (
        "remount replaces stale device transcript with canonical server history",
        "remount keeps device cache with notice when canonical history is unavailable",
        "durable backend session identity survives timestamp age and skew",
        "outgoing Jeeves requests never serialize the device-local transcript",
        "canonical projection preserves unresolved local user work only",
        "successful send caches canonical thread and assistant identities",
    ):
        if token not in controller_tests:
            errors.append(
                f"Jeeves remount regression is missing: {token}"
            )

    for token in (
        '@router.post("/{thread_id}/messages/{message_id}/regenerate")',
        "command_from_context",
        "_compile_chat_context",
        "_provider_history",
        "EngineClient.from_env",
        "conversation_authority.regenerate_assistant_message",
        '"engine-result:" + result.execution_id',
        '"regenerated_from": target.message_id',
        '"causal_user_message_id": causal.message_id',
    ):
        if token not in conversation_route:
            errors.append(
                f"conversation regenerate route lost canonical token: {token}"
            )
    for token in (
        "test_regenerate_route_runs_engine_then_commits_new_branch",
        "test_regenerate_route_never_commits_when_engine_unavailable",
        "test_regenerate_route_rejects_stale_version_before_engine_resolution",
    ):
        if token not in regeneration_tests:
            errors.append(
                f"conversation regenerate regression is missing: {token}"
            )

    legacy_reads = _verify_legacy_reads(route, errors)
    digests = {
        str(path.relative_to(root)): hashlib.sha256(
            _read(path).encode("utf-8")
        ).hexdigest()
        for path in required
    }
    return {
        "schema_version": 1,
        "verifier": "jeeves-conversation-cutover-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown",
        "legacy_read_accesses": legacy_reads,
        "digests": digests,
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        print(f"jeeves-conversation-cutover: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("jeeves-conversation-cutover: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "jeeves-conversation-cutover: OK "
        f"(legacy_reads={receipt['legacy_read_accesses']}, "
        f"files={len(receipt['digests'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
