#!/usr/bin/env python3
"""
Workflow Persistence — resumable run state (Cowabunga v4 adaptation).

Mongo-backed (survives restarts/forks). Persists both finished run records
(for history) and in-flight workflow state (for resume).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


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
        run_id = run.get("run_id") or f"{project_name}_{int(time.time()*1000)}"
        doc = {**run, "run_id": run_id, "project_name": project_name, "saved_at": time.time()}
        self._runs().update_one({"run_id": run_id}, {"$set": doc}, upsert=True)
        return run_id

    def list_runs(self, project_name: Optional[str] = None, limit: int = 25) -> List[Dict]:
        q: Dict = {}
        if project_name:
            q["project_name"] = project_name
        docs = self._runs().find(q, {"_id": 0}).sort("saved_at", -1).limit(int(limit))
        return list(docs)

    def get_run(self, run_id: str) -> Optional[Dict]:
        return self._runs().find_one({"run_id": run_id}, {"_id": 0})

    # ── in-flight state (resume) ──────────────────────────────────────
    def save_state(self, project_name: str, state: Dict) -> None:
        self._state().update_one(
            {"project_name": project_name},
            {"$set": {"project_name": project_name, "state": state, "updated_at": time.time()}},
            upsert=True,
        )

    def load_latest_state(self, project_name: str) -> Optional[Dict]:
        doc = self._state().find_one({"project_name": project_name}, {"_id": 0})
        return doc.get("state") if doc else None

    def clear_state(self, project_name: str) -> None:
        self._state().delete_one({"project_name": project_name})


workflow_persistence = WorkflowPersistence()
