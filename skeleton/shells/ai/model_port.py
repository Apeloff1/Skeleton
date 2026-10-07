"""Provider-neutral model port for shell planning and critique."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Protocol, runtime_checkable

from skeleton.shells.ai.protocol import AIModelRequest, AIModelResponse, parse_model_response


class ModelPrivacyBoundary(str, Enum):
    """Maximum data boundary a model/provider may receive."""

    LOCAL = "local"
    PRIVATE_REMOTE = "private_remote"
    EXTERNAL = "external"

    @property
    def rank(self) -> int:
        return {
            ModelPrivacyBoundary.LOCAL: 0,
            ModelPrivacyBoundary.PRIVATE_REMOTE: 1,
            ModelPrivacyBoundary.EXTERNAL: 2,
        }[self]


@dataclass(frozen=True)
class ModelCapabilities:
    structured_output: bool = True
    tool_use: bool = True
    critique: bool = False
    parallel_candidates: bool = False
    max_input_bytes: int = 2 * 1024 * 1024
    max_output_bytes: int = 2 * 1024 * 1024
    privacy_boundary: ModelPrivacyBoundary = ModelPrivacyBoundary.EXTERNAL

    def __post_init__(self) -> None:
        if self.max_input_bytes <= 0 or self.max_output_bytes <= 0:
            raise ValueError("model byte limits must be positive")
        object.__setattr__(
            self,
            "privacy_boundary",
            ModelPrivacyBoundary(self.privacy_boundary),
        )


@runtime_checkable
class AIModelPort(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def capabilities(self) -> ModelCapabilities: ...

    def propose(self, request: AIModelRequest) -> AIModelResponse: ...

    def critique(
        self,
        request: AIModelRequest,
        response: AIModelResponse,
    ) -> Mapping[str, object]: ...


class CallableAIModelPort:
    """Adapter for local or external model callables."""

    def __init__(
        self,
        model_id: str,
        proposer: Callable[[AIModelRequest], AIModelResponse | Mapping[str, object] | str | bytes],
        *,
        critic: Callable[[AIModelRequest, AIModelResponse], Mapping[str, object]] | None = None,
        capabilities: ModelCapabilities | None = None,
    ) -> None:
        if not model_id or len(model_id) > 256:
            raise ValueError("invalid model_id")
        if not callable(proposer):
            raise TypeError("proposer must be callable")
        if critic is not None and not callable(critic):
            raise TypeError("critic must be callable")
        self._model_id = model_id
        self._proposer = proposer
        self._critic = critic
        self._capabilities = capabilities or ModelCapabilities(critique=critic is not None)

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def propose(self, request: AIModelRequest) -> AIModelResponse:
        raw = self._proposer(request)
        response = raw if isinstance(raw, AIModelResponse) else parse_model_response(raw)
        if response.request_id != request.request_id:
            raise ValueError("model response request_id mismatch")
        if response.proposal.intent_id != request.intent.intent_id:
            raise ValueError("model proposal intent_id mismatch")
        return response

    def critique(
        self,
        request: AIModelRequest,
        response: AIModelResponse,
    ) -> Mapping[str, object]:
        if self._critic is None:
            return {}
        raw = self._critic(request, response)
        if not isinstance(raw, Mapping):
            raise TypeError("critic must return a mapping")
        return dict(raw)
