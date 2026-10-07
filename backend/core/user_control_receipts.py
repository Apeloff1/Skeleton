"""Restart-safe durable storage for accepted AUTO-04 human-control receipts."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading

from skeleton.agents.autonomy_control import AutonomyLevel
from skeleton.agents.human_control import (
    HumanControlAction,
    HumanControlDecision,
)
from skeleton.contracts.canonical import EvidenceRef


class HumanControlReceiptStoreError(RuntimeError):
    """Durable human-control receipt storage failed closed."""


class HumanControlReceiptConflict(HumanControlReceiptStoreError):
    """A receipt conflicts with already committed control history."""


def _decision_from_json(raw: object) -> HumanControlDecision:
    if not isinstance(raw, str):
        raise HumanControlReceiptStoreError("decision_json must be text")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HumanControlReceiptStoreError("decision_json is invalid") from exc
    if not isinstance(payload, dict):
        raise HumanControlReceiptStoreError("decision_json must be an object")
    refs = payload.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        raise HumanControlReceiptStoreError("decision evidence is missing")
    evidence = tuple(
        EvidenceRef(
            source=item["source"],
            digest=item["digest"],
            category=item["category"],
        )
        for item in refs
    )
    requested = payload.get("requested_level")
    return HumanControlDecision(
        accepted=payload["accepted"],
        action=HumanControlAction(payload["action"]),
        reasons=tuple(payload["reasons"]),
        operation_id=payload["operation_id"],
        execution_id=payload["execution_id"],
        agent_id=payload["agent_id"],
        arguments_digest=payload["arguments_digest"],
        state_digest=payload["state_digest"],
        command_digest=payload["command_digest"],
        autonomy_state_digest=payload["autonomy_state_digest"],
        authority_digest=payload["authority_digest"],
        from_level=AutonomyLevel(payload["from_level"]),
        requested_level=(
            None if requested is None else AutonomyLevel(requested)
        ),
        next_level=AutonomyLevel(payload["next_level"]),
        next_paused=payload["next_paused"],
        next_interrupted=payload["next_interrupted"],
        current_version=payload["current_version"],
        next_version=payload["next_version"],
        issuer_id=payload["issuer_id"],
        issuer_digest=payload["issuer_digest"],
        expires_at=payload["expires_at"],
        evidence_refs=evidence,
        independent=payload["independent"],
        observed_at=payload["observed_at"],
        previous_receipt_digest=payload.get("previous_receipt_digest"),
        task_id=payload.get("task_id", "P1-AUTO-04"),
        accountability_id=payload.get(
            "accountability_id",
            "ACC-P1-AUTO-04",
        ),
        schema_version=payload.get("schema_version", 1),
    )


class SQLiteHumanControlReceiptStore:
    """Append-only accepted human-control receipt chain.

    The store is tenant-scoped even though AUTO-04 receipts themselves do not
    contain tenant identity. Tenant binding is therefore durable storage
    metadata and is always supplied again when reading.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "human_control",
    ) -> None:
        normalized = str(namespace).strip()
        if not normalized:
            raise ValueError("namespace must not be empty")
        self.namespace = normalized
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS human_control_receipt (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    authority_digest TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    next_version INTEGER NOT NULL,
                    receipt_digest TEXT NOT NULL,
                    previous_receipt_digest TEXT,
                    action TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    PRIMARY KEY(
                        namespace,
                        tenant_id,
                        operation_id,
                        execution_id,
                        next_version
                    ),
                    UNIQUE(namespace, tenant_id, receipt_digest)
                );

                CREATE INDEX IF NOT EXISTS idx_human_control_latest
                ON human_control_receipt(
                    namespace,
                    tenant_id,
                    operation_id,
                    execution_id,
                    next_version DESC
                );
                """
            )

    @staticmethod
    def _tenant(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise HumanControlReceiptStoreError(
                "tenant_id must be non-empty"
            )
        normalized = value.strip()
        if normalized != value:
            raise HumanControlReceiptStoreError(
                "tenant_id must be normalized"
            )
        return normalized

    def append(
        self,
        *,
        tenant_id: str,
        decision: HumanControlDecision,
    ) -> HumanControlDecision:
        tenant = self._tenant(tenant_id)
        if not isinstance(decision, HumanControlDecision):
            raise TypeError("decision must be HumanControlDecision")
        if not decision.accepted:
            raise HumanControlReceiptConflict(
                "rejected human-control decision cannot be persisted"
            )

        payload = json.dumps(
            decision.receipt_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        key = (
            self.namespace,
            tenant,
            decision.operation_id,
            decision.execution_id,
        )

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                duplicate = self._connection.execute(
                    """
                    SELECT decision_json
                    FROM human_control_receipt
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND receipt_digest = ?
                    """,
                    (
                        self.namespace,
                        tenant,
                        decision.receipt_digest,
                    ),
                ).fetchone()
                if duplicate is not None:
                    existing = _decision_from_json(
                        duplicate["decision_json"]
                    )
                    if existing != decision:
                        raise HumanControlReceiptConflict(
                            "receipt digest already committed differently"
                        )
                    self._connection.execute("COMMIT")
                    return existing

                prior = self._connection.execute(
                    """
                    SELECT *
                    FROM human_control_receipt
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND execution_id = ?
                    ORDER BY next_version DESC
                    LIMIT 1
                    """,
                    key,
                ).fetchone()

                if prior is None:
                    if decision.current_version != 1:
                        raise HumanControlReceiptConflict(
                            "first durable receipt must begin at version 1"
                        )
                    if decision.previous_receipt_digest is not None:
                        raise HumanControlReceiptConflict(
                            "first durable receipt cannot name predecessor"
                        )
                else:
                    if prior["agent_id"] != decision.agent_id:
                        raise HumanControlReceiptConflict(
                            "agent identity changed inside receipt chain"
                        )
                    if (
                        prior["authority_digest"]
                        != decision.authority_digest
                    ):
                        raise HumanControlReceiptConflict(
                            "authority digest changed inside receipt chain"
                        )
                    if (
                        int(prior["next_version"])
                        != decision.current_version
                    ):
                        raise HumanControlReceiptConflict(
                            "receipt version is not contiguous"
                        )
                    if (
                        prior["receipt_digest"]
                        != decision.previous_receipt_digest
                    ):
                        raise HumanControlReceiptConflict(
                            "receipt predecessor digest mismatch"
                        )

                self._connection.execute(
                    """
                    INSERT INTO human_control_receipt(
                        namespace,
                        tenant_id,
                        operation_id,
                        execution_id,
                        agent_id,
                        authority_digest,
                        current_version,
                        next_version,
                        receipt_digest,
                        previous_receipt_digest,
                        action,
                        decision_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        tenant,
                        decision.operation_id,
                        decision.execution_id,
                        decision.agent_id,
                        decision.authority_digest,
                        decision.current_version,
                        decision.next_version,
                        decision.receipt_digest,
                        decision.previous_receipt_digest,
                        decision.action.value,
                        payload,
                    ),
                )
                self._connection.execute("COMMIT")
                return decision
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def chain(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        execution_id: str,
    ) -> tuple[HumanControlDecision, ...]:
        tenant = self._tenant(tenant_id)
        for field, value in (
            ("operation_id", operation_id),
            ("execution_id", execution_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise HumanControlReceiptStoreError(
                    f"{field} must be non-empty"
                )
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT decision_json
                FROM human_control_receipt
                WHERE namespace = ?
                  AND tenant_id = ?
                  AND operation_id = ?
                  AND execution_id = ?
                ORDER BY next_version ASC
                """,
                (
                    self.namespace,
                    tenant,
                    operation_id,
                    execution_id,
                ),
            ).fetchall()
        decisions = tuple(
            _decision_from_json(row["decision_json"]) for row in rows
        )
        previous: HumanControlDecision | None = None
        for item in decisions:
            if previous is None:
                if (
                    item.current_version != 1
                    or item.previous_receipt_digest is not None
                ):
                    raise HumanControlReceiptStoreError(
                        "persisted receipt chain has invalid root"
                    )
            else:
                if item.current_version != previous.next_version:
                    raise HumanControlReceiptStoreError(
                        "persisted receipt chain is non-contiguous"
                    )
                if (
                    item.previous_receipt_digest
                    != previous.receipt_digest
                ):
                    raise HumanControlReceiptStoreError(
                        "persisted receipt chain predecessor mismatch"
                    )
            previous = item
        return decisions

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "HumanControlReceiptConflict",
    "HumanControlReceiptStoreError",
    "SQLiteHumanControlReceiptStore",
]
