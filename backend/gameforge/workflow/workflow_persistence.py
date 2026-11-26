#!/usr/bin/env python3
"""
Workflow Persistence — resumable run state (Cowabunga v4 adaptation).

Mongo-backed (survives restarts/forks). Persists both finished run records
(for history) and in-flight workflow state (for resume).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from urllib.parse import urlsplit, urlunsplit
from typing import Dict, List, Optional

from gameforge.workflow.delivery_scope import current_scope


def _owned():
    return {"scope_key": current_scope().key, "format": 2}


def _key(kind: str, identity: str) -> str:
    return hashlib.sha256(json.dumps([kind, current_scope().key, identity],
                                     separators=(",", ":")).encode()).hexdigest()


# Historical receipts must not become a second source of bearer tokens.
def _without_delivery_credentials(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"download_token", "token"}:
                continue
            if key in {"download_link", "qr_payload"} and isinstance(item, str):
                parts = urlsplit(item)
                result[key] = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
            else:
                result[key] = _without_delivery_credentials(item)
        return result
    if isinstance(value, list):
        return [_without_delivery_credentials(item) for item in value]
    return value


class WorkflowPersistence:
    def _db(self):
        from core.databases import get_sync_db
        return get_sync_db()

    def _runs(self):
        return self._db()["gameforge_workflow_runs"]

    def _state(self):
        return self._db()["gameforge_workflow_state"]

    # ── finished runs (history) ───────────────────────────────────────
    def save_run(self, project_name: str, run: Dict) -> str:
        run_id = run.get("run_id") or uuid.uuid4().hex
        doc = {**_without_delivery_credentials(run), **_owned(),
               "run_id": run_id, "project_name": project_name, "saved_at": time.time()}
        self._runs().update_one({"_id": _key("run", run_id), **_owned()}, {"$set": doc}, upsert=True)
        return run_id

    def list_runs(self, project_name: Optional[str] = None, limit: int = 25) -> List[Dict]:
        q: Dict = _owned()
        if project_name:
            q["project_name"] = project_name
        docs = self._runs().find(q, {"_id": 0, "scope_key": 0, "format": 0}).sort("saved_at", -1).limit(max(1, min(int(limit), 100)))
        return [_without_delivery_credentials(doc) for doc in docs]

    def get_run(self, run_id: str) -> Optional[Dict]:
        doc = self._runs().find_one({"_id": _key("run", run_id), **_owned()}, {"_id": 0, "scope_key": 0, "format": 0})
        return _without_delivery_credentials(doc) if doc else None

    # ── in-flight state (resume) ──────────────────────────────────────
    def save_state(self, project_name: str, state: Dict) -> None:
        self._state().update_one(
            {"_id": _key("state", project_name), **_owned(), "state.run_id": state["run_id"]},
            {"$set": {**_owned(), "project_name": project_name, "state": state, "updated_at": time.time()}},
            upsert=True,
        )

    def load_latest_state(self, project_name: str) -> Optional[Dict]:
        doc = self._state().find_one({"_id": _key("state", project_name), **_owned()}, {"_id": 0})
        return doc.get("state") if doc else None

    def clear_state(self, project_name: str, run_id: str) -> None:
        self._state().delete_one({"_id": _key("state", project_name), **_owned(), "state.run_id": run_id})


workflow_persistence = WorkflowPersistence()
