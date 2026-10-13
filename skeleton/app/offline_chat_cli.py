"""Standalone, Docker-free offline chat for native and GGUF model deployments.

This uses the same per-model SQLite state authority as the desktop GUI.
No hosted provider, cloud dependency, Tk display or external service.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sqlite3
from pathlib import Path
import sys

from skeleton.ai.model_runtime.offline_chat import (
    OfflineChatStore, _digest_request, load_private_bundle, save_private_bundle,
)
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError
from skeleton.app.offline_grounding import (
    audit_answer_citations, grounded_request_digest, prepare_evidence,
)
from skeleton.app.offline_knowledge import (
    OfflineKnowledgeLibrary, read_reference_file as _read_reference_file,
)
from skeleton.app.local_ai import (
    DurableOfflineAISession,
    load_gguf_deployment,
    load_native_checkpoint,
    private_desktop_database,
    _model_tokenizer_digest,
)


def _result(answer, session_id: str, *, as_json: bool,
            evidence: dict | None = None, request_id: str | None = None) -> None:
    if as_json:
        body = {
            "session_id": session_id,
            "model_digest": answer.model_digest,
            "text": answer.text,
            "execution_receipt_digest": answer.execution_receipt_digest,
            "input_tokens": answer.input_tokens,
            "output_tokens": answer.output_tokens,
        }
        if request_id is not None:
            body["request_id"] = request_id
        if evidence is not None:
            body["evidence"] = evidence
            body["citation_audit"] = audit_answer_citations(answer.text, evidence)
        print(json.dumps(body, sort_keys=True, ensure_ascii=False))
    else:
        print("Local AI>", answer.text)
        if evidence is not None:
            print("Sources supplied to model (accuracy not verified):")
            for source in evidence["citations"]:
                print(" ", source["title"], source["citation"])
            print("Citation IDs:",
                  audit_answer_citations(answer.text, evidence)["status"],
                  "(not factual verification)")


def _grounded_turn(chat: DurableOfflineAISession, message: str, *,
                   max_tokens: int, request_id: str | None = None):
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
        request_id=request_id,
    )), manifest


def _emit(event: str, message: str, *, as_json: bool, **data) -> None:
    if as_json:
        print(json.dumps({"event": event, "message": message, **data},
                         sort_keys=True, ensure_ascii=False))
    else:
        print(message)


def _submit_turn(chat: DurableOfflineAISession, message: str, *,
                 max_tokens: int, grounded: bool, request_id: str,
                 as_json: bool) -> None:
    """Recover an exact committed request before doing any model work."""
    prompt = message.strip()
    if not prompt or len(prompt.encode("utf-8")) > 4096:
        raise RuntimeContractError("message must contain 1–4096 UTF-8 bytes")
    if grounded and len(prompt.encode("utf-8")) > 1024:
        raise RuntimeContractError("grounded query exceeds 1024 bytes")
    digest = _digest_request(prompt, GenerationConfig(max_new_tokens=max_tokens))
    if grounded:
        digest = grounded_request_digest(digest)
    # Read and validate the canonical model-bound history before replay lookup.
    chat.resume(chat.session_id)
    replay = chat.store.replay(chat.session_id, request_id, digest)
    if replay is not None:
        evidence = chat.store.turn_evidence(
            chat.session_id, chat.model_digest, chat.tokenizer_digest,
        )[replay.revision - 1]
        if as_json:
            payload = {
                "session_id": chat.session_id, "request_id": request_id,
                "model_digest": chat.model_digest, "revision": replay.revision,
                "text": replay.text, "output_digest": replay.output_digest,
                "input_tokens": replay.prompt_tokens,
                "output_tokens": replay.generated_tokens, "replayed": True,
            }
            if evidence is not None:
                payload["evidence"] = evidence
                payload["citation_audit"] = audit_answer_citations(replay.text, evidence)
            # Output digest is not mislabeled as an inference execution receipt.
            print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        else:
            print("Local AI>", replay.text)
            print("Recovered saved turn", replay.revision, "without new generation.")
        return
    if grounded:
        answer, evidence = _grounded_turn(
            chat, prompt, max_tokens=max_tokens, request_id=request_id,
        )
        _result(answer, chat.session_id, as_json=as_json, evidence=evidence, request_id=request_id)
    else:
        answer = asyncio.run(chat.ask(
            prompt, max_output_tokens=max_tokens, request_id=request_id,
        ))
        _result(answer, chat.session_id, as_json=as_json, request_id=request_id)


def _run_interactive(chat: DurableOfflineAISession, *, max_tokens: int,
                     as_json: bool) -> None:
    commands = (
        "/help; /id; /history; /list [search]; /new [instructions]; "
        "/resume SESSION_ID; /fork [turn]; /tokens N; /ground QUESTION; "
        "/retry; /references; /add FILE; /search QUERY; /save FILE; "
        "/import FILE; /exit"
    )
    _emit("ready", "Local model " + chat.model_digest + "\nSession: " + chat.session_id
          + "\nCommands: " + commands, as_json=as_json,
          session_id=chat.session_id, model_digest=chat.model_digest)
    pending: tuple[str, str, int, bool, str] | None = None
    while True:
        try:
            message = input("" if as_json else "You> ").strip()
        except (EOFError, KeyboardInterrupt):
            if not as_json:
                print()
            return
        if not message:
            continue
        command, _, argument = message.partition(" ")
        argument = argument.strip()
        try:
            if command == "/exit":
                return
            if command == "/help":
                _emit("help", commands, as_json=as_json)
                continue
            if command == "/id":
                _emit("session", "Session: " + chat.session_id, as_json=as_json,
                      session_id=chat.session_id, output_tokens=max_tokens)
                continue
            if command == "/history":
                chat.resume(chat.session_id)
                if as_json:
                    print(json.dumps({"session_id": chat.session_id,
                                      "messages": [{"role": role, "content": content}
                                                   for role, content in chat.history]},
                                     ensure_ascii=False))
                else:
                    for role, content in chat.history:
                        print(("You> " if role == "user" else "Local AI> ") + content)
                continue
            if command == "/new":
                if argument:
                    if len(argument.encode("utf-8")) > 4096:
                        raise RuntimeContractError("instructions exceed 4096 UTF-8 bytes")
                    sid = chat.store.create(chat.model_digest, chat.tokenizer_digest,
                                            system=argument)
                    chat.resume(sid)
                else:
                    chat.create_conversation()
                pending = None
                _emit("session", "New session: " + chat.session_id,
                      as_json=as_json, session_id=chat.session_id)
                continue
            if command == "/resume":
                if not argument:
                    raise RuntimeContractError("usage: /resume SESSION_ID")
                chat.resume(argument)
                pending = None
                _emit("session", "Restored " + chat.session_id, as_json=as_json,
                      session_id=chat.session_id, turns=len(chat.history) // 2)
                continue
            if command == "/list":
                cursor = None
                while True:
                    page = chat.store.session_summaries(
                        chat.model_digest, chat.tokenizer_digest,
                        query=argument, cursor=cursor, limit=100,
                    )
                    for item in page["sessions"]:
                        _emit("conversation", f"{item['session_id']}  {item['revision']} turns  {item['title']}",
                              as_json=as_json, **item)
                    cursor = page["next_cursor"]
                    if cursor is None:
                        break
                continue
            if command == "/fork":
                after = int(argument) if argument else None
                sid = chat.fork_conversation(chat.session_id, after_turn=after)
                chat.resume(sid)
                pending = None
                _emit("session", "Branched to " + sid, as_json=as_json, session_id=sid)
                continue
            if command == "/tokens":
                value = int(argument)
                limit = (chat.backend.runtime.limits.max_new_tokens
                         if hasattr(chat.backend, "runtime") else 8192)
                context = (chat.backend.runtime.limits.max_context
                           if hasattr(chat.backend, "runtime") else chat.backend.config.context_size or 4096)
                if not 1 <= value <= min(limit, context - 1):
                    raise RuntimeContractError("token budget exceeds the selected model limits")
                max_tokens = value
                _emit("budget", f"Output budget: {value} tokens", as_json=as_json,
                      max_output_tokens=value)
                continue
            if command in {"/references", "/add", "/search"}:
                knowledge = OfflineKnowledgeLibrary(chat.store, chat.model_digest, chat.tokenizer_digest)
                if command == "/references":
                    for item in knowledge.list_documents():
                        _emit("reference", item["document_id"] + "  " + item["title"],
                              as_json=as_json, **item)
                elif command == "/add":
                    if not argument:
                        raise RuntimeContractError("usage: /add FILE")
                    path = Path(argument).expanduser()
                    item = knowledge.add_text(path.name, _read_reference_file(path))
                    _emit("reference", "Indexed " + item["title"], as_json=as_json, **item)
                else:
                    if not argument:
                        raise RuntimeContractError("usage: /search QUERY")
                    hits = knowledge.search(argument, limit=6)
                    for hit in hits:
                        _emit("passage", hit["title"] + "\n" + hit["passage"] + "\n" + hit["citation"],
                              as_json=as_json, **hit)
                    if not hits:
                        _emit("search", "No matching local reference passages.", as_json=as_json)
                continue
            if command == "/save":
                if not argument:
                    raise RuntimeContractError("usage: /save NEW_FILE.json")
                save_private_bundle(Path(argument).expanduser(), chat.export_conversation(chat.session_id))
                _emit("export", "Private backup saved to " + argument, as_json=as_json)
                continue
            if command == "/import":
                if not argument:
                    raise RuntimeContractError("usage: /import FILE.json")
                sid = chat.import_conversation(load_private_bundle(Path(argument).expanduser()))
                chat.resume(sid)
                pending = None
                _emit("session", "Imported session " + sid, as_json=as_json, session_id=sid)
                continue
            if command == "/retry":
                if pending is None or pending[0] != chat.session_id:
                    raise RuntimeContractError("no interrupted request exists in this session")
            else:
                if command.startswith("/") and command != "/ground":
                    raise RuntimeContractError("unknown command; use /help")
                grounded = command == "/ground"
                prompt = argument if grounded else message
                if not prompt:
                    raise RuntimeContractError("usage: /ground QUESTION")
                pending = (chat.session_id, prompt, max_tokens, grounded, secrets.token_urlsafe(18))
            sid, prompt, budget, grounded, request_id = pending
            _emit("submitted", "Request: " + request_id, as_json=as_json,
                  session_id=sid, request_id=request_id)
            _submit_turn(chat, prompt, max_tokens=budget, grounded=grounded,
                         request_id=request_id, as_json=as_json)
            pending = None
        except KeyboardInterrupt:
            _emit("cancelled", "Interrupted. No success is assumed; /retry checks the original receipt first.",
                  as_json=as_json)
        except (RuntimeError, ValueError, OSError, sqlite3.Error) as exc:
            _emit("error", str(exc), as_json=as_json)


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
    parser.add_argument("--request-id", help="stable one-shot request ID; requires --session")
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
    if args.request_id is not None and (not args.session or args.interactive or manage):
        parser.error("--request-id requires --session with a one-shot message")
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
            request_id = args.request_id or secrets.token_urlsafe(18)
            _submit_turn(
                chat, args.grounded_message if args.grounded_message is not None else args.message,
                max_tokens=budget, grounded=args.grounded_message is not None,
                request_id=request_id, as_json=args.json,
            )
            if not args.json:
                print("Session:", chat.session_id)
                print("Request:", request_id)
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
