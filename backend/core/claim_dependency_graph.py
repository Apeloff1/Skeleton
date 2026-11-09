"""Tamper-evident dependency graph for derived claims.

Empirical evidence can support a derived conclusion while that conclusion still
logically depends on upstream claims. This graph records those dependencies so a
revoked premise cannot remain silently embedded in authoritative downstream
knowledge. Historical knowledge remains untouched; only live authority propagates.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Iterable

from core.file_lease import FileLease


GRAPH_VERSION = 1


class ClaimDependencyIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ClaimDependency:
    claim: str
    depends_on: tuple[str, ...]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _norm(value: str) -> str:
    return " ".join(str(value).split()).strip()


class ClaimDependencyGraph:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "claim-dependencies.json"
        self._lease = FileLease(self.root / ".claim-dependencies.lock")
        with self._lease.acquire():
            if not self.path.exists(): self._write({})
            else: self._load()

    @staticmethod
    def _checksum(edges: dict[str, list[str]]) -> str:
        return _sha({"version": GRAPH_VERSION, "edges": edges})

    def _load(self) -> dict[str, list[str]]:
        try: env = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise ClaimDependencyIntegrityError("claim dependency graph unreadable") from exc
        edges = env.get("edges"); checksum = env.get("sha256")
        if env.get("version") != GRAPH_VERSION: raise ClaimDependencyIntegrityError("unsupported claim dependency graph version")
        if not isinstance(edges, dict) or not isinstance(checksum, str): raise ClaimDependencyIntegrityError("claim dependency graph malformed")
        normalized = {str(k): [str(x) for x in v] for k, v in edges.items() if isinstance(v, list)}
        if not hmac.compare_digest(checksum, self._checksum(normalized)): raise ClaimDependencyIntegrityError("claim dependency graph checksum mismatch")
        return normalized

    def _write(self, edges: dict[str, list[str]]) -> None:
        env = {"version": GRAPH_VERSION, "edges": edges, "sha256": self._checksum(edges)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(env)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    @staticmethod
    def _has_path(edges: dict[str, list[str]], start: str, target: str) -> bool:
        seen: set[str] = set(); stack = [start]
        while stack:
            current = stack.pop()
            if current == target: return True
            if current in seen: continue
            seen.add(current); stack.extend(edges.get(current, ()))
        return False

    def register(self, claim: str, depends_on: Iterable[str]) -> ClaimDependency:
        claim = _norm(claim)
        parents = tuple(dict.fromkeys(_norm(x) for x in depends_on if _norm(x)))
        if not claim: raise ValueError("claim required")
        if claim in parents: raise ValueError("claim cannot depend on itself")
        with self._lease.acquire():
            edges = self._load(); prior = tuple(edges.get(claim, ()))
            wanted = tuple(sorted(parents))
            if prior and tuple(sorted(prior)) != wanted:
                raise ClaimDependencyIntegrityError("claim dependency identity collision")
            trial = {**edges, claim: list(wanted)}
            for parent in wanted:
                if self._has_path(trial, parent, claim):
                    raise ValueError("claim dependency cycle detected")
            edges[claim] = list(wanted); self._write(edges)
        return ClaimDependency(claim, wanted)

    def dependencies(self, claim: str) -> tuple[str, ...]:
        with self._lease.acquire(): edges = self._load()
        return tuple(edges.get(_norm(claim), ()))

    def dependents(self, claim: str, *, recursive: bool = False) -> tuple[str, ...]:
        claim = _norm(claim)
        with self._lease.acquire(): edges = self._load()
        direct = {child for child, parents in edges.items() if claim in parents}
        if not recursive: return tuple(sorted(direct))
        affected = set(direct); frontier = list(direct)
        while frontier:
            parent = frontier.pop()
            for child, parents in edges.items():
                if child not in affected and parent in parents:
                    affected.add(child); frontier.append(child)
        return tuple(sorted(affected))

    def blockers(self, claim: str, authoritative) -> tuple[str, ...]:
        """Return direct dependencies that are not currently authoritative."""
        return tuple(parent for parent in self.dependencies(claim) if not authoritative(parent))

    def snapshot(self) -> tuple[ClaimDependency, ...]:
        with self._lease.acquire(): edges = self._load()
        return tuple(ClaimDependency(claim, tuple(parents)) for claim, parents in sorted(edges.items()))

    def stats(self) -> dict[str, Any]:
        with self._lease.acquire(): edges = self._load()
        return {
            "version": GRAPH_VERSION, "claims": len(edges), "edges": sum(len(v) for v in edges.values()),
            "sha256": self._checksum(edges), "cross_process_locking": True, "lock_backend": self._lease.backend,
        }
