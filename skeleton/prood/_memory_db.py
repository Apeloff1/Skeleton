"""In-memory Mongo-shaped stub for Prood sibling ports (no real Mongo required)."""
from __future__ import annotations

import copy
import itertools
import threading
import time
from typing import Any, Iterator

ASCENDING = 1
DESCENDING = -1


class _Cursor:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def sort(self, key_or_list, direction: int | None = None):
        if isinstance(key_or_list, list):
            # [(field, dir), ...] — apply last key first for stability
            rows = list(self._rows)
            for field, direction in reversed(key_or_list):
                rows.sort(key=lambda r, f=field: r.get(f) if r.get(f) is not None else 0,
                          reverse=(direction == DESCENDING or direction == -1))
            self._rows = rows
        else:
            field = key_or_list
            d = DESCENDING if direction in (DESCENDING, -1) else ASCENDING
            self._rows = sorted(
                self._rows,
                key=lambda r: r.get(field) if r.get(field) is not None else 0,
                reverse=(d == DESCENDING),
            )
        return self

    def limit(self, n: int):
        self._rows = self._rows[: max(0, int(n))]
        return self

    def __iter__(self) -> Iterator[dict]:
        return iter(copy.deepcopy(self._rows))

    def __list__(self):  # pragma: no cover
        return list(self)


class MemoryCollection:
    def __init__(self, name: str):
        self.name = name
        self._docs: list[dict] = []
        self._id_seq = itertools.count(1)
        self._lock = threading.RLock()
        self._indexes: list = []

    def create_index(self, keys, **kwargs):
        self._indexes.append((keys, kwargs))
        return f"{self.name}_idx_{len(self._indexes)}"

    def _match(self, doc: dict, query: dict) -> bool:
        if not query:
            return True
        for k, v in query.items():
            if k == "$or":
                if not any(self._match(doc, clause) for clause in v):
                    return False
                continue
            if isinstance(v, dict):
                dv = doc.get(k)
                if "$in" in v and dv not in v["$in"]:
                    return False
                if "$gt" in v and not (dv is not None and dv > v["$gt"]):
                    return False
                if "$gte" in v and not (dv is not None and dv >= v["$gte"]):
                    return False
                if "$lt" in v and not (dv is not None and dv < v["$lt"]):
                    return False
                if "$lte" in v and not (dv is not None and dv <= v["$lte"]):
                    return False
                if "$ne" in v and dv == v["$ne"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    def _project(self, doc: dict, projection: dict | None) -> dict:
        if not projection:
            return copy.deepcopy(doc)
        out = {}
        include_id = projection.get("_id", 1) != 0
        if include_id and "_id" in doc:
            out["_id"] = doc["_id"]
        keys = [k for k, v in projection.items() if k != "_id" and v]
        if keys:
            for k in keys:
                if k in doc:
                    out[k] = copy.deepcopy(doc[k])
        else:
            # exclusion-only
            out = copy.deepcopy(doc)
            for k, v in projection.items():
                if v == 0:
                    out.pop(k, None)
        return out

    def insert_one(self, doc: dict):
        with self._lock:
            d = copy.deepcopy(doc)
            if "_id" not in d:
                d["_id"] = next(self._id_seq)
            self._docs.append(d)
            return type("R", (), {"inserted_id": d["_id"]})()

    def insert_many(self, docs: list[dict], ordered: bool = True):
        ids = []
        for doc in docs:
            ids.append(self.insert_one(doc).inserted_id)
        return type("R", (), {"inserted_ids": ids})()

    def find(self, query: dict | None = None, projection: dict | None = None, limit: int = 0):
        query = query or {}
        with self._lock:
            rows = [self._project(d, projection) for d in self._docs if self._match(d, query)]
        cur = _Cursor(rows)
        if limit:
            cur.limit(limit)
        return cur

    def find_one(self, query: dict | None = None, projection: dict | None = None):
        rows = list(self.find(query, projection).limit(1))
        return rows[0] if rows else None

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        with self._lock:
            for d in self._docs:
                if self._match(d, query):
                    if "$set" in update:
                        d.update(copy.deepcopy(update["$set"]))
                    else:
                        d.update({k: v for k, v in update.items() if not k.startswith("$")})
                    return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()
            if upsert:
                base = copy.deepcopy(query)
                if "$set" in update:
                    base.update(copy.deepcopy(update["$set"]))
                else:
                    base.update({k: v for k, v in update.items() if not k.startswith("$")})
                self.insert_one(base)
                return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": base.get("_id")})()
        return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()

    def replace_one(self, query: dict, replacement: dict, upsert: bool = False):
        with self._lock:
            for i, d in enumerate(self._docs):
                if self._match(d, query):
                    new = copy.deepcopy(replacement)
                    new.setdefault("_id", d.get("_id"))
                    self._docs[i] = new
                    return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()
            if upsert:
                self.insert_one(replacement)
        return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()

    def delete_many(self, query: dict):
        with self._lock:
            before = len(self._docs)
            self._docs = [d for d in self._docs if not self._match(d, query)]
            return type("R", (), {"deleted_count": before - len(self._docs)})()

    def delete_one(self, query: dict):
        with self._lock:
            for i, d in enumerate(self._docs):
                if self._match(d, query):
                    self._docs.pop(i)
                    return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    def estimated_document_count(self) -> int:
        return len(self._docs)

    def count_documents(self, query: dict | None = None) -> int:
        return len(list(self.find(query or {})))

    def drop(self):
        with self._lock:
            self._docs.clear()

    def aggregate(self, pipeline: list[dict]):
        rows = [copy.deepcopy(d) for d in self._docs]
        for stage in pipeline:
            if "$match" in stage:
                q = stage["$match"]
                rows = [r for r in rows if self._match(r, q)]
            elif "$group" in stage:
                g = stage["$group"]
                key = g.get("_id")
                groups: dict[Any, dict] = {}
                for r in rows:
                    if isinstance(key, str) and key.startswith("$"):
                        gk = r.get(key[1:])
                    else:
                        gk = key
                    bucket = groups.setdefault(gk, {"_id": gk})
                    for field, expr in g.items():
                        if field == "_id":
                            continue
                        if isinstance(expr, dict):
                            if "$sum" in expr:
                                v = expr["$sum"]
                                if v == 1:
                                    bucket[field] = bucket.get(field, 0) + 1
                                elif isinstance(v, str) and v.startswith("$"):
                                    bucket[field] = bucket.get(field, 0) + (r.get(v[1:]) or 0)
                            elif "$max" in expr:
                                v = expr["$max"]
                                if isinstance(v, str) and v.startswith("$"):
                                    cur = bucket.get(field)
                                    nv = r.get(v[1:])
                                    bucket[field] = nv if cur is None else max(cur, nv)
                            elif "$first" in expr:
                                v = expr["$first"]
                                if field not in bucket:
                                    if isinstance(v, str) and v.startswith("$"):
                                        bucket[field] = r.get(v[1:])
                                    else:
                                        bucket[field] = v
                rows = list(groups.values())
            elif "$sort" in stage:
                for field, direction in reversed(list(stage["$sort"].items())):
                    rows.sort(key=lambda r, f=field: r.get(f) if r.get(f) is not None else 0,
                              reverse=(direction == -1))
            elif "$limit" in stage:
                rows = rows[: int(stage["$limit"])]
        return rows

    def bulk_write(self, ops, ordered: bool = True):  # pragma: no cover
        return type("R", (), {"inserted_count": 0})()


class MemoryDatabase:
    def __init__(self, name: str = "test_database"):
        self.name = name
        self._cols: dict[str, MemoryCollection] = {}
        self._lock = threading.RLock()

    def __getitem__(self, name: str) -> MemoryCollection:
        with self._lock:
            if name not in self._cols:
                self._cols[name] = MemoryCollection(name)
            return self._cols[name]

    def list_collection_names(self) -> list[str]:
        return list(self._cols.keys())

    def drop_collection(self, name: str):
        with self._lock:
            col = self._cols.pop(name, None)
            if col:
                col.drop()

    def command(self, cmd: dict | str, *args, **kwargs):
        # compact / ping no-ops
        return {"ok": 1}


class MemoryClient:
    def __init__(self):
        self._dbs: dict[str, MemoryDatabase] = {}

    def __getitem__(self, name: str) -> MemoryDatabase:
        if name not in self._dbs:
            self._dbs[name] = MemoryDatabase(name)
        return self._dbs[name]


_CLIENT = MemoryClient()
_DEFAULT_DB = _CLIENT["test_database"]


def get_sync_db(db_name: str | None = None) -> MemoryDatabase:
    if db_name:
        return _CLIENT[db_name]
    return _DEFAULT_DB


def reset_memory_db() -> None:
    """Test helper — wipe all collections."""
    global _CLIENT, _DEFAULT_DB
    _CLIENT = MemoryClient()
    _DEFAULT_DB = _CLIENT["test_database"]


# Alias used by build_journey: `from core.databases import client as _MONGO`
client = _CLIENT


# Alias expected by runtime_health: from core.databases import core_db
core_db = _DEFAULT_DB
