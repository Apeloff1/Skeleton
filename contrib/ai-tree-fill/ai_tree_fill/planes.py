"""Live planes the AI tree claimed and did not resolve."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ai_tree_fill.laws import (
    LawBreak,
    digest_card,
    forbid_coin,
    merkle_root,
    parse_pointers,
)
from ai_tree_fill.numerics import dot


@dataclass
class PointerMemory:
    """Episodic store of pointer clauses. Prose never lands."""

    leaves: list[str] = field(default_factory=list)

    def absorb(self, stimulus: str) -> dict:
        clauses = parse_pointers(stimulus)
        self.leaves.extend(clauses)
        root = merkle_root(self.leaves)
        return {"hit": 1, "law": "pointer-memory", "n": len(clauses), "root": root}

    def recall(self, needle: str) -> list[str]:
        return [leaf for leaf in self.leaves if needle in leaf][:8]


@dataclass
class Retriever:
    cards: list[tuple[str, list[str]]] = field(default_factory=list)

    def index(self, doc_id: str, stimulus: str) -> None:
        self.cards.append((doc_id, parse_pointers(stimulus)))

    def query(self, stimulus: str, k: int = 3) -> list[dict]:
        q = parse_pointers(stimulus)
        scored = []
        for doc_id, terms in self.cards:
            score = sum(1.0 for term in q if term in terms)
            if score:
                scored.append({"doc": doc_id, "score": score, "terms": terms})
        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:k]


@dataclass
class DurableOutbox:
    sent: dict[str, dict] = field(default_factory=dict)

    def enqueue(self, key: str, payload: Mapping[str, object]) -> dict:
        forbid_coin(payload)
        if key in self.sent:
            return {"hit": 1, "law": "outbox-idempotent", "key": key, "replay": True}
        card = {"key": key, "payload": dict(payload), "at": time.time()}
        self.sent[key] = card
        return {"hit": 1, "law": "outbox-accept", "key": key, "digest": digest_card(card), "replay": False}


@dataclass
class FailureDomain:
    """Local quorum on roots. No chain. No coin."""

    votes: dict[str, str] = field(default_factory=dict)

    def vote(self, peer: str, root: str) -> None:
        self.votes[peer] = root

    def quorum(self, need: int = 2) -> dict:
        if len(self.votes) < need:
            raise LawBreak("quorum", f"need {need} got {len(self.votes)}")
        counts: dict[str, int] = {}
        for root in self.votes.values():
            counts[root] = counts.get(root, 0) + 1
        winner, tally = max(counts.items(), key=lambda item: item[1])
        if tally < need:
            raise LawBreak("quorum", "no root reached need")
        return {"hit": 1, "law": "failure-domain", "root": winner, "tally": tally, "peers": len(self.votes)}


@dataclass
class Admission:
    owners: dict[str, str] = field(default_factory=dict)

    def claim(self, path: str, owner: str) -> None:
        if not owner:
            raise LawBreak("admission", "empty owner")
        self.owners[path] = owner

    def audit(self, tracked: Sequence[str]) -> dict:
        unowned = [path for path in tracked if path not in self.owners]
        if unowned:
            raise LawBreak("admission", "unowned " + ",".join(unowned))
        return {"hit": 1, "law": "admission", "owned": len(self.owners)}


def bm25_lite(query: Sequence[str], doc: Sequence[str]) -> float:
    if not query or not doc:
        return 0.0
    overlap = sum(1 for term in query if term in doc)
    return overlap / math_len(doc)


def math_len(doc: Sequence[str]) -> float:
    return float(max(1, len(doc)))


def skill_bind(name: str, contract: str) -> dict:
    if not name or not contract:
        raise LawBreak("skill", "unnamed skill")
    return {"hit": 1, "law": "skill-bind", "name": name, "contract": contract, "digest": digest_card({"n": name, "c": contract})}


def provider_card(name: str, live: bool) -> dict:
    return {
        "hit": 1 if live else 0,
        "law": "provider",
        "name": name,
        "device": "cpu",
        "torch": False,
        "authority": "none",
    }


def compensation(effect: str, undo: str) -> dict:
    if effect == undo:
        raise LawBreak("compensation", "undo aliases effect")
    return {"hit": 1, "law": "compensation", "effect": effect, "undo": undo}


def recovery(step: str, checkpoint: str) -> dict:
    if not checkpoint:
        raise LawBreak("recovery", "missing checkpoint")
    return {"hit": 1, "law": "recovery", "step": step, "checkpoint": checkpoint, "resumed": True}


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math_len_vec(a)
    nb = math_len_vec(b)
    if na == 0 or nb == 0:
        return 0.0
    return dot(a, b) / (na * nb)


def math_len_vec(vec: Sequence[float]) -> float:
    return sum(x * x for x in vec) ** 0.5
