"""Permit-bound tool execution for Jeeves.

The epistemic planner may recommend an action and the decision authorizer may
issue a fresh one-time permit, but neither should bypass the existing host tool
security model. This module composes both boundaries.

A :class:`ToolExecutionIntent` binds an abstract action to the exact call id,
tool name, arguments, user, run and trace before the action is assessed. The
intent fingerprint is carried in ``AbstractAction.metadata`` and therefore
becomes part of the candidate/decision fingerprint. At execution time the gate:

1. consumes the one-time epistemic authorization token;
2. verifies that the resulting permit still names the pre-bound intent;
3. verifies exact tool/call/argument/user/context identity; and
4. delegates to ``ToolExecutor``, which independently enforces trusted host
   grants, risk, call budgets, schema validation, timeouts and evidence output.

A binding failure burns the authorization token. This is deliberate: a token
that has been presented for a different call is treated as compromised/replayed
rather than returned to circulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .epistemic_authorization import (
    AuthorizationResult,
    AuthorizationToken,
    DecisionAuthorizer,
    ExecutionPermit,
)
from .tools import ToolExecutor, ToolExecutionContext, ToolGrant
from .types import (
    AgentContractError,
    ToolCall,
    ToolObservation,
    json_safe,
    require_id,
    require_tool_name,
    stable_fingerprint,
    stable_id,
)


class AuthorizedToolError(RuntimeError):
    """Base error for permit-bound tool execution."""


class AuthorizedToolDenied(AuthorizedToolError):
    """Raised when the epistemic authorization or exact call binding fails."""


@dataclass(frozen=True, slots=True)
class ToolExecutionIntent:
    intent_id: str
    action_id: str
    call_id: str
    tool_name: str
    argument_fingerprint: str
    user_id: str
    run_id: str
    trace_id: str
    fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", require_id("intent_id", self.intent_id))
        object.__setattr__(self, "action_id", require_id("action_id", self.action_id))
        object.__setattr__(self, "call_id", require_id("call_id", self.call_id))
        object.__setattr__(self, "tool_name", require_tool_name(self.tool_name))
        object.__setattr__(self, "user_id", require_id("user_id", self.user_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "trace_id", require_id("trace_id", self.trace_id))
        for name in ("argument_fingerprint", "fingerprint"):
            value = str(getattr(self, name)).strip().lower()
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise AgentContractError(f"{name} must be a sha256 hex fingerprint")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))
        if self.fingerprint != stable_fingerprint(self.canonical_payload):
            raise AgentContractError("tool execution intent fingerprint mismatch")

    @property
    def canonical_payload(self) -> Mapping[str, Any]:
        return {
            "action_id": self.action_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "argument_fingerprint": self.argument_fingerprint,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "metadata": self.metadata,
        }

    @classmethod
    def bind(
        cls,
        *,
        action_id: str,
        call: ToolCall,
        context: ToolExecutionContext,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolExecutionIntent":
        if not isinstance(call, ToolCall):
            raise TypeError("call must be ToolCall")
        if not isinstance(context, ToolExecutionContext):
            raise TypeError("context must be ToolExecutionContext")
        action_id = require_id("action_id", action_id)
        clean_metadata = json_safe(dict(metadata or {}))
        argument_fingerprint = stable_fingerprint(call.arguments)
        payload = {
            "action_id": action_id,
            "call_id": call.call_id,
            "tool_name": call.name,
            "argument_fingerprint": argument_fingerprint,
            "user_id": context.user_id,
            "run_id": context.run_id,
            "trace_id": context.trace_id,
            "metadata": clean_metadata,
        }
        fingerprint = stable_fingerprint(payload)
        return cls(
            intent_id=stable_id("tool_intent", {"fingerprint": fingerprint}),
            action_id=action_id,
            call_id=call.call_id,
            tool_name=call.name,
            argument_fingerprint=argument_fingerprint,
            user_id=context.user_id,
            run_id=context.run_id,
            trace_id=context.trace_id,
            fingerprint=fingerprint,
            metadata=clean_metadata,
        )


@dataclass(frozen=True, slots=True)
class BoundToolExecution:
    execution_id: str
    intent: ToolExecutionIntent
    authorization: AuthorizationResult
    permit: ExecutionPermit
    observation: ToolObservation
    call_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_id",
            require_id("execution_id", self.execution_id),
        )
        if not isinstance(self.intent, ToolExecutionIntent):
            raise AgentContractError("intent must be ToolExecutionIntent")
        if not isinstance(self.authorization, AuthorizationResult):
            raise AgentContractError("authorization must be AuthorizationResult")
        if not isinstance(self.permit, ExecutionPermit):
            raise AgentContractError("permit must be ExecutionPermit")
        if not isinstance(self.observation, ToolObservation):
            raise AgentContractError("observation must be ToolObservation")
        for name in ("call_fingerprint", "fingerprint"):
            value = str(getattr(self, name)).strip().lower()
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise AgentContractError(f"{name} must be a sha256 hex fingerprint")
            object.__setattr__(self, name, value)


class PermitBoundToolExecutor:
    """Compose one-time epistemic permits with the existing host ToolExecutor."""

    INTENT_METADATA_KEY = "tool_intent_fingerprint"

    def __init__(
        self,
        authorizer: DecisionAuthorizer,
        executor: ToolExecutor,
    ) -> None:
        if not isinstance(authorizer, DecisionAuthorizer):
            raise TypeError("authorizer must be DecisionAuthorizer")
        if not isinstance(executor, ToolExecutor):
            raise TypeError("executor must be ToolExecutor")
        self.authorizer = authorizer
        self.executor = executor

    def execute(
        self,
        token: AuthorizationToken,
        intent: ToolExecutionIntent,
        call: ToolCall,
        context: ToolExecutionContext,
        *,
        grants: Sequence[ToolGrant],
        expected_policy_fingerprint: str,
    ) -> BoundToolExecution:
        if not isinstance(token, AuthorizationToken):
            raise TypeError("token must be AuthorizationToken")
        if not isinstance(intent, ToolExecutionIntent):
            raise TypeError("intent must be ToolExecutionIntent")
        if not isinstance(call, ToolCall):
            raise TypeError("call must be ToolCall")
        if not isinstance(context, ToolExecutionContext):
            raise TypeError("context must be ToolExecutionContext")

        # Consume first. Any later mismatch intentionally burns the token.
        authorization = self.authorizer.consume(
            token,
            action_id=intent.action_id,
            expected_policy_fingerprint=expected_policy_fingerprint,
        )
        if not authorization.allowed or authorization.permit is None:
            failures = ",".join(item.value for item in authorization.failures) or "denied"
            raise AuthorizedToolDenied(f"epistemic authorization rejected: {failures}")
        permit = authorization.permit

        mismatches = self.binding_mismatches(
            permit=permit,
            intent=intent,
            call=call,
            context=context,
        )
        if mismatches:
            raise AuthorizedToolDenied(
                "execution intent mismatch: " + ", ".join(mismatches)
            )

        observation = self.executor.execute(call, context, grants=grants)
        call_fingerprint = stable_fingerprint(
            {
                "call_id": call.call_id,
                "tool_name": call.name,
                "arguments": call.arguments,
                "user_id": context.user_id,
                "run_id": context.run_id,
                "trace_id": context.trace_id,
            }
        )
        fingerprint = stable_fingerprint(
            {
                "intent": intent.fingerprint,
                "authorization": authorization.fingerprint,
                "permit": permit.permit_fingerprint,
                "call": call_fingerprint,
                "observation": {
                    "call_id": observation.call_id,
                    "tool_name": observation.tool_name,
                    "ok": observation.ok,
                    "payload": observation.payload,
                    "error": observation.error,
                    "evidence": [
                        (
                            ref.evidence_id,
                            ref.fingerprint,
                            ref.confidence,
                        )
                        for ref in observation.evidence
                    ],
                    "cached": observation.cached,
                },
            }
        )
        return BoundToolExecution(
            execution_id=stable_id("bound_execution", {"fingerprint": fingerprint}),
            intent=intent,
            authorization=authorization,
            permit=permit,
            observation=observation,
            call_fingerprint=call_fingerprint,
            fingerprint=fingerprint,
        )

    @classmethod
    def binding_mismatches(
        cls,
        *,
        permit: ExecutionPermit,
        intent: ToolExecutionIntent,
        call: ToolCall,
        context: ToolExecutionContext,
    ) -> tuple[str, ...]:
        mismatches: list[str] = []
        if permit.action.action_id != intent.action_id:
            mismatches.append("action_id")
        bound_fingerprint = permit.action.metadata.get(cls.INTENT_METADATA_KEY)
        if bound_fingerprint != intent.fingerprint:
            mismatches.append("action_intent_fingerprint")
        if intent.call_id != call.call_id:
            mismatches.append("call_id")
        if intent.tool_name != call.name:
            mismatches.append("tool_name")
        if intent.argument_fingerprint != stable_fingerprint(call.arguments):
            mismatches.append("arguments")
        if intent.user_id != context.user_id:
            mismatches.append("user_id")
        if intent.run_id != context.run_id:
            mismatches.append("run_id")
        if intent.trace_id != context.trace_id:
            mismatches.append("trace_id")
        return tuple(mismatches)


def bind_intent_metadata(
    metadata: Mapping[str, Any] | None,
    intent: ToolExecutionIntent,
) -> Mapping[str, Any]:
    """Return validated action metadata carrying an exact tool-intent binding."""

    if not isinstance(intent, ToolExecutionIntent):
        raise TypeError("intent must be ToolExecutionIntent")
    value = dict(metadata or {})
    existing = value.get(PermitBoundToolExecutor.INTENT_METADATA_KEY)
    if existing is not None and existing != intent.fingerprint:
        raise AgentContractError("metadata already binds a different tool intent")
    value[PermitBoundToolExecutor.INTENT_METADATA_KEY] = intent.fingerprint
    value["tool_intent_id"] = intent.intent_id
    value["tool_call_id"] = intent.call_id
    value["tool_name"] = intent.tool_name
    value["tool_argument_fingerprint"] = intent.argument_fingerprint
    value["tool_user_id"] = intent.user_id
    return json_safe(value)
