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
        if self._file.exists():
            data = json.loads(self._file.read_text(encoding="utf-8"))
            for doc_id, d in data.items():
                self._docs[doc_id] = Document(
                    doc_id=doc_id, title=d["title"], body=d["body"],
                    tags=d.get("tags", []), subsystems=d.get("subsystems", []),
                    version=d.get("version", 1), updated_ns=d.get("updated_ns", 0),
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
        doc = Document(
            doc_id=doc_id, title=title, body=body,
            tags=tags or [], subsystems=subsystems or [],
            version=(existing.version + 1) if existing else 1,
            updated_ns=time.time_ns(),
        )
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
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        scored = [(self._score(d, terms), d) for d in self._docs.values()]
        hits = [d for s, d in sorted(scored, key=lambda x: -x[0]) if s > 0]
        return [d.to_dict() for d in hits[:limit]]

    def for_subsystem(self, subsystem: str) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self._docs.values() if subsystem in d.subsystems]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "knowledge-base-card",
            "documents": len(self._docs),
            "tags": sorted({t for d in self._docs.values() for t in d.tags}),
            "subsystems_covered": sorted({s for d in self._docs.values() for s in d.subsystems}),
        }
