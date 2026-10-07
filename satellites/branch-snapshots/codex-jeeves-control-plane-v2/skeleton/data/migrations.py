"""Data migrations — ordered, reversible state migrations.

Migration runner for schema/data evolution across all persisted
Skeleton state files. Each migration has an id, up() and down(),
and is recorded in a migrations ledger so state is never migrated
twice or rolled back past a checkpoint.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Migration:
    migration_id: str
    description: str
    up: Callable[[Path], None]
    down: Optional[Callable[[Path], None]] = None


class MigrationRunner:
    """Ordered migration runner with persistent ledger."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".skeleton")
        self._migrations: List[Migration] = []
        self._ledger_file = self.root / "migrations.json"
        self._applied: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._ledger_file.exists():
            self._applied = json.loads(self._ledger_file.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._ledger_file.write_text(json.dumps(self._applied, indent=2), encoding="utf-8")

    def register(self, migration_id: str, description: str,
                 up: Callable[[Path], None],
                 down: Optional[Callable[[Path], None]] = None) -> Migration:
        m = Migration(migration_id=migration_id, description=description, up=up, down=down)
        self._migrations.append(m)
        self._migrations.sort(key=lambda x: x.migration_id)
        return m

    def applied_ids(self) -> List[str]:
        return [a["migration_id"] for a in self._applied]

    def pending(self) -> List[Migration]:
        applied = set(self.applied_ids())
        return [m for m in self._migrations if m.migration_id not in applied]

    def migrate(self, target: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        ran: List[str] = []
        for m in self.pending():
            if target and m.migration_id > target:
                break
            if not dry_run:
                m.up(self.root)
                self._applied.append({
                    "migration_id": m.migration_id,
                    "applied_ns": time.time_ns(),
                    "description": m.description,
                })
                self._save()
            ran.append(m.migration_id)
        return {"migrated": ran, "dry_run": dry_run, "pending_after": len(self.pending())}

    def rollback(self, steps: int = 1) -> Dict[str, Any]:
        rolled: List[str] = []
        by_id = {m.migration_id: m for m in self._migrations}
        for _ in range(min(steps, len(self._applied))):
            last = self._applied[-1]
            m = by_id.get(last["migration_id"])
            if not m or not m.down:
                break
            m.down(self.root)
            self._applied.pop()
            self._save()
            rolled.append(m.migration_id)
        return {"rolled_back": rolled}

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "migration-card",
            "registered": len(self._migrations),
            "applied": len(self._applied),
            "pending": len(self.pending()),
            "latest": self._applied[-1] if self._applied else None,
        }
