"""Tokenizer fingerprints from digested inputs and token-id observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class TokenizationSample:
    sample_id: str
    input_digest: str
    character_count: int
    token_ids: tuple[int, ...]
    condition: str = "default"

    def __post_init__(self) -> None:
        if not self.sample_id or not self.condition:
            raise ReverseEngineeringError("tokenization sample identity is required")
        if not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("input_digest must be a sha256 hex digest")
        if self.character_count < 0:
            raise ReverseEngineeringError("character_count must be non-negative")
        if any(token < 0 for token in self.token_ids):
            raise ReverseEngineeringError("token ids must be non-negative")


@dataclass(frozen=True)
class TokenizerFingerprint:
    condition: str
    sample_count: int
    total_characters: int
    total_tokens: int
    unique_token_ids: int
    min_token_id: int | None
    max_token_id: int | None
    mean_characters_per_token: float | None
    empty_tokenization_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "sample_count": self.sample_count,
            "total_characters": self.total_characters,
            "total_tokens": self.total_tokens,
            "unique_token_ids": self.unique_token_ids,
            "min_token_id": self.min_token_id,
            "max_token_id": self.max_token_id,
            "mean_characters_per_token": self.mean_characters_per_token,
            "empty_tokenization_count": self.empty_tokenization_count,
            "digest": self.digest,
        }


def fingerprint_tokenizer(samples: Sequence[TokenizationSample]) -> tuple[TokenizerFingerprint, ...]:
    if not samples:
        raise ReverseEngineeringError("tokenizer fingerprint requires samples")
    grouped: dict[str, list[TokenizationSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.condition, []).append(sample)

    reports: list[TokenizerFingerprint] = []
    for condition, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.sample_id)
        all_ids = [token for item in ordered for token in item.token_ids]
        total_chars = sum(item.character_count for item in ordered)
        total_tokens = len(all_ids)
        payload = {
            "condition": condition,
            "samples": [
                {
                    "sample_id": item.sample_id,
                    "input_digest": item.input_digest,
                    "character_count": item.character_count,
                    "token_ids": list(item.token_ids),
                }
                for item in ordered
            ],
        }
        reports.append(
            TokenizerFingerprint(
                condition=condition,
                sample_count=len(ordered),
                total_characters=total_chars,
                total_tokens=total_tokens,
                unique_token_ids=len(set(all_ids)),
                min_token_id=min(all_ids) if all_ids else None,
                max_token_id=max(all_ids) if all_ids else None,
                mean_characters_per_token=(total_chars / total_tokens if total_tokens else None),
                empty_tokenization_count=sum(1 for item in ordered if not item.token_ids),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
