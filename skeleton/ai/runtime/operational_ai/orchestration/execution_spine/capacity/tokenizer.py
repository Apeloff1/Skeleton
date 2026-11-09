"""Native tokenizer preflight; no approximate count is called an exact proof."""
from __future__ import annotations
from dataclasses import dataclass
from ..contracts import SpineError, SpineLimits


@dataclass(frozen=True, slots=True)
class TokenAdmission:
    status: str
    prompt_tokens: int | None
    context_ceiling: int
    output_reserve: int

    @property
    def admitted(self) -> bool:
        return (self.prompt_tokens is None or
                self.prompt_tokens + self.output_reserve <= self.context_ceiling)


def check(backend, messages: tuple[dict, ...], limits: SpineLimits,
          *, require_exact: bool = False) -> TokenAdmission:
    if type(require_exact) is not bool:
        raise SpineError('invalid native tokenizer requirement')
    if type(messages) is not tuple or not messages:
        raise SpineError('context candidate must have messages')
    counter = getattr(backend, 'count_tokens', None)
    if counter is None:
        if require_exact:
            raise SpineError('native pre-count required but unavailable')
        return TokenAdmission('native-backend-must-enforce-unknown-precount',
                              None, limits.context_tokens, limits.max_output_tokens)
    if not callable(counter):
        raise SpineError('malformed native token counting capability')
    try:
        counted = counter(list(messages))
    except Exception as exc:
        # A provider error must never be interpreted as legitimate budget
        # overflow and silently cause successive loss of historical context.
        raise SpineError('native tokenizer pre-count failed') from exc
    if type(counted) is not int or counted < 0:
        raise SpineError('invalid backend authored token count')
    if counted + limits.max_output_tokens > limits.context_tokens:
        raise SpineError('exact tokenizer context ceiling exceeded')
    return TokenAdmission('exact-backend-count-admitted', counted,
                          limits.context_tokens, limits.max_output_tokens)
