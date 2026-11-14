"""Native-tokenizer contract; never infer exact token count from bytes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .contracts import require_text, strict_integer
from .errors import deny
from .model_pins import require_sha256


@dataclass(frozen=True, slots=True)
class TokenAdmission:
    prompt_tokens: int
    output_reserved: int
    context_limit: int
    available_margin: int


class NativeTokenFence:
    """A caller-provided, verified native tokenizer must supply exact counts."""

    def __init__(
        self,
        *,
        model_sha256: str,
        tokenizer_sha256: str,
        counter: Callable[[str], int],
        max_context: int,
    ) -> None:
        require_sha256(model_sha256)
        require_sha256(tokenizer_sha256)
        if not callable(counter):
            deny("tokenizer-required")
        self.model_sha256 = model_sha256
        self.tokenizer_sha256 = tokenizer_sha256
        self.counter = counter
        self.max_context = strict_integer(
            max_context, minimum=64, maximum=262144, field="token-context"
        )

    def reserve(
        self,
        prompt: str,
        *,
        model_sha256: str,
        tokenizer_sha256: str,
        output_tokens: int,
        system_reserve: int = 0,
    ) -> TokenAdmission:
        require_text(prompt, maximum=32768, field="prompt")
        if model_sha256 != self.model_sha256 or tokenizer_sha256 != self.tokenizer_sha256:
            deny("tokenizer-identity")
        strict_integer(output_tokens, minimum=1, maximum=32768, field="output-reserve")
        strict_integer(system_reserve, minimum=0, maximum=32768, field="system-reserve")
        tokens = self.counter(prompt)
        if type(tokens) is not int or not 0 <= tokens <= 262144:
            deny("tokenizer-result")
        margin = self.max_context - tokens - output_tokens - system_reserve
        if margin < 0:
            deny("tokenizer-capacity")
        return TokenAdmission(tokens, output_tokens, self.max_context, margin)
