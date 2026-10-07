"""Optional tiktoken-backed exact token accounting.

This adapter is intentionally narrow: it exposes counting/truncation without
letting provider-specific model objects leak into canonical Skeleton state.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable

from .optional import load_optional
from .registry import source


@dataclass(frozen=True, slots=True)
class TokenCount:
    encoding_name: str
    token_count: int
    character_count: int


class TiktokenTokenizer:
    def __init__(
        self,
        *,
        model: str | None = None,
        encoding_name: str | None = None,
        importer: Callable[[str], object] = import_module,
    ) -> None:
        if bool(model) == bool(encoding_name):
            raise ValueError("provide exactly one of model or encoding_name")
        self.model = model
        self.encoding_name = encoding_name
        self._importer = importer
        self._encoding = None

    def _load_encoding(self):
        if self._encoding is not None:
            return self._encoding
        module = load_optional(source("tiktoken"), "tiktoken", importer=self._importer)
        if self.model is not None:
            encoding = module.encoding_for_model(self.model)
        else:
            encoding = module.get_encoding(self.encoding_name)
        if not hasattr(encoding, "encode") or not hasattr(encoding, "decode"):
            raise TypeError("tiktoken encoding does not implement encode/decode")
        self._encoding = encoding
        return encoding

    def encode(self, text: str, *, allow_special_text: bool = False) -> tuple[int, ...]:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        encoding = self._load_encoding()
        if allow_special_text:
            tokens = encoding.encode(text, disallowed_special=())
        else:
            # Default tiktoken behavior rejects registered special-token text.
            tokens = encoding.encode(text)
        return tuple(int(token) for token in tokens)

    def decode(self, tokens: tuple[int, ...] | list[int]) -> str:
        encoding = self._load_encoding()
        return str(encoding.decode(list(tokens)))

    def count(self, text: str) -> TokenCount:
        tokens = self.encode(text)
        encoding = self._load_encoding()
        name = str(getattr(encoding, "name", self.encoding_name or self.model or "unknown"))
        return TokenCount(
            encoding_name=name,
            token_count=len(tokens),
            character_count=len(text),
        )

    def fits(self, text: str, *, maximum_tokens: int) -> bool:
        if maximum_tokens < 0:
            raise ValueError("maximum_tokens must be non-negative")
        return len(self.encode(text)) <= maximum_tokens

    def truncate(
        self,
        text: str,
        *,
        maximum_tokens: int,
        allow_special_text: bool = False,
    ) -> str:
        if maximum_tokens < 0:
            raise ValueError("maximum_tokens must be non-negative")
        tokens = self.encode(text, allow_special_text=allow_special_text)
        if len(tokens) <= maximum_tokens:
            return text
        if maximum_tokens == 0:
            return ""
        return self.decode(tokens[:maximum_tokens])


__all__ = ["TokenCount", "TiktokenTokenizer"]
