"""Quest state machine. Verb counts. No stored prose."""

from __future__ import annotations

from typing import Any, Mapping


MAX_QUESTS = 16
STATES = ("locked", "open", "done")


class QuestEngineError(ValueError):
    """Quest engine contract violation."""


def compile_book(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) > MAX_QUESTS:
        raise QuestEngineError("too many quests")
    book = []
    seen: set[str] = set()
    for raw in rows:
        qid = str(raw.get("id") or "")
        verb = str(raw.get("verb") or "").strip().lower()
        need = int(raw.get("count") or 1)
        if not qid or not verb or need < 1:
            raise QuestEngineError("quest row invalid")
        if qid in seen:
            raise QuestEngineError("duplicate quest")
        seen.add(qid)
        book.append({"id": qid, "verb": verb, "need": need, "have": 0, "state": "open"})
    return book


def observe(book: list[dict[str, Any]], verb: str) -> list[dict[str, Any]]:
    name = str(verb or "").strip().lower()
    nxt = []
    for quest in book:
        row = dict(quest)
        if row["state"] == "open" and row["verb"] == name:
            row["have"] = int(row["have"]) + 1
            if row["have"] >= row["need"]:
                row["state"] = "done"
        nxt.append(row)
    return nxt


def run(rows: list[Mapping[str, Any]], verbs: list[str]) -> dict[str, Any]:
    book = compile_book(rows)
    for verb in verbs:
        book = observe(book, verb)
    done = sum(1 for quest in book if quest["state"] == "done")
    return {
        "kind": "quest_engine",
        "n": len(book),
        "done": done,
        "open": sum(1 for quest in book if quest["state"] == "open"),
        "book": book,
        "complete": done == len(book) and len(book) > 0,
        "stored_prose": 0,
    }


def nexus_book() -> list[dict[str, Any]]:
    return [
        {"id": "q_heat", "verb": "heat", "count": 3},
        {"id": "q_extract", "verb": "extract", "count": 1},
        {"id": "q_craft", "verb": "craft", "count": 1},
        {"id": "q_bait", "verb": "bait", "count": 1},
    ]
