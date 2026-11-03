"""Independent output sanity before applying case-level quality assertions."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import integer, text, sha256
from .errors import deny


@dataclass(frozen=True, slots=True)
class OutputIntegrity:
    utf8_sha256: str
    utf8_bytes: int
    characters: int
    newline_count: int
    replacement_chars: int
    null_count: int
    ends_with_newline: bool

    def record(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


def inspect(text_output: str, *, maximum_bytes: int = 1048576) -> OutputIntegrity:
    text(text_output, "model-output", 262144)
    integer(maximum_bytes, "maximum-bytes", 1, 1048576)
    raw = text_output.encode("utf-8")
    if len(raw) > maximum_bytes:
        deny("output-byte-cap")
    return OutputIntegrity(
        utf8_sha256=sha256(raw), utf8_bytes=len(raw),
        characters=len(text_output), newline_count=text_output.count("\n"),
        replacement_chars=text_output.count("\ufffd"),
        null_count=text_output.count("\x00"),
        ends_with_newline=text_output.endswith("\n"),
    )
