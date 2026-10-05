"""Versioned data-class consistency policy for VOL-030.

The policy is descriptive and non-executing. It defines the minimum consistency
semantics required for each governed data class and produces content-addressed
policy identity that remote-execution requests can bind.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Any

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.vault.data_governance import DataClass


CONSISTENCY_POLICY_SCHEMA_VERSION = 1
CONSISTENCY_POLICY_ID = "vol030-data-class-consistency"
CONSISTENCY_POLICY_VERSION = 1


class ConsistencyPolicyError(ValueError):
    """Consistency policy or request is malformed."""


class ConsistencyMode(str, Enum):
    EVENTUAL = "eventual"
    READ_YOUR_WRITES = "read_your_writes"
    LINEARIZABLE = "linearizable"


_STRENGTH = {
    ConsistencyMode.EVENTUAL: 0,
    ConsistencyMode.READ_YOUR_WRITES: 1,
    ConsistencyMode.LINEARIZABLE: 2,
}


def _mode(value: ConsistencyMode | str) -> ConsistencyMode:
    try:
        return ConsistencyMode(value)
    except ValueError as exc:
        raise ConsistencyPolicyError("invalid consistency mode") from exc


@dataclass(frozen=True, slots=True)
class DataClassConsistencyRule:
    data_class: DataClass | str | int
    minimum_mode: ConsistencyMode | str
    allow_remote_execution: bool = True

    def __post_init__(self) -> None:
        try:
            classification = DataClass.parse(self.data_class)
        except Exception as exc:
            raise ConsistencyPolicyError("invalid data class") from exc
        object.__setattr__(self, "data_class", classification)
        object.__setattr__(self, "minimum_mode", _mode(self.minimum_mode))
        if not isinstance(self.allow_remote_execution, bool):
            raise ConsistencyPolicyError(
                "allow_remote_execution must be boolean"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "data_class": self.data_class.label,
            "minimum_mode": self.minimum_mode.value,
            "allow_remote_execution": self.allow_remote_execution,
        }


@dataclass(frozen=True, slots=True)
class DataConsistencyPolicy:
    policy_id: str
    version: int
    rules: tuple[DataClassConsistencyRule, ...]
    schema_version: int = CONSISTENCY_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.policy_id != CONSISTENCY_POLICY_ID:
            raise ConsistencyPolicyError("policy_id drift")
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version < 1
        ):
            raise ConsistencyPolicyError("version must be positive integer")
        if not isinstance(self.rules, tuple) or not self.rules:
            raise ConsistencyPolicyError("rules must be non-empty tuple")
        if any(
            not isinstance(rule, DataClassConsistencyRule)
            for rule in self.rules
        ):
            raise ConsistencyPolicyError(
                "rules must contain DataClassConsistencyRule"
            )
        by_class = {rule.data_class: rule for rule in self.rules}
        if len(by_class) != len(self.rules):
            raise ConsistencyPolicyError("duplicate data-class rule")
        if set(by_class) != set(DataClass):
            raise ConsistencyPolicyError(
                "policy must cover every governed data class"
            )
        object.__setattr__(
            self,
            "rules",
            tuple(sorted(self.rules, key=lambda rule: int(rule.data_class))),
        )
        if self.schema_version != CONSISTENCY_POLICY_SCHEMA_VERSION:
            raise ConsistencyPolicyError(
                "unsupported consistency policy schema"
            )

    def rule_for(
        self,
        data_class: DataClass | str | int,
    ) -> DataClassConsistencyRule:
        try:
            classification = DataClass.parse(data_class)
        except Exception as exc:
            raise ConsistencyPolicyError("invalid data class") from exc
        for rule in self.rules:
            if rule.data_class is classification:
                return rule
        raise ConsistencyPolicyError("data class is not governed")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "rules": [rule.payload() for rule in self.rules],
            "authority_scope": "consistency-policy-only",
            "production_authority": False,
        }

    @property
    def policy_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


def canonical_data_consistency_policy() -> DataConsistencyPolicy:
    return DataConsistencyPolicy(
        policy_id=CONSISTENCY_POLICY_ID,
        version=CONSISTENCY_POLICY_VERSION,
        rules=(
            DataClassConsistencyRule(
                DataClass.PUBLIC,
                ConsistencyMode.EVENTUAL,
            ),
            DataClassConsistencyRule(
                DataClass.INTERNAL,
                ConsistencyMode.READ_YOUR_WRITES,
            ),
            DataClassConsistencyRule(
                DataClass.CONFIDENTIAL,
                ConsistencyMode.LINEARIZABLE,
            ),
            DataClassConsistencyRule(
                DataClass.RESTRICTED,
                ConsistencyMode.LINEARIZABLE,
            ),
        ),
    )


def consistency_satisfies(
    *,
    policy: DataConsistencyPolicy,
    data_class: DataClass | str | int,
    requested_mode: ConsistencyMode | str,
) -> bool:
    if not isinstance(policy, DataConsistencyPolicy):
        raise TypeError("policy must be DataConsistencyPolicy")
    mode = _mode(requested_mode)
    rule = policy.rule_for(data_class)
    if not rule.allow_remote_execution:
        return False
    return _STRENGTH[mode] >= _STRENGTH[rule.minimum_mode]


__all__ = [
    "CONSISTENCY_POLICY_ID",
    "CONSISTENCY_POLICY_SCHEMA_VERSION",
    "CONSISTENCY_POLICY_VERSION",
    "ConsistencyMode",
    "ConsistencyPolicyError",
    "DataClassConsistencyRule",
    "DataConsistencyPolicy",
    "canonical_data_consistency_policy",
    "consistency_satisfies",
]
