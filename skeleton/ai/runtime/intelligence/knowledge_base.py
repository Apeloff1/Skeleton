"""Knowledge base — searchable operational knowledge store.

Stores runbooks, incident postmortems, and subsystem documentation as
searchable documents with tags and related-subsystem links. Supports
full-text search with ranking, doc versioning, and automatic links to
relevant docs from doctor card alerts.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


_DOC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


class KnowledgeError(ValueError):
    """A document cannot be stored or loaded safely."""


@dataclass
class Document:
    doc_id: str
    title: str
    body: str
    tags: List[str] = field(default_factory=list)
    subsystems: List[str] = field(default_factory=list)
    version: int = 1
    updated_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "tags": self.tags,
            "subsystems": self.subsystems,
            "version": self.version,
            "updated_ns": self.updated_ns,
        }


class KnowledgeBase:
    """Versioned searchable document store."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".skeleton")
        self._docs: Dict[str, Document] = {}
        self._file = self.root / "knowledge.json"
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        data = json.loads(self._file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise KnowledgeError("knowledge file must be an object")
        for doc_id, raw in data.items():
            if not isinstance(raw, dict):
                raise KnowledgeError("knowledge document must be an object")
            self._docs[doc_id] = self._document(
                doc_id,
                raw.get("title"),
                raw.get("body"),
                raw.get("tags", []),
                raw.get("subsystems", []),
                raw.get("version", 1),
                raw.get("updated_ns", 0),
            )

    def _document(
        self,
        doc_id: object,
        title: object,
        body: object,
        tags: object,
        subsystems: object,
        version: object,
        updated_ns: object,
    ) -> Document:
        if not isinstance(doc_id, str) or _DOC_ID.fullmatch(doc_id) is None:
            raise KnowledgeError("doc_id must be a safe token")
        if not isinstance(title, str) or not title.strip():
            raise KnowledgeError("title is required")
        if not isinstance(body, str) or not body.strip():
            raise KnowledgeError("body is required")
        if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise KnowledgeError("tags must be non-empty strings")
        if not isinstance(subsystems, list) or any(not isinstance(name, str) or not name.strip() for name in subsystems):
            raise KnowledgeError("subsystems must be non-empty strings")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise KnowledgeError("version must be a positive integer")
        if isinstance(updated_ns, bool) or not isinstance(updated_ns, int) or updated_ns < 0:
            raise KnowledgeError("updated_ns must be a non-negative integer")
        return Document(
            doc_id=doc_id,
            title=title.strip(),
            body=body,
            tags=list(tags),
            subsystems=list(subsystems),
            version=version,
            updated_ns=updated_ns,
        )

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(
            {d.doc_id: {**d.to_dict(), "body": d.body} for d in self._docs.values()}, indent=2
        ), encoding="utf-8")

    def put(self, doc_id: str, title: str, body: str,
            tags: Optional[List[str]] = None,
            subsystems: Optional[List[str]] = None) -> Document:
        existing = self._docs.get(doc_id)
        if tags is None:
            kept_tags = list(existing.tags) if existing else []
        else:
            kept_tags = list(tags)
        if subsystems is None:
            kept_subsystems = list(existing.subsystems) if existing else []
        else:
            kept_subsystems = list(subsystems)
        version = (existing.version + 1) if existing else 1
        doc = self._document(doc_id, title, body, kept_tags, kept_subsystems, version, time.time_ns())
        self._docs[doc_id] = doc
        self._save()
        return doc

    def get(self, doc_id: str) -> Optional[Document]:
        return self._docs.get(doc_id)

    def delete(self, doc_id: str) -> bool:
        if doc_id in self._docs:
            del self._docs[doc_id]
            self._save()
            return True
        return False

    def _score(self, doc: Document, terms: List[str]) -> float:
        hay = f"{doc.title} {doc.body} {' '.join(doc.tags)}".lower()
        score = 0.0
        for term in terms:
            score += hay.count(term) * (3.0 if term in doc.title.lower() else 1.0)
        return score

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        scored = [(self._score(d, terms), d) for d in self._docs.values()]
        hits = [d for s, d in sorted(scored, key=lambda x: (-x[0], x[1].doc_id)) if s > 0]
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        return [
            {**doc.to_dict(), "body": doc.body}
            for doc in hits[:limit]
        ]

    def for_subsystem(self, subsystem: str) -> List[Dict[str, Any]]:
        return [{**doc.to_dict(), "body": doc.body} for doc in self._docs.values() if subsystem in doc.subsystems]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "knowledge-base-card",
            "documents": len(self._docs),
            "tags": sorted({t for d in self._docs.values() for t in d.tags}),
            "subsystems_covered": sorted({s for d in self._docs.values() for s in d.subsystems}),
        }
