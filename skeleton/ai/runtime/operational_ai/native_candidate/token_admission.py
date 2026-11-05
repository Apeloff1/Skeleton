"""Token and model vocabulary admission using actual native transformer IDs."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import number
from .errors import deny


@dataclass(frozen=True, slots=True)
class TokenProof:
    lines: int
    total_tokens: int
    known_tokens: int
    unknown_tokens: int
    optimizer_steps_estimate: int
    known_fraction_ppm: int

    def record(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def inspect_lines(model, lines: tuple[str, ...], *,
                  maximum_steps: int, min_known_ppm: int) -> TokenProof:
    number(maximum_steps, "steps", 1, 1000000)
    number(min_known_ppm, "known-floor", 0, 1000000)
    if not callable(getattr(model, "_ids", None)) or not hasattr(model, "unk"):
        deny("native-tokenizer-required")
    if not lines or len(lines) > 576:
        deny("token-input-count")
    known = unknown = steps = 0
    for line in lines:
        if type(line) is not str or len(line.encode("utf-8")) > 16384:
            deny("token-line")
        values = model._ids(line)
        if type(values) not in (list, tuple) or not values or len(values) > 65536:
            deny("token-id-sequence")
        if any(type(token) is not int or token < 0 or token >= len(model.itos)
               for token in values):
            deny("token-id-range")
        missed = sum(token == model.unk for token in values)
        unknown += missed
        known += len(values) - missed
        steps += max(0, len(values) - 1)
        if steps > maximum_steps:
            deny("training-step-budget")
    total = known + unknown
    fraction = (known * 1000000) // total
    if fraction < min_known_ppm:
        deny("tokenizer-vocabulary-incompatible")
    if steps == 0:
        deny("tokenizer-empty-gradient")
    return TokenProof(len(lines), total, known, unknown, steps, fraction)
