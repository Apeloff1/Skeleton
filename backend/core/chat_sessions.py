"""Bounded chat adapters over canonical conversation, memory and engine owners.

No transcript, model, memory or tool authority is created here. Prepared commands
are private operational metadata on their original governed conversation row.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping
import uuid
from urllib.parse import urlsplit

from core.conversations import ConversationConflict, conversation_authority
from core.engine_client import EngineExecutionCommand, EngineProtocolError
from core.loop_local_asyncio import LoopLocalAsyncPrimitive
from skeleton.context.sources import conversation_message_segment

PREPARED_SCHEMA = "backend.ai.chat-execution.v1"
MAX_PREPARED_BYTES = 2 * 1024 * 1024


_indexes_ready = False
_index_lock = LoopLocalAsyncPrimitive(asyncio.Lock)


async def initialize_chat_runtime():
    """Bounded startup/first-use initialization of existing canonical owners."""
    global _indexes_ready
    if _indexes_ready:
        return
    async with _index_lock.get():
        if not _indexes_ready:
            from core.chat_turns import chat_turn_authority

            await asyncio.wait_for(conversation_authority.ensure_indexes(), timeout=5)
            await asyncio.wait_for(chat_turn_authority.ensure_indexes(), timeout=5)
            _indexes_ready = True


def canonical_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise EngineProtocolError("prepared chat payload is not bounded finite JSON") from exc
    if len(encoded) > MAX_PREPARED_BYTES:
        raise EngineProtocolError("prepared chat payload exceeds its byte bound")
    return encoded


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def prepare_metadata(
    command: EngineExecutionCommand, *, request_digest: str, dependencies: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    payload = {
        "schema_version": PREPARED_SCHEMA,
        "request_digest": request_digest,
        "command": command.as_dict(),
        "dependencies": dict(dependencies or {}),
    }
    payload["command_digest"] = digest(payload["command"])
    payload["record_digest"] = digest(payload)
    return payload


def checked_command(
    metadata,
    *,
    thread,
    user_message,
    tenant_id: str,
    owner_id: str,
    expected_request_digest: str | None = None,
) -> EngineExecutionCommand:
    if not isinstance(metadata, dict) or set(metadata) != {
        "schema_version",
        "request_digest",
        "command",
        "dependencies",
        "command_digest",
        "record_digest",
    }:
        raise EngineProtocolError("prepared chat command schema is invalid")
    unsigned = {key: value for key, value in metadata.items() if key != "record_digest"}
    if (
        metadata["schema_version"] != PREPARED_SCHEMA
        or digest(unsigned) != metadata["record_digest"]
        or digest(metadata["command"]) != metadata["command_digest"]
    ):
        raise EngineProtocolError("prepared chat command digest differs")
    command = EngineExecutionCommand.from_dict(metadata["command"])
    user_segment = conversation_message_segment(thread, user_message, purpose="model-inference")
    if (
        command.operation.tenant_id != tenant_id
        or command.operation.actor_id != owner_id
        or thread.tenant_id != tenant_id
        or thread.owner_id != owner_id
        or command.operation.capability != "assistant.chat"
        or command.operation.idempotency_key != user_message.idempotency_key
        or command.compiled_context.turn_id != user_message.message_id
        or user_message.thread_id != thread.thread_id
        or (user_segment.segment_id, user_segment.content_digest)
        not in command.compiled_context.source_snapshot
        or "conversation:" + thread.thread_id not in command.context_seed_refs
        or "conversation-message:" + user_message.message_id not in command.context_seed_refs
        or "chat-request-sha256:" + metadata["request_digest"] not in user_message.attachment_refs
        or (expected_request_digest is not None and metadata["request_digest"] != expected_request_digest)
    ):
        raise EngineProtocolError("prepared chat command does not match its canonical message")
    expected_operation = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "skeleton-ai-chat:" + thread.thread_id + ":" + user_message.message_id)
    )
    expected_execution = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "skeleton-ai-chat-execution:" + expected_operation)
    )
    if (
        command.operation.operation_id != expected_operation
        or command.execution_request.execution_id != expected_execution
    ):
        raise EngineProtocolError("prepared chat command lineage differs")
    return command


async def read_prepared(
    *, thread, user_message, tenant_id: str, owner_id: str, expected_request_digest: str | None = None
):
    refs = await conversation_authority.user_request_refs(
        thread.thread_id, user_message.message_id, tenant_id=tenant_id, owner_id=owner_id
    )
    if refs != user_message.attachment_refs:
        from dataclasses import replace

        user_message = replace(user_message, attachment_refs=refs)
    metadata = await conversation_authority.chat_execution(
        thread.thread_id, user_message.message_id, tenant_id=tenant_id, owner_id=owner_id
    )
    if metadata is None:
        if "chat-prepared-execution:v1" in user_message.attachment_refs:
            raise EngineProtocolError("prepared chat command is missing from its canonical row")
        return None, None
    return metadata, checked_command(
        metadata,
        thread=thread,
        user_message=user_message,
        tenant_id=tenant_id,
        owner_id=owner_id,
        expected_request_digest=expected_request_digest,
    )


@dataclass(frozen=True, slots=True)
class PreparedContextProjection:
    """Public identity projection of the exact stored canonical context handoff."""

    context_id: str
    context_digest: str
    source_snapshot: tuple[tuple[str, str], ...]
    compiler_version: str
    operation_id: str
    execution_id: str
    turn_id: str

    @classmethod
    def from_command(cls, command):
        binding = command.compiled_context
        return cls(
            binding.context_id,
            binding.context_digest,
            binding.source_snapshot,
            binding.compiler_version,
            binding.operation_id,
            binding.execution_id,
            binding.turn_id,
        )

    def binding_dict(self):
        return {
            "context_id": self.context_id,
            "context_digest": self.context_digest,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "source_snapshot": [list(pair) for pair in self.source_snapshot],
            "compiler_version": self.compiler_version,
        }


def command_expired(command, *, now=None) -> bool:
    instant = now or datetime.now(timezone.utc)
    return command.operation.deadline <= instant or command.delegated_authority.expires_at <= instant


def require_writable_tip(thread, transcript, user_message):
    if not thread.writable or not transcript or transcript[-1].message_id != user_message.message_id:
        raise ConversationConflict("only the current writable canonical user turn can resume")


async def context_sources(*, memory_references, crawler_context, user, tenant_id, owner_id, created_at):
    """Materialize only explicitly selected current owner evidence as data."""
    from fastapi import HTTPException
    from core.canonical_memory import canonical_memory_repository
    from skeleton.context.sources import memory_record_segment
    from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust

    segments, dependencies = [], {"memory": [], "crawler": []}
    total_bytes = 0
    seen = set()
    for reference in memory_references:
        key = (reference.namespace, reference.memory_id)
        if key in seen:
            raise HTTPException(
                status_code=422,
                detail={"code": "chat_memory_reference_duplicate", "message": "Select each memory once."},
            )
        seen.add(key)
        try:
            record = await canonical_memory_repository.get(
                reference.memory_id, tenant_id=tenant_id, namespace=reference.namespace
            )
            if (
                record.subject_id != owner_id
                or not record.active
                or (record.expires_at is not None and record.expires_at <= datetime.now(timezone.utc))
            ):
                raise ValueError("memory authority differs")
            content = record.content
            if not isinstance(content, str) or not content:
                raise ValueError("memory is not materialized")
            total_bytes += len(content.encode("utf-8"))
            if total_bytes > 65536:
                raise ValueError("selected memory exceeds context byte bound")
            segments.append(memory_record_segment(record, tenant_id=tenant_id, purpose="model-inference"))
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "chat_memory_unavailable",
                    "message": "A selected memory is unavailable, changed or outside your scope.",
                },
            ) from exc
        dependencies["memory"].append(
            {
                "memory_id": record.memory_id,
                "namespace": record.namespace,
                "version": record.version,
                "payload_digest": record.payload_digest,
            }
        )
    if crawler_context is not None:
        try:
            from core.dragon_crawler import read_crawler_context

            projection = await read_crawler_context(
                user,
                query=crawler_context.query,
                max_docs=crawler_context.max_documents,
                max_chars=crawler_context.max_characters,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "chat_crawler_context_unavailable",
                    "message": "Current authorized crawler context is unavailable.",
                },
            ) from exc
        documents = projection.get("documents")
        references = projection.get("references")
        if (
            not isinstance(documents, list)
            or not isinstance(references, list)
            or len(documents) > 4
            or len(references) > 4
        ):
            raise EngineProtocolError("crawler context projection is invalid")
        if not documents:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "chat_crawler_no_sources",
                    "message": "No current captured sources match this query. Capture an authorized source or choose a different query.",
                },
            )
        for document in documents:
            text = document.get("text")
            source_id = document.get("source_id")
            if (
                not isinstance(text, str)
                or not text
                or not isinstance(source_id, str)
                or len(source_id) > 1024
            ):
                raise EngineProtocolError("crawler evidence projection is invalid")
            content_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if document.get("content_digest") != content_digest:
                raise EngineProtocolError("crawler evidence digest differs")
            source_ref = document.get("source_ref")
            if not isinstance(source_ref, str) or not source_ref or len(source_ref) > 1024:
                raise EngineProtocolError("crawler evidence reference is invalid")
            source_url, title = document.get("source_url"), document.get("title")
            if (
                not isinstance(source_url, str)
                or not source_url
                or len(source_url) > 2000
                or any(ord(character) < 32 for character in source_url)
                or not isinstance(title, str)
                or len(title) > 4096
            ):
                raise EngineProtocolError("crawler citation metadata is invalid")
            parsed_url = urlsplit(source_url)
            if (
                parsed_url.scheme not in {"http", "https"}
                or not parsed_url.hostname
                or parsed_url.username is not None
                or parsed_url.password is not None
            ):
                raise EngineProtocolError("crawler citation URL is invalid")
            evidence = canonical_bytes(
                {
                    "source_url": source_url,
                    "title": title,
                    "authority": "external_evidence_only",
                    "review_state": "unreviewed",
                    "passage_sha256": content_digest,
                    "passage": text,
                }
            ).decode("utf-8")
            total_bytes += len(evidence.encode("utf-8"))
            if total_bytes > 131072:
                raise EngineProtocolError("selected evidence exceeds context byte bound")
            segments.append(
                ContextSegment.from_content(
                    segment_id=str(
                        uuid.uuid5(uuid.NAMESPACE_URL, "chat-crawler:" + source_id + ":" + content_digest)
                    ),
                    kind=ContextKind.RETRIEVAL_EVIDENCE,
                    source_type="dragon-crawler",
                    source_id=source_id,
                    content=evidence,
                    trust_level=ContextTrust.UNTRUSTED_EVIDENCE,
                    data_class="confidential",
                    tenant_id=tenant_id,
                    purpose="model-inference",
                    priority=400,
                    relevance=0.8,
                    created_at=created_at,
                    provenance=(
                        source_ref,
                        "crawler-url:" + source_url,
                        "crawler-passage-sha256:" + content_digest,
                    ),
                    retention_class="conversation-source-evidence",
                )
            )
        dependencies["crawler"] = references
    return tuple(segments), dependencies


async def assert_current_dependencies(metadata, *, user, tenant_id, owner_id):
    from fastapi import HTTPException
    from core.canonical_memory import canonical_memory_repository

    dependencies = metadata["dependencies"]
    if not isinstance(dependencies, dict) or set(dependencies) - {
        "memory",
        "crawler",
        "attachments",
        "dragon",
    }:
        raise EngineProtocolError("prepared evidence dependencies are invalid")
    memory = dependencies.get("memory", [])
    crawler = dependencies.get("crawler", [])
    if not isinstance(memory, list) or len(memory) > 8 or not isinstance(crawler, list) or len(crawler) > 4:
        raise EngineProtocolError("prepared evidence dependency bounds differ")
    for pin in memory:
        try:
            record = await canonical_memory_repository.get(
                pin["memory_id"], tenant_id=tenant_id, namespace=pin["namespace"]
            )
            if (
                record.subject_id != owner_id
                or not record.active
                or record.version != pin["version"]
                or record.payload_digest != pin["payload_digest"]
                or (record.expires_at is not None and record.expires_at <= datetime.now(timezone.utc))
            ):
                raise ValueError("memory identity changed")
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "chat_memory_withdrawn",
                    "message": "A selected memory changed or was withdrawn; this request cannot reuse it.",
                },
            ) from exc
    attachments = dependencies.get("attachments", [])
    dragon = dependencies.get("dragon", [])
    if (
        not isinstance(attachments, list)
        or len(attachments) > 4
        or not isinstance(dragon, list)
        or len(dragon) > 3
    ):
        raise EngineProtocolError("prepared attachment/Dragon dependency bounds differ")
    for pin in attachments:
        try:
            from core.chat_attachments import resolve_attachment_context

            if not isinstance(pin, dict) or set(pin) != {"thread_id", "attachment_ref", "source_snapshot"}:
                raise ValueError("attachment binding schema differs")
            resolution = await resolve_attachment_context(
                thread_id=pin["thread_id"],
                tenant_id=tenant_id,
                owner_id=owner_id,
                attachment_refs=(pin["attachment_ref"],),
                created_at=datetime.now(timezone.utc),
            )
            if [[segment.segment_id, segment.content_digest] for segment in resolution.segments] != pin[
                "source_snapshot"
            ]:
                raise ValueError("attachment evidence changed")
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "chat_attachment_withdrawn",
                    "message": "A selected attachment changed or was withdrawn; this request cannot reuse it.",
                },
            ) from exc
    for pin in dragon:
        try:
            if (
                not isinstance(pin, dict)
                or set(pin) != {"thread_id", "query", "source_id", "content_digest"}
                or not isinstance(pin["query"], str)
                or len(pin["query"]) > 512
            ):
                raise ValueError("Dragon binding schema differs")
            thread = await conversation_authority.get_thread(
                pin["thread_id"], tenant_id=tenant_id, owner_id=owner_id
            )
            current = await conversation_authority.dragon_context_segments(thread, pin["query"])
            if (pin["source_id"], pin["content_digest"]) not in {
                (segment.source_id, segment.content_digest) for segment in current
            }:
                raise ValueError("Dragon consented projection changed")
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "chat_dragon_projection_withdrawn",
                    "message": "A consented Dragon checkpoint changed or was withdrawn; this request cannot reuse it.",
                },
            ) from exc
    if crawler:
        try:
            from core.dragon_crawler import assert_crawler_context

            await assert_crawler_context(user, references=crawler)
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "chat_crawler_source_withdrawn",
                    "message": "Crawler evidence changed or was withdrawn; this request cannot reuse it.",
                },
            ) from exc


async def inherit_history_dependencies(
    dependencies,
    *,
    thread,
    transcript,
    selected_segments,
    tenant_id,
    owner_id,
    current_message=None,
):
    """Preserve causal source obligations through newly selected chat history."""
    selected_ids = {
        segment.source_id for segment in selected_segments if segment.source_type == "conversation"
    }
    if current_message is not None:
        fresh = (
            current_message.sequence == thread.message_sequence + 1
            and current_message.branch_id == thread.active_branch_id
            and current_message.parent_message_id == (transcript[-1].message_id if transcript else None)
        )
        edited_tip = (
            current_message.sequence == thread.message_sequence
            and current_message.supersedes_message_id is not None
            and bool(transcript)
            and transcript[-1].message_id == current_message.message_id
            and transcript[-1].content == current_message.content
            and transcript[-1].parent_message_id == current_message.parent_message_id
        )
        if (
            current_message.thread_id != thread.thread_id
            or current_message.branch_id != thread.active_branch_id
            or current_message.author_type.value != "user"
            or not (fresh or edited_tip)
        ):
            raise ConversationConflict("current chat preview differs from the canonical thread tip")
        expected = conversation_message_segment(thread, current_message, purpose="model-inference")
        actual = [
            segment
            for segment in selected_segments
            if segment.source_type == "conversation" and segment.source_id == current_message.message_id
        ]
        if len(actual) != 1 or (actual[0].segment_id, actual[0].content_digest) != (
            expected.segment_id,
            expected.content_digest,
        ):
            raise ConversationConflict("the exact current USER preview must fit the selected model context")
        # This input is prepared atomically after history validation. Its own
        # source obligations are supplied above; it is not a persisted ancestor.
        selected_ids.discard(current_message.message_id)
    causal_ids = set()
    message_by_id = {message.message_id: message for message in transcript}
    message_by_pair = {}
    known_history = {(segment.segment_id, segment.content_digest) for segment in selected_segments}
    assistant_snapshots = {}
    for item in transcript:
        if item.content:
            segment = conversation_message_segment(thread, item, purpose="model-inference")
            pair = (segment.segment_id, segment.content_digest)
            known_history.add(pair)
            message_by_pair[pair] = item.message_id
        if item.author_type.value == "assistant" and item.causal_user_message_id:
            assistant_snapshots.setdefault(item.causal_user_message_id, set()).update(
                item.context_source_snapshot
            )
    pending = set(selected_ids)
    visited = set()
    while pending:
        message_id = pending.pop()
        if message_id in visited:
            continue
        visited.add(message_id)
        if len(visited) > 256:
            raise ConversationConflict(
                "selected regenerated context exceeds its source graph bound; start a fresh conversation"
            )
        message = message_by_id.get(message_id)
        if message is None:
            raise ConversationConflict("selected context lost its canonical message lineage")
        if message.author_type.value == "user":
            causal_ids.add(message.message_id)
        elif message.author_type.value == "assistant" and message.causal_user_message_id:
            causal_ids.add(message.causal_user_message_id)
            causal_message = message_by_id.get(message.causal_user_message_id)
            legacy_causal = (
                causal_message is None or "chat-prepared-execution:v1" not in causal_message.attachment_refs
            )
            if message.supersedes_message_id is not None or legacy_causal:
                pending.update(
                    message_by_pair[pair]
                    for pair in message.context_source_snapshot
                    if pair in message_by_pair and message_by_pair[pair] not in visited
                )
        if len(causal_ids) > 256 or len(pending) + len(visited) > 256:
            raise ConversationConflict(
                "selected context exceeds its causal source bound; start a fresh conversation"
            )
    inherited = await conversation_authority.chat_history_dependencies(
        thread.thread_id, causal_ids, tenant_id=tenant_id, owner_id=owner_id
    )
    checked_dependencies = []
    for message, metadata, legacy_command in inherited:
        if metadata is None:
            if "chat-prepared-execution:v1" in message.attachment_refs:
                raise EngineProtocolError("selected history lost its prepared execution")
            # A legacy issued context may still carry expiring attachment or
            # consented Dragon inputs. Recover only identities provable from
            # the original command or canonical assistant snapshot.
            known = set(known_history)
            for ref in message.attachment_refs:
                if ref.startswith("ephemeral-context-sha256:"):
                    known.add(
                        (
                            str(
                                uuid.uuid5(
                                    uuid.NAMESPACE_URL,
                                    "artifact-context:" + tenant_id + ":chat-context:" + message.message_id,
                                )
                            ),
                            ref.removeprefix("ephemeral-context-sha256:"),
                        )
                    )
            snapshots = set()
            if legacy_command is not None:
                command = EngineExecutionCommand.from_dict(legacy_command)
                snapshots.update(command.compiled_context.source_snapshot)
            snapshots.update(assistant_snapshots.get(message.message_id, ()))
            group = {"attachments": [], "dragon": []}
            refs = [ref for ref in message.attachment_refs if ref.startswith("chat-attachment://")]
            for ref in refs:
                from core.chat_attachments import resolve_attachment_context

                try:
                    admitted = await resolve_attachment_context(
                        thread_id=thread.thread_id,
                        tenant_id=tenant_id,
                        owner_id=owner_id,
                        attachment_refs=(ref,),
                        created_at=message.created_at,
                    )
                    pairs = {(segment.segment_id, segment.content_digest) for segment in admitted.segments}
                    if not pairs or not pairs.issubset(snapshots):
                        raise ValueError("legacy attachment original identity cannot be recovered")
                except Exception as exc:
                    raise ConversationConflict(
                        "legacy attachment evidence changed or cannot be verified; start a new conversation with current sources"
                    ) from exc
                known.update(pairs)
                group["attachments"].append(
                    {
                        "thread_id": thread.thread_id,
                        "attachment_ref": ref,
                        "source_snapshot": [
                            [segment.segment_id, segment.content_digest] for segment in admitted.segments
                        ],
                    }
                )
            unknown = snapshots - known
            if unknown:
                current_dragon = await conversation_authority.dragon_context_segments(
                    thread, message.content or ""
                )
                for segment in current_dragon:
                    pair = (segment.segment_id, segment.content_digest)
                    if pair in unknown:
                        unknown.remove(pair)
                        group["dragon"].append(
                            {
                                "thread_id": thread.thread_id,
                                "query": (message.content or "")[:512],
                                "source_id": segment.source_id,
                                "content_digest": segment.content_digest,
                            }
                        )
            if unknown:
                raise ConversationConflict(
                    "legacy source context cannot be verified; start a new conversation with current sources"
                )
            checked_dependencies.append(group)
            continue
        checked_command(metadata, thread=thread, user_message=message, tenant_id=tenant_id, owner_id=owner_id)
        checked_dependencies.append(metadata["dependencies"])
    result = {"memory": [], "crawler": [], "attachments": [], "dragon": []}
    identities = {"memory": {}, "crawler": {}, "attachments": {}, "dragon": {}}
    for group in [*checked_dependencies, dependencies]:
        if not isinstance(group, dict) or set(group) - {"memory", "crawler", "attachments", "dragon"}:
            raise EngineProtocolError("history source dependencies are invalid")
        for kind, maximum in (("memory", 8), ("crawler", 4), ("attachments", 4), ("dragon", 3)):
            pins = group.get(kind, [])
            if not isinstance(pins, list) or len(pins) > maximum:
                raise ConversationConflict("selected history exceeds source dependency bounds")
            for pin in pins:
                if not isinstance(pin, dict):
                    raise EngineProtocolError("history source dependency is malformed")
                if kind == "memory":
                    identity = (pin.get("namespace"), pin.get("memory_id"))
                elif kind == "crawler":
                    identity = (pin.get("session_id"), pin.get("source_id"))
                elif kind == "attachments":
                    identity = (pin.get("thread_id"), pin.get("attachment_ref"))
                else:
                    identity = (pin.get("thread_id"), pin.get("source_id"))
                encoded = digest(pin)
                if identity in identities[kind]:
                    if identities[kind][identity] != encoded:
                        raise ConversationConflict(
                            "selected history refers to different revisions of one source"
                        )
                    continue
                identities[kind][identity] = encoded
                result[kind].append(pin)
                if len(result[kind]) > maximum:
                    raise ConversationConflict(
                        "selected history exceeds source dependency bounds; start a fresh conversation"
                    )
    return result
