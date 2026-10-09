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
    OfflineChatStore, _digest_request, load_private_bundle, save_private_bundle,
)
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError
from skeleton.app.offline_grounding import (
    grounded_request_digest, prepare_evidence,
)
from skeleton.app.offline_knowledge import (
    OfflineKnowledgeLibrary, MAX_DOCUMENT_BYTES,
)
from skeleton.app.local_ai import (
    DurableOfflineAISession,
    load_gguf_deployment,
    load_native_checkpoint,
    private_desktop_database,
    _model_tokenizer_digest,
)


def _read_reference_file(path: Path) -> str:
    """Admit only bounded operator-selected local UTF-8 text, never a URL."""
    if path.is_symlink() or not path.is_file():
        raise RuntimeContractError("reference path must be a local regular non-symlink file")
    if not 1 <= path.stat().st_size <= MAX_DOCUMENT_BYTES:
        raise RuntimeContractError("reference file exceeds the 64 KiB limit")
    with path.open("rb") as source:
        payload = source.read(MAX_DOCUMENT_BYTES + 1)
    if not 1 <= len(payload) <= MAX_DOCUMENT_BYTES:
        raise RuntimeContractError("reference changed or exceeded size budget")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise RuntimeContractError("reference must be UTF-8 text") from exc
    if "\x00" in text:
        raise RuntimeContractError("binary reference content is prohibited")
    return text


def _result(answer, session_id: str, *, as_json: bool,
            evidence: dict | None = None) -> None:
    if as_json:
        body = {
            "session_id": session_id,
            "model_digest": answer.model_digest,
            "text": answer.text,
            "execution_receipt_digest": answer.execution_receipt_digest,
            "input_tokens": answer.input_tokens,
            "output_tokens": answer.output_tokens,
        }
        if evidence is not None:
            body["evidence"] = evidence
        print(json.dumps(body, sort_keys=True, ensure_ascii=False))
    else:
        print("Local AI>", answer.text)
        if evidence is not None:
            print("Sources supplied to model (accuracy not verified):")
            for source in evidence["citations"]:
                print(" ", source["title"], source["citation"])


def _grounded_turn(chat: DurableOfflineAISession, message: str, *,
                   max_tokens: int):
    """Use the same source selection and atomic turn receipt as localhost."""
    if not isinstance(message, str) or not message.strip():
        raise RuntimeContractError("grounded message must not be empty")
    if len(message.strip().encode("utf-8")) > 1024:
        raise RuntimeContractError("grounded query exceeds 1024 bytes")
    index = OfflineKnowledgeLibrary(
        chat.store, chat.model_digest, chat.tokenizer_digest,
    )
    references = index.search(message, limit=2)
    if not references:
        raise RuntimeContractError("no local reference passages match this question")
    digest = grounded_request_digest(_digest_request(
        message.strip(), GenerationConfig(max_new_tokens=max_tokens),
    ))
    manifest = prepare_evidence(
        message.strip(), digest, references,
        chat.model_digest, chat.tokenizer_digest,
    )
    return asyncio.run(chat.ask(
        message, max_output_tokens=max_tokens, evidence_manifest=manifest,
    )), manifest


def _run_interactive(chat: DurableOfflineAISession, *, max_tokens: int,
                     as_json: bool) -> None:
    print("Offline model:", chat.model_digest)
    print("Session:", chat.session_id)
    print("Commands: /id  /new  /list  /resume SESSION_ID  /ground QUESTION  /exit")
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
        if message.startswith("/ground "):
            answer, evidence = _grounded_turn(
                chat, message[len("/ground "):].strip(), max_tokens=max_tokens,
            )
            _result(answer, chat.session_id, as_json=as_json, evidence=evidence)
        else:
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
    modes.add_argument("--grounded-message",
                       help="generate one offline turn with immutable supplied-source evidence")
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
    modes.add_argument("--add-reference", metavar="FILE", type=Path,
                       help="index a local text/code/Markdown reference into model-scoped SQLite")
    modes.add_argument("--list-references", action="store_true",
                       help="list local reference titles, identifiers and SHA-256 hashes")
    modes.add_argument("--search-reference", metavar="QUERY",
                       help="search verified local passages without calling the model")
    modes.add_argument("--delete-reference", metavar="DOCUMENT_ID",
                       help="remove one local model-bound reference and all its chunks")
    parser.add_argument("--output", type=Path,
                        help="new backup destination; required for --export-session")
    parser.add_argument("--fork-after-turn", type=int,
                        help="with --fork-session, copy history only through this turn")
    parser.add_argument("--search-limit", type=int, default=6,
                        help="with --search-reference, return 1–12 ranked source passages")
    parser.add_argument("--max-output-tokens", type=int,
                        help="per-turn model completion-token budget")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output for one-shot, list and management")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manage = bool(args.list or args.delete_session or args.export_session
                  or args.import_bundle or args.fork_session
                  or args.add_reference or args.list_references
                  or args.search_reference or args.delete_reference)
    if args.output is not None and args.export_session is None:
        parser.error("--output is valid only with --export-session")
    if args.export_session and args.output is None:
        parser.error("--export-session requires --output")
    if args.session and manage:
        parser.error("--session only applies to --message or --interactive")
    if args.fork_after_turn is not None and not args.fork_session:
        parser.error("--fork-after-turn requires --fork-session")
    if args.search_limit != 6 and not args.search_reference:
        parser.error("--search-limit requires --search-reference")
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
                if (args.add_reference or args.list_references
                        or args.search_reference or args.delete_reference):
                    knowledge = OfflineKnowledgeLibrary(
                        store, model_digest, token_digest
                    )
                    if args.add_reference:
                        content = _read_reference_file(args.add_reference)
                        print(json.dumps(knowledge.add_text(
                            args.add_reference.name, content
                        ), sort_keys=True))
                        return 0
                    if args.list_references:
                        print(json.dumps(knowledge.list_documents(), sort_keys=True))
                        return 0
                    if args.search_reference:
                        print(json.dumps(knowledge.search(
                            args.search_reference, limit=args.search_limit
                        ), sort_keys=True, ensure_ascii=False))
                        return 0
                    if args.delete_reference:
                        knowledge.delete(args.delete_reference)
                        print(json.dumps({
                            "deleted_document_id": args.delete_reference
                        }))
                        return 0
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
            if args.grounded_message is not None:
                answer, evidence = _grounded_turn(
                    chat, args.grounded_message, max_tokens=budget,
                )
                _result(answer, chat.session_id, as_json=args.json, evidence=evidence)
            else:
                answer = asyncio.run(
                    chat.ask(args.message, max_output_tokens=budget)
                )
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
