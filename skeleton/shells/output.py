"""Bounded output views for command consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from skeleton.shells.redaction import SecretRedactor
from skeleton.shells.runner import ShellResult


@dataclass(frozen=True)
class OutputView:
    text: str
    original_bytes: int
    rendered_chars: int
    truncated: bool
    stream: str

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "original_bytes": self.original_bytes,
            "rendered_chars": self.rendered_chars,
            "truncated": self.truncated,
            "stream": self.stream,
        }


def render_output(
    result: ShellResult,
    *,
    stream: Literal["stdout", "stderr"] = "stdout",
    encoding: str = "utf-8",
    max_chars: int = 16_384,
    mode: Literal["head", "tail"] = "tail",
    redactor: SecretRedactor | None = None,
) -> OutputView:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    raw = result.stdout if stream == "stdout" else result.stderr
    text = raw.decode(encoding, errors="replace")
    cleaned = (redactor or SecretRedactor()).redact_text(text)
    truncated = len(cleaned) > max_chars
    if truncated:
        if mode == "head":
            rendered = cleaned[:max_chars]
        elif mode == "tail":
            rendered = cleaned[-max_chars:]
        else:
            raise ValueError("mode must be head or tail")
    else:
        rendered = cleaned
    return OutputView(rendered, len(raw), len(rendered), truncated, stream)


def combined_summary(
    result: ShellResult,
    *,
    max_chars_per_stream: int = 4096,
    redactor: SecretRedactor | None = None,
) -> dict[str, object]:
    scrubber = redactor or SecretRedactor()
    stdout = render_output(result, stream="stdout", max_chars=max_chars_per_stream, redactor=scrubber)
    stderr = render_output(result, stream="stderr", max_chars=max_chars_per_stream, redactor=scrubber)
    return {
        "returncode": result.returncode,
        "ok": result.ok,
        "timed_out": result.timed_out,
        "output_limited": result.output_limited,
        "stdout": stdout.to_dict(),
        "stderr": stderr.to_dict(),
    }
