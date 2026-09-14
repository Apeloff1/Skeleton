"""Integrity-checked durable receipts for governed product execution.

Receipts are written only by executors after producing a concrete result. Each
operation gets at most one canonical receipt file. The envelope is SHA-256
protected and atomically replaced so dashboards can trust completed-work state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


class ReceiptIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    operation_id: str
    capability_id: str
    action: str
    executor: str
    completed_at: str
    result: dict[str, Any]


class ExecutionReceiptStore:
    VERSION = 1

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _canonical(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def _digest(cls, payload: dict[str, Any]) -> str:
        return hashlib.sha256(cls._canonical(payload)).hexdigest()

    def _path(self, operation_id: str) -> Path:
        operation_id = operation_id.strip()
        if not operation_id or any(ch not in "0123456789abcdef" for ch in operation_id.lower()):
            raise ValueError("operation_id must be a hexadecimal identifier")
        return self.directory / f"{operation_id}.json"

    def write(
        self,
        *,
        operation_id: str,
        capability_id: str,
        action: str,
        executor: str,
        result: dict[str, Any],
    ) -> ExecutionReceipt:
        # Validate result serialization before touching disk.
        self._canonical(result)
        path = self._path(operation_id)
        receipt = ExecutionReceipt(
            operation_id=operation_id,
            capability_id=capability_id,
            action=action,
            executor=executor,
            completed_at=datetime.now(UTC).isoformat(),
            result=dict(result),
        )
        payload = {"version": self.VERSION, "receipt": asdict(receipt)}
        envelope = {"payload": payload, "sha256": self._digest(payload)}
        temp = path.with_suffix(".tmp")
        with temp.open("wb") as handle:
            handle.write(self._canonical(envelope))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        return receipt

    def read(self, operation_id: str) -> ExecutionReceipt | None:
        path = self._path(operation_id)
        if not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            payload = envelope["payload"]
            digest = envelope["sha256"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ReceiptIntegrityError("execution receipt is unreadable") from exc
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION or not isinstance(digest, str):
            raise ReceiptIntegrityError("execution receipt envelope is malformed")
        if not hmac.compare_digest(self._digest(payload), digest):
            raise ReceiptIntegrityError("execution receipt checksum mismatch")
        try:
            raw = payload["receipt"]
            return ExecutionReceipt(
                operation_id=str(raw["operation_id"]),
                capability_id=str(raw["capability_id"]),
                action=str(raw["action"]),
                executor=str(raw["executor"]),
                completed_at=str(raw["completed_at"]),
                result=dict(raw["result"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReceiptIntegrityError("execution receipt payload is invalid") from exc

    def list_recent(self, *, limit: int = 50) -> list[ExecutionReceipt]:
        if limit < 0 or limit > 500:
            raise ValueError("limit must be between 0 and 500")
        paths = sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        receipts: list[ExecutionReceipt] = []
        for path in paths[:limit]:
            receipt = self.read(path.stem)
            if receipt is not None:
                receipts.append(receipt)
        return receipts
