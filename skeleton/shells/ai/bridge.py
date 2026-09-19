"""Bridge Jeeves IntelligenceOrchestrator reasoning into the shell AI model port."""

from __future__ import annotations

from typing import Mapping

from skeleton.intelligence.orchestrator import IntelligenceOrchestrator
from skeleton.shells.ai.model_port import AIModelPort, ModelCapabilities
from skeleton.shells.ai.protocol import AIModelRequest, AIModelResponse, parse_model_response


class JeevesShellModelPort:
    """Use a Jeeves reasoning capability as a structured shell planner.

    The intelligence layer sees only the bounded request dictionary and redacted
    tool cards. Its output must still pass the shell AI protocol parser.
    """

    def __init__(
        self,
        orchestrator: IntelligenceOrchestrator,
        *,
        model_id: str = "jeeves-intelligence",
        min_confidence: float = 0.0,
    ) -> None:
        if not model_id or len(model_id) > 256:
            raise ValueError("invalid Jeeves shell model_id")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence out of range")
        self.orchestrator = orchestrator
        self._model_id = model_id
        self.min_confidence = min_confidence
        self._capabilities = ModelCapabilities(
            structured_output=True,
            tool_use=True,
            critique=False,
            parallel_candidates=False,
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def propose(self, request: AIModelRequest) -> AIModelResponse:
        result = self.orchestrator.reason(
            "Produce a structured shell plan matching the supplied AI shell protocol.",
            {
                "shell_ai_request": request.to_dict(),
                "response_contract": "AIModelResponse protocol version 1",
                "no_raw_shell": True,
            },
            min_confidence=self.min_confidence,
            selection_mode="best_confidence",
            use_cache=False,
        )
        answer = result.get("answer")
        if isinstance(answer, AIModelResponse):
            response = answer
        elif isinstance(answer, (Mapping, str, bytes)):
            response = parse_model_response(answer)
        else:
            raise TypeError("Jeeves shell planner must return structured model response data")
        if response.request_id != request.request_id:
            raise ValueError("Jeeves shell response request_id mismatch")
        return response

    def critique(
        self,
        request: AIModelRequest,
        response: AIModelResponse,
    ) -> Mapping[str, object]:
        return {}
