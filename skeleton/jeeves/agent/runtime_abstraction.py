"""Generalizing state/action abstraction for the Jeeves runtime guard.

Security identity and learning identity have different requirements.

Security must bind the *exact* call: exact arguments, call id, user, run and
trace. The epistemic tool gate already does this. A learned transition model,
on the other hand, becomes useless if every resource id, goal id or retry number
creates a brand-new state/action cell.

This module keeps those identities separate. ``GeneralizingRuntimeEpistemicGuard``
retains the exact intent for authorization while deriving model keys from a
bounded structural abstraction of arguments and coarse runtime signals.

The abstraction intentionally avoids storing raw strings or resource ids. Numeric
values retain sign/order-of-magnitude information because risk and cost often
change with scale; strings retain broad structural class and length only.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .epistemic_tool_gate import ToolExecutionIntent
from .model_based_control import CompactState
from .runtime_guard import (
    RuntimeEpistemicGuard,
    RuntimeGuardDenied,
    RuntimeGuardRequest,
    RuntimeGuardSignals,
)
from .types import AgentContractError, json_safe, stable_fingerprint, stable_id


@dataclass(frozen=True, slots=True)
class ArgumentAbstractionPolicy:
    maximum_depth: int = 5
    maximum_object_keys: int = 32
    maximum_sequence_items_sampled: int = 8
    string_short_limit: int = 16
    string_medium_limit: int = 128

    def __post_init__(self) -> None:
        for name in (
            "maximum_depth",
            "maximum_object_keys",
            "maximum_sequence_items_sampled",
            "string_short_limit",
            "string_medium_limit",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise AgentContractError(f"{name} must be a positive integer")
        if self.string_short_limit >= self.string_medium_limit:
            raise AgentContractError("string abstraction length limits are inverted")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "maximum_depth": self.maximum_depth,
                "maximum_object_keys": self.maximum_object_keys,
                "maximum_sequence_items_sampled": self.maximum_sequence_items_sampled,
                "string_short_limit": self.string_short_limit,
                "string_medium_limit": self.string_medium_limit,
            }
        )


class ArgumentAbstractor:
    """Map JSON values to deterministic low-information structural classes."""

    _UUID = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    _HEX = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
    _EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    _URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
    _PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\.\.?/)")
    _INTEGER_STRING = re.compile(r"^[+-]?\d+$")

    def __init__(self, policy: ArgumentAbstractionPolicy | None = None) -> None:
        self.policy = policy or ArgumentAbstractionPolicy()

    def abstract(self, value: Any) -> Any:
        clean = json_safe(value)
        return self._abstract(clean, depth=0)

    def fingerprint(self, value: Any) -> str:
        return stable_fingerprint(
            {
                "policy": self.policy.fingerprint,
                "shape": self.abstract(value),
            }
        )

    def _abstract(self, value: Any, *, depth: int) -> Any:
        if depth >= self.policy.maximum_depth:
            return {"type": self._type_name(value), "truncated": True}
        if value is None:
            return {"type": "null"}
        if type(value) is bool:
            return {"type": "bool", "value": value}
        if type(value) is int:
            return {
                "type": "int",
                "sign": self._sign(value),
                "magnitude": self._numeric_magnitude(float(value)),
            }
        if type(value) is float:
            return {
                "type": "float",
                "sign": self._sign(value),
                "magnitude": self._numeric_magnitude(value),
                "integer_like": value.is_integer(),
            }
        if isinstance(value, str):
            return self._abstract_string(value)
        if isinstance(value, list):
            sample = value[: self.policy.maximum_sequence_items_sampled]
            shapes = [self._abstract(item, depth=depth + 1) for item in sample]
            unique: dict[str, Any] = {}
            for shape in shapes:
                unique.setdefault(stable_fingerprint(shape), shape)
            return {
                "type": "array",
                "length": self._length_bucket(len(value)),
                "item_shapes": [unique[key] for key in sorted(unique)],
                "heterogeneous": len(unique) > 1,
            }
        if isinstance(value, dict):
            keys = sorted(value)
            selected = keys[: self.policy.maximum_object_keys]
            return {
                "type": "object",
                "key_count": self._length_bucket(len(keys)),
                "fields": {
                    key: self._abstract(value[key], depth=depth + 1)
                    for key in selected
                },
                "keys_truncated": len(keys) > len(selected),
            }
        raise AgentContractError(
            f"unsupported argument abstraction type: {type(value).__name__}"
        )

    def _abstract_string(self, value: str) -> Mapping[str, Any]:
        if not value:
            structural = "empty"
        elif self._UUID.fullmatch(value):
            structural = "uuid"
        elif self._EMAIL.fullmatch(value):
            structural = "email"
        elif self._URL.match(value):
            structural = "url"
        elif self._PATH.match(value):
            structural = "path"
        elif self._HEX.fullmatch(value):
            structural = "hex_identifier"
        elif self._INTEGER_STRING.fullmatch(value):
            structural = "integer_string"
        elif value.isidentifier():
            structural = "identifier"
        elif value.isalnum():
            structural = "alphanumeric"
        else:
            structural = "free_text"
        return {
            "type": "string",
            "structure": structural,
            "length": self._string_length_bucket(len(value)),
        }

    def _string_length_bucket(self, length: int) -> str:
        if length == 0:
            return "empty"
        if length <= self.policy.string_short_limit:
            return "short"
        if length <= self.policy.string_medium_limit:
            return "medium"
        return "long"

    @staticmethod
    def _length_bucket(length: int) -> str:
        if length == 0:
            return "0"
        if length == 1:
            return "1"
        if length <= 4:
            return "2-4"
        if length <= 16:
            return "5-16"
        if length <= 64:
            return "17-64"
        return "65+"

    @staticmethod
    def _sign(value: int | float) -> str:
        if value == 0:
            return "zero"
        return "positive" if value > 0 else "negative"

    @staticmethod
    def _numeric_magnitude(value: float) -> str:
        absolute = abs(value)
        if absolute == 0:
            return "0"
        if absolute < 1:
            return "lt1"
        exponent = int(math.floor(math.log10(absolute)))
        if exponent <= 0:
            return "1-9"
        if exponent == 1:
            return "10-99"
        if exponent == 2:
            return "100-999"
        if exponent == 3:
            return "1k-9k"
        if exponent <= 5:
            return "10k-999k"
        return "1m+"

    @staticmethod
    def _type_name(value: Any) -> str:
        if value is None:
            return "null"
        if type(value) is bool:
            return "bool"
        if type(value) is int:
            return "int"
        if type(value) is float:
            return "float"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return type(value).__name__


class GeneralizingRuntimeEpistemicGuard(RuntimeEpistemicGuard):
    """Runtime guard with separate exact authorization and generalized model keys."""

    def __init__(
        self,
        *args: Any,
        argument_abstractor: ArgumentAbstractor | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.argument_abstractor = argument_abstractor or ArgumentAbstractor()

    def execute(self, request: RuntimeGuardRequest):
        if not isinstance(request, RuntimeGuardRequest):
            raise TypeError("request must be RuntimeGuardRequest")
        if request.host_policy_decision.decision.value != "allow":
            raise RuntimeGuardDenied(
                "runtime guard refuses a call not already allowed by host policy"
            )
        if not self.policy.enabled:
            raise RuntimeGuardDenied("runtime epistemic guard is disabled")

        ledger = self.audit_store.get_or_create(request.run_id)
        request_fingerprint = self._request_fingerprint(request)
        argument_abstraction = self.argument_abstractor.abstract(request.call.arguments)
        abstraction_fingerprint = stable_fingerprint(argument_abstraction)
        action_id = stable_id(
            "tool_action",
            {
                "tool": request.call.name,
                "argument_abstraction": argument_abstraction,
                "risk": request.tool_spec.risk.value,
                "abstraction_policy": self.argument_abstractor.policy.fingerprint,
            },
        )
        intent = ToolExecutionIntent.bind(
            action_id=action_id,
            call=request.call,
            context=request.execution_context,
            metadata={
                "goal_id": request.goal_id,
                "step_id": request.step_id,
                "attempt": request.attempt,
                "plan_version": request.plan_version,
                "request_fingerprint": request_fingerprint,
                "argument_abstraction_fingerprint": abstraction_fingerprint,
            },
        )
        operation_id = stable_id(
            "guard_op",
            {
                "run": request.run_id,
                "step": request.step_id,
                "attempt": request.attempt,
                "intent": intent.fingerprint,
            },
        )
        self._reserve_operation(operation_id)
        try:
            return self._execute_reserved(
                request,
                ledger=ledger,
                request_fingerprint=request_fingerprint,
                action_id=action_id,
                intent=intent,
                operation_id=operation_id,
            )
        except Exception:
            with self._lock:
                self._reserved.discard(operation_id)
            raise

    def _compact_state(
        self,
        request: RuntimeGuardRequest,
        *,
        phase: str,
        signals: RuntimeGuardSignals | None = None,
        extra_features: Mapping[str, Any] | None = None,
    ) -> CompactState:
        selected = signals or request.signals
        argument_abstraction = self.argument_abstractor.abstract(request.call.arguments)
        features: dict[str, Any] = {
            "phase": phase,
            "tool": request.call.name,
            "risk": request.tool_spec.risk.value,
            "argument_class": stable_fingerprint(argument_abstraction)[:16],
        }
        features.update(dict(extra_features or {}))
        return CompactState.from_signals(
            features=features,
            progress=selected.progress,
            uncertainty=selected.uncertainty,
            budget_pressure=selected.budget_pressure,
            failure_pressure=selected.failure_pressure,
            risk=request.tool_spec.risk,
            terminal=selected.terminal,
            metadata={
                "run_id": request.run_id,
                "goal_id": request.goal_id,
                "step_id": request.step_id,
                "attempt": request.attempt,
                "plan_version": request.plan_version,
                "request_fingerprint": self._request_fingerprint(request),
                "argument_abstraction": argument_abstraction,
                "argument_abstraction_policy": self.argument_abstractor.policy.fingerprint,
            },
        )

    def learning_identity(self, request: RuntimeGuardRequest) -> Mapping[str, Any]:
        """Return the non-secret generalized state/action identity for diagnostics."""

        abstracted = self.argument_abstractor.abstract(request.call.arguments)
        state = self._compact_state(request, phase="pre")
        action_id = stable_id(
            "tool_action",
            {
                "tool": request.call.name,
                "argument_abstraction": abstracted,
                "risk": request.tool_spec.risk.value,
                "abstraction_policy": self.argument_abstractor.policy.fingerprint,
            },
        )
        return json_safe(
            {
                "state_id": state.state_id,
                "state_fingerprint": state.fingerprint,
                "action_id": action_id,
                "argument_abstraction": abstracted,
                "argument_abstraction_fingerprint": stable_fingerprint(abstracted),
                "policy_fingerprint": self.argument_abstractor.policy.fingerprint,
            }
        )