"""Standalone, Docker-free offline chat for native and GGUF model deployments.

This uses the same per-model SQLite state authority as the desktop GUI.
No hosted provider, cloud dependency, Tk display or external service.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from skeleton.ai.model_runtime.offline_chat import (
    OfflineChatStore, load_private_bundle, save_private_bundle,
)
from skeleton.app.local_ai import (
    DurableOfflineAISession,
    load_gguf_deployment,
    load_native_checkpoint,
    private_desktop_database,
    _model_tokenizer_digest,
)


def _result(answer, session_id: str, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "session_id": session_id,
            "model_digest": answer.model_digest,
            "text": answer.text,
            "execution_receipt_digest": answer.execution_receipt_digest,
            "input_tokens": answer.input_tokens,
            "output_tokens": answer.output_tokens,
        }, sort_keys=True, ensure_ascii=False))
    else:
        print("Local AI>", answer.text)


def _run_interactive(chat: DurableOfflineAISession, *, max_tokens: int,
                     as_json: bool) -> None:
    print("Offline model:", chat.model_digest)
    print("Session:", chat.session_id)
    print("Commands: /id  /new  /list  /resume SESSION_ID  /exit")
    while True:
        try:
            message = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if message == "/exit":
            return
        if message == "/id":
            print("Session:", chat.session_id)
            continue
        if message == "/new":
            print("New session:", chat.create_conversation())
            continue
        if message == "/list":
            for session_id, revision in chat.list_conversations():
                print(f"{session_id}  revision={revision}")
            continue
        if message.startswith("/resume "):
            chat.resume(message[len("/resume "):].strip())
            print("Restored:", chat.session_id, "turns=", len(chat.history) // 2)
            continue
        if not message:
            continue
        answer = asyncio.run(chat.ask(message, max_output_tokens=max_tokens))
        _result(answer, chat.session_id, as_json=as_json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run exact-model-bound local AI conversations without Docker/cloud/Tk."
    )
    models = parser.add_mutually_exclusive_group(required=True)
    models.add_argument("--native-checkpoint", type=Path,
                        help="existing Skeleton native-model checkpoint JSON")
    models.add_argument("--gguf-deployment", type=Path,
                        help="digest-pinned offline llama.cpp model deployment JSON")
    parser.add_argument("--database", type=Path,
                        help="SQLite path; defaults to the Windows GUI's per-model local store")
    parser.add_argument("--session", help="resume a saved conversation ID")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--message", help="complete and commit one local AI turn")
    modes.add_argument("--interactive", action="store_true",
                       help="multi-turn terminal conversation, including session switching")
    modes.add_argument("--list", action="store_true",
                       help="list conversations for the selected exact model")
    modes.add_argument("--delete-session", metavar="SESSION_ID",
                       help="delete a stored conversation and all retry receipts")
    modes.add_argument("--fork-session", metavar="SESSION_ID",
                       help="branch a saved conversation without modifying the parent")
    modes.add_argument("--export-session", metavar="SESSION_ID",
                       help="create a private portable backup of one conversation")
    modes.add_argument("--import-bundle", metavar="PATH", type=Path,
                       help="import a valid same-model portable conversation backup")
    parser.add_argument("--output", type=Path,
                        help="new backup destination; required for --export-session")
    parser.add_argument("--fork-after-turn", type=int,
                        help="with --fork-session, copy history only through this turn")
    parser.add_argument("--max-output-tokens", type=int,
                        help="per-turn model completion-token budget")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output for one-shot, list and management")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manage = bool(args.list or args.delete_session or args.export_session
                  or args.import_bundle or args.fork_session)
    if args.output is not None and args.export_session is None:
        parser.error("--output is valid only with --export-session")
    if args.export_session and args.output is None:
        parser.error("--export-session requires --output")
    if args.session and manage:
        parser.error("--session only applies to --message or --interactive")
    if args.fork_after_turn is not None and not args.fork_session:
        parser.error("--fork-after-turn requires --fork-session")
    if args.max_output_tokens is not None and (
        type(args.max_output_tokens) is not int or args.max_output_tokens < 1
    ):
        parser.error("--max-output-tokens must be positive")
    try:
        backend = (load_native_checkpoint(args.native_checkpoint)
                   if args.native_checkpoint is not None
                   else load_gguf_deployment(args.gguf_deployment))
        database = args.database or private_desktop_database(backend.model_digest)
        if manage:
            # Administrative inspection/deletion must not silently create a
            # new chat. Use the same per-model store without a session adapter.
            with OfflineChatStore(database) as store:
                model_digest = backend.model_digest
                token_digest = _model_tokenizer_digest(backend)
                if args.list:
                    records = [
                        {"session_id": sid, "revision": revision}
                        for sid, revision in store.list_sessions(
                            model_digest, token_digest
                        )
                    ]
                    if args.json:
                        print(json.dumps(records, sort_keys=True))
                    else:
                        for record in records:
                            print(record["session_id"], "revision=", record["revision"])
                    return 0
                if args.delete_session:
                    store.delete(args.delete_session, model_digest, token_digest)
                    print(json.dumps({"deleted_session_id": args.delete_session}))
                    return 0
                if args.fork_session:
                    branch_id = store.fork(
                        args.fork_session, model_digest, token_digest,
                        after_turn=args.fork_after_turn,
                    )
                    print(json.dumps({"source_session_id": args.fork_session,
                                      "forked_session_id": branch_id}))
                    return 0
                if args.export_session:
                    payload = store.export_bundle(
                        args.export_session, model_digest, token_digest
                    )
                    save_private_bundle(args.output, payload)
                    print(json.dumps({"exported_session_id": args.export_session,
                                      "path": str(args.output)}))
                    return 0
                if args.import_bundle:
                    new_session = store.import_bundle(
                        load_private_bundle(args.import_bundle),
                        model_digest, token_digest
                    )
                    print(json.dumps({"imported_session_id": new_session}))
                    return 0
        chat = DurableOfflineAISession(
            backend, database=database, session_id=args.session
        )
        try:
            budget = args.max_output_tokens or chat.preferred_output_tokens
            if args.interactive:
                _run_interactive(chat, max_tokens=budget, as_json=args.json)
                return 0
            answer = asyncio.run(chat.ask(args.message, max_output_tokens=budget))
            _result(answer, chat.session_id, as_json=args.json)
            if not args.json:
                print("Session:", chat.session_id)
            return 0
        finally:
            chat.close()
    except (Exception, KeyboardInterrupt) as exc:
        # Local operator diagnostics; the UI never substitutes a cloud model.
        print("Offline model request rejected:", str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
