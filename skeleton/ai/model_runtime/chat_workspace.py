"""Native chat workspace: branching, history, search, retention and undo.

This module is deliberately model-independent. It manages validated chat
transcripts and optimistic revisions, while NativeChatEngine handles inference.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
import threading
import time
from typing import Any, Iterable, Mapping

from .chat_protocol import ChatMessage, ChatTranscript
from .runtime_contracts import RuntimeContractError


@dataclass(frozen=True)
class WorkspaceRecord:
    conversation_id: str
    revision: int
    created_at: float
    updated_at: float
    title: str
    pinned: bool
    archived: bool
    tags: tuple[str, ...]
    message_count: int
    digest: str


@dataclass(frozen=True)
class WorkspaceEvent:
    conversation_id: str
    revision: int
    action: str
    timestamp: float
    digest: str


class NativeChatWorkspace:
    """Thread-safe revisioned chat state with bounded undo history."""

    def __init__(self, *, max_conversations: int = 4096,
                 max_history: int = 32, max_events: int = 8192) -> None:
        for value in (max_conversations, max_history, max_events):
            if type(value) is not int or value < 1 or value > 100000:
                raise RuntimeContractError("invalid workspace capacity")
        self.max_conversations = max_conversations
        self.max_history = max_history
        self.max_events = max_events
        self._lock = threading.RLock()
        self._data: dict[str, dict[str, Any]] = {}
        self._events: list[WorkspaceEvent] = []

    def _get(self, conversation_id: str) -> dict[str, Any]:
        try:
            return self._data[conversation_id]
        except (KeyError, TypeError) as exc:
            raise RuntimeContractError("unknown workspace conversation") from exc

    def _check(self, item: dict[str, Any], expected_revision: int | None) -> None:
        if expected_revision is not None:
            if type(expected_revision) is not int or item["revision"] != expected_revision:
                raise RuntimeContractError("workspace revision conflict")

    def _record(self, cid: str, action: str) -> None:
        item = self._data[cid]
        item["revision"] += 1
        item["updated_at"] = time.time()
        self._events.append(WorkspaceEvent(cid, item["revision"], action,
                                           item["updated_at"], item["transcript"].digest()))
        if len(self._events) > self.max_events:
            del self._events[:len(self._events) - self.max_events]

    def _change(self, cid: str, transcript: ChatTranscript, action: str,
                expected_revision: int | None = None) -> int:
        if not isinstance(transcript, ChatTranscript):
            raise RuntimeContractError("chat transcript required")
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            history = item["undo"]
            history.append(item["transcript"])
            if len(history) > self.max_history:
                del history[0]
            item["transcript"] = transcript
            item["redo"].clear()
            self._record(cid, action)
            return item["revision"]

    def create(self, *, title: str = "New conversation",
               transcript: ChatTranscript | None = None) -> str:
        if type(title) is not str or not 1 <= len(title) <= 256:
            raise RuntimeContractError("invalid conversation title")
        initial = transcript if transcript is not None else ChatTranscript(())
        if not isinstance(initial, ChatTranscript):
            raise RuntimeContractError("invalid initial transcript")
        with self._lock:
            if len(self._data) >= self.max_conversations:
                raise RuntimeContractError("workspace capacity exhausted")
            cid = secrets.token_urlsafe(24)
            now = time.time()
            self._data[cid] = dict(transcript=initial, title=title, tags=(),
                                   pinned=False, archived=False, revision=0,
                                   created_at=now, updated_at=now, undo=[], redo=[])
            self._record(cid, "create")
            return cid

    def exists(self, cid: str) -> bool:
        with self._lock:
            return isinstance(cid, str) and cid in self._data

    def count(self) -> int:
        with self._lock:
            return len(self._data)

    def get(self, cid: str) -> ChatTranscript:
        with self._lock:
            return self._get(cid)["transcript"]

    def revision(self, cid: str) -> int:
        with self._lock:
            return self._get(cid)["revision"]

    def describe(self, cid: str) -> WorkspaceRecord:
        with self._lock:
            item = self._get(cid)
            transcript = item["transcript"]
            return WorkspaceRecord(cid, item["revision"], item["created_at"],
                                   item["updated_at"], item["title"], item["pinned"],
                                   item["archived"], item["tags"],
                                   len(transcript.messages), transcript.digest())

    def list_records(self, *, include_archived: bool = False) -> tuple[WorkspaceRecord, ...]:
        with self._lock:
            ids = sorted(self._data, key=lambda cid: (-self._data[cid]["updated_at"], cid))
            return tuple(self.describe(cid) for cid in ids
                         if include_archived or not self._data[cid]["archived"])

    def replace(self, cid: str, transcript: ChatTranscript, *,
                expected_revision: int | None = None) -> int:
        return self._change(cid, transcript, "replace", expected_revision)

    def append(self, cid: str, role: str, content: str, *,
               name: str | None = None, expected_revision: int | None = None) -> int:
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            updated = item["transcript"].append(role, content, name)
            return self._change(cid, updated, "append", expected_revision)

    def append_many(self, cid: str, messages: Iterable[ChatMessage], *,
                    expected_revision: int | None = None) -> int:
        additions = tuple(messages)
        if any(not isinstance(m, ChatMessage) for m in additions):
            raise RuntimeContractError("invalid chat messages")
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            transcript = ChatTranscript(item["transcript"].messages + additions)
            return self._change(cid, transcript, "append_many", expected_revision)

    def delete_last(self, cid: str, *, expected_revision: int | None = None) -> int:
        with self._lock:
            transcript = self.get(cid)
            if not transcript.messages:
                raise RuntimeContractError("conversation is empty")
            return self._change(cid, ChatTranscript(transcript.messages[:-1]),
                                "delete_last", expected_revision)

    def delete_range(self, cid: str, start: int, stop: int, *,
                     expected_revision: int | None = None) -> int:
        if type(start) is not int or type(stop) is not int or start < 0 or stop < start:
            raise RuntimeContractError("invalid message range")
        with self._lock:
            transcript = self.get(cid)
            if stop > len(transcript.messages):
                raise RuntimeContractError("message range exceeds transcript")
            updated = ChatTranscript(transcript.messages[:start] + transcript.messages[stop:])
            return self._change(cid, updated, "delete_range", expected_revision)

    def edit_message(self, cid: str, index: int, content: str, *,
                     expected_revision: int | None = None) -> int:
        with self._lock:
            transcript = self.get(cid)
            if type(index) is not int or not 0 <= index < len(transcript.messages):
                raise RuntimeContractError("invalid message index")
            old = transcript.messages[index]
            messages = list(transcript.messages)
            messages[index] = ChatMessage(old.role, content, old.name)
            return self._change(cid, ChatTranscript(tuple(messages)), "edit", expected_revision)

    def truncate(self, cid: str, count: int, *,
                 expected_revision: int | None = None) -> int:
        if type(count) is not int or count < 0:
            raise RuntimeContractError("invalid truncation")
        with self._lock:
            transcript = self.get(cid)
            return self._change(cid, transcript.tail(count), "truncate", expected_revision)

    def clear(self, cid: str, *, expected_revision: int | None = None) -> int:
        return self._change(cid, ChatTranscript(()), "clear", expected_revision)

    def fork(self, cid: str, *, through: int | None = None) -> str:
        with self._lock:
            item = self._get(cid)
            messages = item["transcript"].messages
            if through is None:
                through = len(messages)
            if type(through) is not int or not 0 <= through <= len(messages):
                raise RuntimeContractError("invalid fork point")
            child = self.create(title=item["title"] + " (branch)",
                                transcript=ChatTranscript(messages[:through]))
            self._data[child]["tags"] = item["tags"]
            return child

    def clone(self, cid: str) -> str:
        return self.fork(cid)

    def merge(self, target: str, source: str, *,
              expected_revision: int | None = None) -> int:
        with self._lock:
            left = self.get(target)
            right = self.get(source)
            return self._change(target, left.merge(right), "merge", expected_revision)

    def undo(self, cid: str, *, expected_revision: int | None = None) -> int:
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            if not item["undo"]:
                raise RuntimeContractError("no undo history")
            item["redo"].append(item["transcript"])
            if len(item["redo"]) > self.max_history:
                del item["redo"][0]
            item["transcript"] = item["undo"].pop()
            self._record(cid, "undo")
            return item["revision"]

    def redo(self, cid: str, *, expected_revision: int | None = None) -> int:
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            if not item["redo"]:
                raise RuntimeContractError("no redo history")
            item["undo"].append(item["transcript"])
            if len(item["undo"]) > self.max_history:
                del item["undo"][0]
            item["transcript"] = item["redo"].pop()
            self._record(cid, "redo")
            return item["revision"]

    def rename(self, cid: str, title: str) -> None:
        if not isinstance(title, str) or not 1 <= len(title) <= 256:
            raise RuntimeContractError("invalid conversation title")
        with self._lock:
            self._get(cid)["title"] = title
            self._record(cid, "rename")

    def set_tags(self, cid: str, tags: Iterable[str]) -> None:
        values = tuple(tags)
        if len(values) > 32:
            raise RuntimeContractError("invalid conversation tags")
        if any(type(tag) is not str for tag in values):
            raise RuntimeContractError("invalid conversation tags")
        if len(set(values)) != len(values):
            raise RuntimeContractError("invalid conversation tags")
        if any(type(tag) is not str or not 1 <= len(tag) <= 64 for tag in values):
            raise RuntimeContractError("invalid conversation tags")
        with self._lock:
            self._get(cid)["tags"] = values
            self._record(cid, "tags")

    def add_tag(self, cid: str, tag: str) -> None:
        with self._lock:
            tags = self._get(cid)["tags"]
            if tag not in tags:
                self.set_tags(cid, tags + (tag,))

    def remove_tag(self, cid: str, tag: str) -> None:
        with self._lock:
            self.set_tags(cid, tuple(t for t in self._get(cid)["tags"] if t != tag))

    def pin(self, cid: str) -> None:
        with self._lock:
            self._get(cid)["pinned"] = True
            self._record(cid, "pin")

    def unpin(self, cid: str) -> None:
        with self._lock:
            self._get(cid)["pinned"] = False
            self._record(cid, "unpin")

    def archive(self, cid: str) -> None:
        with self._lock:
            self._get(cid)["archived"] = True
            self._record(cid, "archive")

    def unarchive(self, cid: str) -> None:
        with self._lock:
            self._get(cid)["archived"] = False
            self._record(cid, "unarchive")

    def delete(self, cid: str, *, expected_revision: int | None = None) -> None:
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            del self._data[cid]

    def delete_many(self, ids: Iterable[str]) -> int:
        values = tuple(ids)
        if any(type(cid) is not str for cid in values):
            raise RuntimeContractError("invalid conversation IDs")
        if len(set(values)) != len(values):
            raise RuntimeContractError("duplicate conversation IDs")
        with self._lock:
            for cid in values:
                self._get(cid)
            for cid in values:
                del self._data[cid]
            return len(values)

    def search(self, query: str, *, roles: Iterable[str] | None = None,
               limit: int = 100) -> tuple[tuple[str, int, ChatMessage], ...]:
        if not isinstance(query, str) or not query or type(limit) is not int or not 1 <= limit <= 10000:
            raise RuntimeContractError("invalid search request")
        if isinstance(roles, (str, bytes)):
            raise RuntimeContractError("invalid role filter")
        selected = set(roles) if roles is not None else None
        if selected is not None and not selected.issubset(("system", "developer", "user", "assistant", "tool")):
            raise RuntimeContractError("invalid role filter")
        needle = query.casefold()
        with self._lock:
            found = []
            for cid in sorted(self._data):
                for index, message in enumerate(self._data[cid]["transcript"].messages):
                    if (selected is None or message.role in selected) and needle in message.content.casefold():
                        found.append((cid, index, message))
                        if len(found) >= limit:
                            return tuple(found)
            return tuple(found)

    def search_titles(self, query: str) -> tuple[str, ...]:
        if not isinstance(query, str):
            raise RuntimeContractError("invalid title query")
        with self._lock:
            return tuple(cid for cid in sorted(self._data)
                         if query.casefold() in self._data[cid]["title"].casefold())

    def filter_tag(self, tag: str) -> tuple[str, ...]:
        if not isinstance(tag, str):
            raise RuntimeContractError("invalid tag")
        with self._lock:
            return tuple(cid for cid in sorted(self._data) if tag in self._data[cid]["tags"])

    def filter_archived(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(cid for cid in sorted(self._data) if self._data[cid]["archived"])

    def filter_pinned(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(cid for cid in sorted(self._data) if self._data[cid]["pinned"])

    def latest(self, limit: int = 20) -> tuple[str, ...]:
        if type(limit) is not int or limit < 1:
            raise RuntimeContractError("invalid result limit")
        return tuple(record.conversation_id for record in self.list_records()[:limit])

    def events(self, *, conversation_id: str | None = None,
               limit: int = 100) -> tuple[WorkspaceEvent, ...]:
        if type(limit) is not int or not 1 <= limit <= self.max_events:
            raise RuntimeContractError("invalid event limit")
        with self._lock:
            events = (event for event in self._events
                      if conversation_id is None or event.conversation_id == conversation_id)
            return tuple(list(events)[-limit:])

    def export(self, cid: str) -> dict[str, Any]:
        with self._lock:
            item = self._get(cid)
            return {"schema": "native.chat.workspace.v1",
                    "title": item["title"], "tags": list(item["tags"]),
                    "pinned": item["pinned"], "archived": item["archived"],
                    "transcript": item["transcript"].to_list()}

    def import_conversation(self, data: Mapping[str, Any]) -> str:
        if not isinstance(data, Mapping) or data.get("schema") != "native.chat.workspace.v1":
            raise RuntimeContractError("invalid workspace import schema")
        if set(data) - {"schema", "title", "tags", "pinned", "archived", "transcript"}:
            raise RuntimeContractError("unexpected workspace import fields")
        if type(data.get("pinned", False)) is not bool or type(data.get("archived", False)) is not bool:
            raise RuntimeContractError("invalid imported conversation flags")
        if not isinstance(data.get("title"), str) or not isinstance(data.get("transcript"), list):
            raise RuntimeContractError("invalid imported conversation fields")
        transcript = ChatTranscript.parse(data["transcript"])
        cid = self.create(title=data["title"], transcript=transcript)
        try:
            self.set_tags(cid, data.get("tags", ()))
            if data.get("pinned", False):
                self.pin(cid)
            if data.get("archived", False):
                self.archive(cid)
        except BaseException:
            self.delete(cid)
            raise
        return cid

    def export_json(self, cid: str) -> str:
        return json.dumps(self.export(cid), sort_keys=True, separators=(",", ":"))

    def import_json(self, payload: str) -> str:
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > 3000000:
            raise RuntimeContractError("invalid workspace JSON")
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise RuntimeContractError("invalid workspace JSON") from exc
        return self.import_conversation(obj)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"conversations": len(self._data),
                    "messages": sum(len(item["transcript"].messages) for item in self._data.values()),
                    "pinned": sum(item["pinned"] for item in self._data.values()),
                    "archived": sum(item["archived"] for item in self._data.values()),
                    "events": len(self._events)}

    def prune_archived(self, *, older_than: float) -> int:
        if isinstance(older_than, bool) or not isinstance(older_than, (int, float)):
            raise RuntimeContractError("invalid cutoff")
        with self._lock:
            ids = [cid for cid, item in self._data.items()
                   if item["archived"] and not item["pinned"] and item["updated_at"] < older_than]
            return self.delete_many(ids)

    def compare_and_rename(self, cid: str, expected_revision: int, title: str) -> int:
        if not isinstance(title, str) or not 1 <= len(title) <= 256:
            raise RuntimeContractError("invalid conversation title")
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            self.rename(cid, title)
            return item["revision"]

    def compare_and_archive(self, cid: str, expected_revision: int) -> int:
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            self.archive(cid)
            return item["revision"]

    def compare_and_pin(self, cid: str, expected_revision: int) -> int:
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            self.pin(cid)
            return item["revision"]

    def compare_and_tags(self, cid: str, expected_revision: int,
                         tags: Iterable[str]) -> int:
        with self._lock:
            item = self._get(cid)
            self._check(item, expected_revision)
            self.set_tags(cid, tags)
            return item["revision"]

    def message_at(self, cid: str, index: int) -> ChatMessage:
        with self._lock:
            messages = self.get(cid).messages
            if type(index) is not int or not 0 <= index < len(messages):
                raise RuntimeContractError("invalid message index")
            return messages[index]

    def message_count(self, cid: str) -> int:
        return len(self.get(cid).messages)

    def role_counts(self, cid: str) -> dict[str, int]:
        return self.get(cid).count_by_role()

    def transcript_bytes(self, cid: str) -> int:
        return self.get(cid).byte_size()

    def transcript_digest(self, cid: str) -> str:
        return self.get(cid).digest()

    def list_by_tag(self, tag: str) -> tuple[WorkspaceRecord, ...]:
        return tuple(self.describe(cid) for cid in self.filter_tag(tag))

    def list_pinned(self) -> tuple[WorkspaceRecord, ...]:
        return tuple(self.describe(cid) for cid in self.filter_pinned())

    def list_archived(self) -> tuple[WorkspaceRecord, ...]:
        return tuple(self.describe(cid) for cid in self.filter_archived())

    def has_undo(self, cid: str) -> bool:
        with self._lock:
            return bool(self._get(cid)["undo"])

    def has_redo(self, cid: str) -> bool:
        with self._lock:
            return bool(self._get(cid)["redo"])

    def clear_history(self, cid: str) -> None:
        with self._lock:
            item = self._get(cid)
            item["undo"].clear()
            item["redo"].clear()
            self._record(cid, "clear_history")

    def history_depth(self, cid: str) -> tuple[int, int]:
        with self._lock:
            item = self._get(cid)
            return len(item["undo"]), len(item["redo"])

    def recent_events(self, cid: str, limit: int = 100) -> tuple[WorkspaceEvent, ...]:
        return self.events(conversation_id=cid, limit=limit)

    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    def event_actions(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for event in self._events:
                counts[event.action] = counts.get(event.action, 0) + 1
            return counts

    def workspace_capacity_remaining(self) -> int:
        with self._lock:
            return self.max_conversations - len(self._data)

    def append_user(self, cid: str, content: str, *,
                    expected_revision: int | None = None) -> int:
        return self.append(cid, "user", content, expected_revision=expected_revision)

    def append_assistant(self, cid: str, content: str, *,
                         expected_revision: int | None = None) -> int:
        return self.append(cid, "assistant", content, expected_revision=expected_revision)

    def append_tool(self, cid: str, content: str, *, name: str,
                    expected_revision: int | None = None) -> int:
        return self.append(cid, "tool", content, name=name, expected_revision=expected_revision)

    def last_user(self, cid: str) -> ChatMessage | None:
        return self.get(cid).last_user_message()

    def last_assistant(self, cid: str) -> ChatMessage | None:
        return self.get(cid).last_assistant_message()

    def last_turn(self, cid: str) -> ChatTranscript:
        return self.get(cid).last_turn()

    def instruction_prefix(self, cid: str) -> ChatTranscript:
        return self.get(cid).instruction_prefix()

    def dialogue(self, cid: str) -> ChatTranscript:
        return self.get(cid).dialogue_only()

    def conversation_turns(self, cid: str) -> tuple[ChatTranscript, ...]:
        return self.get(cid).dialogue_turns()

    def trim_messages(self, cid: str, keep_last: int, *,
                      expected_revision: int | None = None) -> int:
        return self.truncate(cid, keep_last, expected_revision=expected_revision)

    def trim_bytes(self, cid: str, budget: int, *,
                   expected_revision: int | None = None) -> int:
        with self._lock:
            transcript = self.get(cid).trim_to_bytes(budget)
            return self._change(cid, transcript, "trim_bytes", expected_revision)

    def remove_role(self, cid: str, role: str, *,
                    expected_revision: int | None = None) -> int:
        if role not in ("system", "developer", "user", "assistant", "tool"):
            raise RuntimeContractError("invalid role")
        with self._lock:
            transcript = self.get(cid)
            updated = ChatTranscript(tuple(m for m in transcript.messages if m.role != role))
            return self._change(cid, updated, "remove_role", expected_revision)

    def replace_last(self, cid: str, role: str, content: str, *,
                     expected_revision: int | None = None) -> int:
        with self._lock:
            transcript = self.get(cid).replace_last(role, content)
            return self._change(cid, transcript, "replace_last", expected_revision)

    def insert_message(self, cid: str, index: int, message: ChatMessage, *,
                       expected_revision: int | None = None) -> int:
        if not isinstance(message, ChatMessage):
            raise RuntimeContractError("invalid chat message")
        with self._lock:
            messages = list(self.get(cid).messages)
            if type(index) is not int or not 0 <= index <= len(messages):
                raise RuntimeContractError("invalid insert index")
            messages.insert(index, message)
            return self._change(cid, ChatTranscript(tuple(messages)), "insert", expected_revision)

    def move_message(self, cid: str, source: int, target: int, *,
                     expected_revision: int | None = None) -> int:
        with self._lock:
            messages = list(self.get(cid).messages)
            if any(type(i) is not int or not 0 <= i < len(messages) for i in (source, target)):
                raise RuntimeContractError("invalid move index")
            message = messages.pop(source)
            messages.insert(target, message)
            return self._change(cid, ChatTranscript(tuple(messages)), "move", expected_revision)

    def swap_messages(self, cid: str, first: int, second: int, *,
                      expected_revision: int | None = None) -> int:
        with self._lock:
            messages = list(self.get(cid).messages)
            if any(type(i) is not int or not 0 <= i < len(messages) for i in (first, second)):
                raise RuntimeContractError("invalid swap index")
            messages[first], messages[second] = messages[second], messages[first]
            return self._change(cid, ChatTranscript(tuple(messages)), "swap", expected_revision)

    def copy_message(self, source_id: str, index: int, target_id: str, *,
                     expected_revision: int | None = None) -> int:
        with self._lock:
            message = self.message_at(source_id, index)
            return self.append(target_id, message.role, message.content,
                               name=message.name, expected_revision=expected_revision)

    def move_to_archive(self, cid: str) -> None:
        self.archive(cid)

    def restore_from_archive(self, cid: str) -> None:
        self.unarchive(cid)

    def export_all(self, *, include_archived: bool = True) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(self.export(record.conversation_id)
                         for record in self.list_records(include_archived=include_archived))

    def clear_events(self) -> None:
        with self._lock:
            self._events.clear()


__all__ = ["NativeChatWorkspace", "WorkspaceRecord", "WorkspaceEvent"]
