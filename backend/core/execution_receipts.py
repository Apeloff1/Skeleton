"""Durable execution receipts with content-addressed result payloads.

A receipt is compact proof: exact operation, input artifact, executor contract,
result digest and immutable result-manifest id. Large generated worlds/build data
live in a verified CAS instead of bloating the receipt ledger. Version-1 inline
receipts remain readable for forward migration.
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

from core.content_store import ContentAddressedStore, ContentIntegrityError


class ReceiptIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    operation_id: str
    capability_id: str
    action: str
    executor: str
    executor_version: int
    effect_class: str
    replay_safe: bool
    input_artifact_manifest_id: str
    completed_at: str
    result_artifact_id: str
    result_sha256: str
    result_summary: dict[str, Any]
    legacy_inline_result: dict[str, Any] | None = None


class ExecutionReceiptStore:
    VERSION = 2
    MAX_OPERATION_ID_LENGTH = 128

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.results = ContentAddressedStore(self.directory / "_results")

    @staticmethod
    def _canonical(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def _digest(cls, payload: Any) -> str:
        return hashlib.sha256(cls._canonical(payload)).hexdigest()

    @staticmethod
    def _summary(result: dict[str, Any], byte_count: int) -> dict[str, Any]:
        summary: dict[str, Any] = {"bytes": byte_count, "keys": sorted(str(key) for key in result)[:32]}
        for key in ("state", "status", "project_id", "session_id", "seed", "scale", "build_id", "can_ship"):
            value = result.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                if key in result:
                    summary[key] = value
        return summary

    def _path(self, operation_id: str) -> Path:
        operation_id = str(operation_id)
        if operation_id != operation_id.strip():
            raise ValueError("operation_id must be a hexadecimal identifier")
        if not operation_id or len(operation_id) > self.MAX_OPERATION_ID_LENGTH:
            raise ValueError("operation_id must be a hexadecimal identifier")
        if any(ch not in "0123456789abcdefABCDEF" for ch in operation_id):
            raise ValueError("operation_id must be a hexadecimal identifier")

        # basename() creates an explicit path boundary that static analyzers and
        # reviewers can verify. The equality check prevents silent normalization
        # from turning a traversal attempt into an alias for another receipt.
        requested = f"{operation_id}.json"
        filename = os.path.basename(requested)
        if filename != requested or filename in {"", ".", ".."}:
            raise ValueError("operation_id does not map to a safe receipt path")
        path = self.directory / filename
        if path.resolve(strict=False).parent != self.directory.resolve():
            raise ValueError("operation_id escapes the receipt directory")
        return path

    def write(
        self,
        *,
        operation_id: str,
        capability_id: str,
        action: str,
        executor: str,
        executor_version: int,
        effect_class: str,
        replay_safe: bool,
        input_artifact_manifest_id: str,
        result: dict[str, Any],
    ) -> ExecutionReceipt:
        if executor_version <= 0:
            raise ValueError("executor_version must be positive")
        if effect_class not in {"query", "state", "external"}:
            raise ValueError("invalid effect_class")
        result_bytes = self._canonical(result)
        result_digest = hashlib.sha256(result_bytes).hexdigest()
        path = self._path(operation_id)
        existing = self.read(operation_id)
        if existing is not None:
            if (
                existing.capability_id == capability_id
                and existing.action == action
                and existing.executor == executor
                and existing.executor_version == executor_version
                and existing.effect_class == effect_class
                and existing.replay_safe == replay_safe
                and existing.input_artifact_manifest_id == input_artifact_manifest_id
                and hmac.compare_digest(existing.result_sha256, result_digest)
            ):
                return existing
            raise ReceiptIntegrityError("execution receipt is write-once")

        result_manifest = self.results.put_bytes(f"result-{operation_id}.json", result_bytes)
        receipt = ExecutionReceipt(
            operation_id=operation_id,
            capability_id=capability_id,
            action=action,
            executor=executor,
            executor_version=executor_version,
            effect_class=effect_class,
            replay_safe=replay_safe,
            input_artifact_manifest_id=input_artifact_manifest_id,
            completed_at=datetime.now(UTC).isoformat(),
            result_artifact_id=result_manifest.id,
            result_sha256=result_digest,
            result_summary=self._summary(result, len(result_bytes)),
        )
        payload = {"version": self.VERSION, "receipt": asdict(receipt)}
        envelope = {"payload": payload, "sha256": self._digest(payload)}
        temp = path.with_suffix(".tmp")
        try:
            with temp.open("xb") as handle:
                handle.write(self._canonical(envelope))
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists():
                raise ReceiptIntegrityError("execution receipt already exists")
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)
        return receipt

    def _read_v1(self, raw: dict[str, Any]) -> ExecutionReceipt:
        result = dict(raw["result"])
        result_bytes = self._canonical(result)
        return ExecutionReceipt(
            operation_id=str(raw["operation_id"]), capability_id=str(raw["capability_id"]),
            action=str(raw["action"]), executor=str(raw["executor"]), executor_version=1,
            effect_class="state", replay_safe=False, input_artifact_manifest_id="",
            completed_at=str(raw["completed_at"]), result_artifact_id="",
            result_sha256=hashlib.sha256(result_bytes).hexdigest(),
            result_summary=self._summary(result, len(result_bytes)), legacy_inline_result=result,
        )

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
        if not isinstance(payload, dict) or not isinstance(digest, str):
            raise ReceiptIntegrityError("execution receipt envelope is malformed")
        if not hmac.compare_digest(self._digest(payload), digest):
            raise ReceiptIntegrityError("execution receipt checksum mismatch")
        version = payload.get("version")
        try:
            raw = payload["receipt"]
            if version == 1:
                receipt = self._read_v1(raw)
            elif version == self.VERSION:
                receipt = ExecutionReceipt(
                    operation_id=str(raw["operation_id"]), capability_id=str(raw["capability_id"]),
                    action=str(raw["action"]), executor=str(raw["executor"]),
                    executor_version=int(raw["executor_version"]), effect_class=str(raw["effect_class"]),
                    replay_safe=bool(raw["replay_safe"]), input_artifact_manifest_id=str(raw["input_artifact_manifest_id"]),
                    completed_at=str(raw["completed_at"]), result_artifact_id=str(raw["result_artifact_id"]),
                    result_sha256=str(raw["result_sha256"]), result_summary=dict(raw["result_summary"]),
                    legacy_inline_result=dict(raw["legacy_inline_result"]) if raw.get("legacy_inline_result") is not None else None,
                )
            else:
                raise ReceiptIntegrityError("unsupported execution receipt version")
        except ReceiptIntegrityError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ReceiptIntegrityError("execution receipt payload is invalid") from exc
        if receipt.operation_id != operation_id:
            raise ReceiptIntegrityError("execution receipt operation id mismatch")
        return receipt

    def load_result(self, receipt_or_id: ExecutionReceipt | str) -> dict[str, Any]:
        receipt = self.read(receipt_or_id) if isinstance(receipt_or_id, str) else receipt_or_id
        if receipt is None:
            raise ReceiptIntegrityError("execution receipt not found")
        if receipt.legacy_inline_result is not None:
            return dict(receipt.legacy_inline_result)
        try:
            manifest = self.results.load_manifest(receipt.result_artifact_id)
            data = self.results.read_manifest(manifest)
        except ContentIntegrityError as exc:
            raise ReceiptIntegrityError("execution result artifact failed integrity validation") from exc
        digest = hashlib.sha256(data).hexdigest()
        if not hmac.compare_digest(digest, receipt.result_sha256):
            raise ReceiptIntegrityError("execution result digest mismatch")
        try:
            result = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReceiptIntegrityError("execution result artifact is not valid JSON") from exc
        if not isinstance(result, dict):
            raise ReceiptIntegrityError("execution result artifact must be an object")
        return result

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

    def stats(self) -> dict[str, Any]:
        return {"receipts": len(list(self.directory.glob("*.json"))), "results": self.results.stats(), "version": self.VERSION}
