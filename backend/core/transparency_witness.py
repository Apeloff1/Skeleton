"""Trusted witness quorum for transparency roots.

Witness agreement authenticates publication state, not scientific truth. A witness
is configured out-of-band with an independence group; callers cannot self-assign a
group. Multiple witnesses from the same group count once. Equivocation by a trusted
witness freezes finality for the affected log until an operator resolves it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from core.file_lease import FileLease

WITNESS_LEDGER_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class WitnessIntegrityError(RuntimeError):
    pass


class WitnessRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TrustedWitness:
    id: str
    independence_group: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class WitnessReceipt:
    version: int
    log_id: str
    tree_size: int
    root_sha256: str
    witness_id: str
    independence_group: str
    observed_at: str
    transport_authenticated: bool
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class WitnessQuorum:
    log_id: str
    tree_size: int
    root_sha256: str
    trusted_receipts: int
    independent_groups: int
    required_groups: int
    reached: bool
    frozen: bool
    witness_ids: tuple[str, ...]
    groups: tuple[str, ...]
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _receipt_payload(*, log_id: str, tree_size: int, root_sha256: str, witness_id: str,
                     independence_group: str, observed_at: str, transport_authenticated: bool) -> dict[str, Any]:
    return {
        "version": WITNESS_LEDGER_VERSION,
        "log_id": log_id,
        "tree_size": tree_size,
        "root_sha256": root_sha256,
        "witness_id": witness_id,
        "independence_group": independence_group,
        "observed_at": observed_at,
        "transport_authenticated": transport_authenticated,
    }


class TransparencyWitnessLedger:
    def __init__(self, root: str | Path, *, trusted_witnesses: Iterable[TrustedWitness] = (),
                 required_groups: int = 3) -> None:
        if required_groups < 1:
            raise ValueError("required_groups must be >= 1")
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "transparency-witnesses.json"
        self._lease = FileLease(self.root / ".transparency-witnesses.lock")
        self.required_groups = int(required_groups)
        self._trusted = self._normalize_registry(trusted_witnesses)
        with self._lease.acquire():
            if not self.path.exists(): self._write([], [])
            else: self._load()

    @staticmethod
    def _normalize_registry(rows: Iterable[TrustedWitness]) -> dict[str, TrustedWitness]:
        registry: dict[str, TrustedWitness] = {}
        for row in rows:
            witness_id = str(row.id).strip(); group = str(row.independence_group).strip()
            if not witness_id or not group:
                raise ValueError("trusted witness id and independence_group are required")
            if witness_id in registry:
                raise ValueError(f"duplicate trusted witness: {witness_id}")
            registry[witness_id] = TrustedWitness(witness_id, group, bool(row.enabled))
        return registry

    def configure(self, rows: Iterable[TrustedWitness]) -> None:
        registry = self._normalize_registry(rows)
        with self._lease.acquire():
            # Configuration is runtime policy. Existing receipts remain historical,
            # but quorum evaluation always uses the current trusted registry.
            self._trusted = registry

    @staticmethod
    def _checksum(receipts: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> str:
        return _sha({"version": WITNESS_LEDGER_VERSION, "receipts": receipts, "incidents": incidents})

    def _load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try: env = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise WitnessIntegrityError("witness ledger unreadable") from exc
        receipts = env.get("receipts"); incidents = env.get("incidents"); checksum = env.get("sha256")
        if env.get("version") != WITNESS_LEDGER_VERSION or not isinstance(receipts, list) or not isinstance(incidents, list) or not isinstance(checksum, str):
            raise WitnessIntegrityError("witness ledger malformed")
        if not hmac.compare_digest(checksum, self._checksum(receipts, incidents)):
            raise WitnessIntegrityError("witness ledger checksum mismatch")
        for raw in receipts:
            if not isinstance(raw, dict) or not _SHA256.fullmatch(str(raw.get("receipt_sha256", ""))):
                raise WitnessIntegrityError("witness receipt malformed")
            payload = {key: raw[key] for key in (
                "version", "log_id", "tree_size", "root_sha256", "witness_id",
                "independence_group", "observed_at", "transport_authenticated",
            )}
            if not hmac.compare_digest(_sha(payload), str(raw["receipt_sha256"])):
                raise WitnessIntegrityError("witness receipt hash mismatch")
        return [dict(x) for x in receipts], [dict(x) for x in incidents]

    def _write(self, receipts: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> None:
        env = {"version": WITNESS_LEDGER_VERSION, "receipts": receipts, "incidents": incidents,
               "sha256": self._checksum(receipts, incidents)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(env)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    def observe(self, *, log_id: str, tree_size: int, root_sha256: str, witness_id: str,
                transport_authenticated: bool, observed_at: str | None = None) -> WitnessReceipt:
        log_id = str(log_id).strip(); witness_id = str(witness_id).strip(); root_sha256 = str(root_sha256).lower().strip()
        witness = self._trusted.get(witness_id)
        if not log_id or tree_size < 0 or not _SHA256.fullmatch(root_sha256):
            raise WitnessRejected("invalid witness observation")
        if witness is None or not witness.enabled:
            raise WitnessRejected("witness is not trusted/enabled")
        if transport_authenticated is not True:
            raise WitnessRejected("witness transport is not authenticated")
        stamp = observed_at or datetime.now(UTC).isoformat()
        payload = _receipt_payload(log_id=log_id, tree_size=tree_size, root_sha256=root_sha256,
                                   witness_id=witness_id, independence_group=witness.independence_group,
                                   observed_at=stamp, transport_authenticated=True)
        receipt = WitnessReceipt(**payload, receipt_sha256=_sha(payload))
        with self._lease.acquire():
            receipts, incidents = self._load()
            same_identity = [r for r in receipts if r.get("log_id") == log_id and int(r.get("tree_size", -1)) == tree_size and r.get("witness_id") == witness_id]
            for prior in same_identity:
                if prior.get("root_sha256") != root_sha256:
                    incident = {"kind": "witness_equivocation", "log_id": log_id, "tree_size": tree_size,
                                "witness_id": witness_id, "independence_group": witness.independence_group,
                                "roots": sorted({str(prior.get("root_sha256")), root_sha256}), "observed_at": stamp}
                    if incident not in incidents: incidents.append(incident)
                    self._write(receipts, incidents)
                    raise WitnessRejected("trusted witness equivocated for the same tree size")
                return WitnessReceipt(**prior)
            receipts.append(asdict(receipt)); self._write(receipts, incidents); return receipt

    def quorum(self, *, log_id: str, tree_size: int, root_sha256: str) -> WitnessQuorum:
        root_sha256 = str(root_sha256).lower().strip()
        if not str(log_id).strip() or tree_size < 0 or not _SHA256.fullmatch(root_sha256):
            raise ValueError("invalid quorum target")
        with self._lease.acquire(): receipts, incidents = self._load()
        target = [r for r in receipts if r.get("log_id") == log_id and int(r.get("tree_size", -1)) == tree_size and r.get("root_sha256") == root_sha256]
        trusted: list[dict[str, Any]] = []
        for raw in target:
            witness = self._trusted.get(str(raw.get("witness_id", "")))
            if witness is None or not witness.enabled or not raw.get("transport_authenticated"):
                continue
            if witness.independence_group != raw.get("independence_group"):
                continue
            trusted.append(raw)
        groups = tuple(sorted({str(r["independence_group"]) for r in trusted}))
        witness_ids = tuple(sorted({str(r["witness_id"]) for r in trusted}))
        frozen = any(i.get("log_id") == log_id and i.get("kind") == "witness_equivocation" for i in incidents)
        reached = not frozen and len(groups) >= self.required_groups
        payload = {"log_id": log_id, "tree_size": tree_size, "root_sha256": root_sha256,
                   "trusted_receipts": len(trusted), "independent_groups": len(groups),
                   "required_groups": self.required_groups, "reached": reached, "frozen": frozen,
                   "witness_ids": witness_ids, "groups": groups}
        return WitnessQuorum(**payload, attestation_sha256=_sha(payload))

    def status(self) -> dict[str, Any]:
        with self._lease.acquire(): receipts, incidents = self._load()
        equivocations = sum(i.get("kind") == "witness_equivocation" for i in incidents)
        return {"version": WITNESS_LEDGER_VERSION, "trusted_witnesses": len(self._trusted),
                "enabled_witnesses": sum(w.enabled for w in self._trusted.values()),
                "independence_groups": len({w.independence_group for w in self._trusted.values() if w.enabled}),
                "required_groups": self.required_groups, "receipts": len(receipts), "incidents": len(incidents),
                "equivocations": equivocations, "healthy": equivocations == 0,
                "cross_process_locking": True, "lock_backend": self._lease.backend,
                "sha256": self._checksum(receipts, incidents)}
