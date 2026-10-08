"""Role-based chat adapter over the executable native LLM runtime.

The adapter uses exact token sequences for inference and explicitly bounds
prompt+completion against model context. It never silently truncates system
instructions and does not persist uncommitted failed generations.
"""
from __future__ import annotations

from dataclasses import dataclass

from .chat_protocol import ChatMessage, ChatTranscript
from .flgb_model_runtime import TokenSequence, digest_json
from .native_llm_runtime import GenerationResult, NativeLLMRuntime
from .runtime_contracts import GenerationConfig, RuntimeContractError


@dataclass(frozen=True)
class ChatTurnResult:
    transcript: ChatTranscript
    generation: GenerationResult
    prompt_tokens: int
    retained_messages: int


class NativeChatEngine:
    def __init__(self, runtime: NativeLLMRuntime, *,
                 max_messages: int = 512, reserve_tokens: int = 1) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise RuntimeContractError("native runtime required")
        if type(max_messages) is not int or not 1 <= max_messages <= 2048:
            raise RuntimeContractError("invalid message capacity")
        if type(reserve_tokens) is not int or reserve_tokens < 1:
            raise RuntimeContractError("invalid generation reserve")
        if reserve_tokens >= runtime.limits.max_context:
            raise RuntimeContractError("reserve exceeds model context")
        self.runtime = runtime
        self.max_messages = max_messages
        self.reserve_tokens = reserve_tokens

    def _token_ids(self, transcript: ChatTranscript) -> tuple[int, ...]:
        return self.runtime.encode(transcript.format_prompt()).token_ids

    def fit(self, transcript: ChatTranscript, config: GenerationConfig) -> ChatTranscript:
        """Remove oldest dialogue messages until the complete request fits."""
        if not isinstance(transcript, ChatTranscript):
            raise RuntimeContractError("chat transcript required")
        if not transcript.messages or transcript.messages[-1].role != "user":
            raise RuntimeContractError("chat generation requires a final user message")
        if not isinstance(config, GenerationConfig):
            raise RuntimeContractError("generation config required")
        transcript.validate_turn_order()
        budget = self.runtime.limits.max_context - max(self.reserve_tokens, config.max_new_tokens)
        if budget < 1:
            raise RuntimeContractError("generation exceeds model context")
        messages = list(transcript.messages)
        while True:
            candidate = ChatTranscript(tuple(messages))
            if len(messages) <= self.max_messages and len(self._token_ids(candidate)) <= budget:
                return candidate
            first_dialogue = next((i for i, m in enumerate(messages)
                                   if m.role not in ("system", "developer")), None)
            if first_dialogue is None:
                raise RuntimeContractError("system instructions exceed model context")
            if first_dialogue == len(messages) - 1:
                raise RuntimeContractError("latest chat message cannot fit model context")
            # Drop an entire oldest dialogue exchange, never leave an orphan reply.
            messages.pop(first_dialogue)
            while first_dialogue < len(messages) and messages[first_dialogue].role in ("assistant", "tool"):
                messages.pop(first_dialogue)
            if not messages:
                raise RuntimeContractError("chat prompt cannot fit model context")

    def preflight(self, transcript: ChatTranscript,
                  config: GenerationConfig) -> dict[str, int]:
        fitted = self.fit(transcript, config)
        ids = self._token_ids(fitted)
        return {"prompt_tokens": len(ids),
                "max_new_tokens": config.max_new_tokens,
                "retained_messages": len(fitted.messages),
                "dropped_messages": len(transcript.messages) - len(fitted.messages),
                "remaining_context": self.runtime.limits.max_context - len(ids)}

    def generate(self, transcript: ChatTranscript,
                 config: GenerationConfig) -> ChatTurnResult:
        fitted = self.fit(transcript, config)
        ids = self._token_ids(fitted)
        if not ids:
            raise RuntimeContractError("empty tokenized chat prompt")
        sequence = TokenSequence(self.runtime.tokenizer.digest, ids,
                                 digest_json({"chat_transcript": fitted.digest()}))
        result = self.runtime.generate_sequence(sequence, config)
        response = fitted.append("assistant", result.text)
        return ChatTurnResult(response, result, len(ids), len(fitted.messages))

    def turn(self, transcript: ChatTranscript, user_text: str,
             config: GenerationConfig) -> ChatTurnResult:
        if not isinstance(user_text, str) or not user_text:
            raise RuntimeContractError("nonempty user message required")
        return self.generate(transcript.append("user", user_text), config)


__all__ = ["NativeChatEngine", "ChatTurnResult"]
