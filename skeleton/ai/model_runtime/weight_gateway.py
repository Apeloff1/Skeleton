"""Serving gateway that pins each native inference request to one weight revision.

Promotion cannot change the transformer halfway through a request. Requests
created after admission pick up the new runtime, while requests created before
admission retain their original service until completion or cancellation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .flgb_model_runtime import LocalModelRequest, require_digest
from .runtime_contracts import GenerationConfig, RuntimeContractError
from .runtime_service import CancellationToken, NativeModelService, NativeServiceResult

if TYPE_CHECKING:
    from .weight_activation import NativeWeightDeployment


class WeightGatewayError(RuntimeContractError):
    """A serving request is bound to an invalid or missing runtime revision."""


@dataclass(frozen=True, slots=True)
class PinnedWeightRequest:
    """Immutable request+service pair. The service keeps its model resident."""

    request: LocalModelRequest
    service: NativeModelService
    model_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, LocalModelRequest):
            raise WeightGatewayError("pinned request requires LocalModelRequest")
        if not isinstance(self.service, NativeModelService):
            raise WeightGatewayError("pinned request requires native model service")
        require_digest(self.model_digest, "pinned model digest")
        if self.service.runtime.model_digest != self.model_digest:
            raise WeightGatewayError("pinned service uses different weights")
        if self.service.identity_digest != self.request.model_identity_digest:
            raise WeightGatewayError("request identity changed after service admission")


class NativeWeightGateway:
    """Acquire fresh services from the deployment manager at request admission."""

    def __init__(self, deployment: "NativeWeightDeployment") -> None:
        from .weight_activation import NativeWeightDeployment

        if not isinstance(deployment, NativeWeightDeployment):
            raise WeightGatewayError("weight gateway requires native deployment manager")
        self._deployment = deployment

    @property
    def active_model_digest(self) -> str:
        return self._deployment.active_model_digest

    def pin(
        self,
        operation_id: str,
        prompt: str,
        config: GenerationConfig,
        *,
        deadline_ms: int,
    ) -> PinnedWeightRequest:
        service = self._deployment.new_model_service()
        request = service.request(
            operation_id, prompt, config, deadline_ms=deadline_ms,
        )
        return PinnedWeightRequest(
            request=request,
            service=service,
            model_digest=service.runtime.model_digest,
        )

    def execute(
        self,
        pinned: PinnedWeightRequest,
        prompt: str,
        config: GenerationConfig,
        *,
        cancellation: CancellationToken | None = None,
        require_current_weights: bool = False,
    ) -> NativeServiceResult:
        if not isinstance(pinned, PinnedWeightRequest):
            raise WeightGatewayError("execute requires pinned weight request")
        if not isinstance(require_current_weights, bool):
            raise WeightGatewayError("invalid freshness policy")
        if require_current_weights and pinned.model_digest != self.active_model_digest:
            raise WeightGatewayError("request became stale after weight promotion")
        pinned.service.runtime.assert_model_unchanged()
        return pinned.service.execute(
            pinned.request, prompt, config, cancellation=cancellation,
        )

    def run_current(
        self,
        operation_id: str,
        prompt: str,
        config: GenerationConfig,
        *,
        deadline_ms: int,
        cancellation: CancellationToken | None = None,
    ) -> NativeServiceResult:
        pinned = self.pin(
            operation_id, prompt, config, deadline_ms=deadline_ms,
        )
        return self.execute(pinned, prompt, config, cancellation=cancellation)


__all__ = ["WeightGatewayError", "PinnedWeightRequest", "NativeWeightGateway"]
