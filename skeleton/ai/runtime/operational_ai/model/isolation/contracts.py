"""Bounded isolation policy; exact model provenance and deadlines."""
from __future__ import annotations
from dataclasses import dataclass
import re

SHA = re.compile(r'^[0-9a-f]{64}$')


class IsolationFailure(RuntimeError):
    """Model execution is unsafe or unqualified; no automatic retry."""


class IsolationUnavailable(IsolationFailure):
    """The process or its custody channel is unusable."""


class IsolationProtocolError(IsolationFailure):
    """The process violated a strict typed protocol contract."""


def digest(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise IsolationProtocolError(f'invalid {label} digest')
    return value


def integer(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise IsolationProtocolError(f'{label} outside allowed bounds')
    return value


@dataclass(frozen=True, slots=True)
class IsolationPolicy:
    context_tokens: int = 2048
    threads: int = 4
    gpu_layers: int = 0
    startup_ms: int = 180000
    inference_ms: int = 120000
    shutdown_ms: int = 2000
    max_frame_bytes: int = 1_048_576
    max_prompts: int = 1024

    def __post_init__(self) -> None:
        integer(self.context_tokens, 'context', 128, 131072)
        integer(self.threads, 'threads', 1, 64)
        integer(self.gpu_layers, 'gpu layers', 0, 256)
        integer(self.startup_ms, 'startup deadline', 100, 600000)
        integer(self.inference_ms, 'inference deadline', 100, 600000)
        integer(self.shutdown_ms, 'shutdown deadline', 0, 30000)
        integer(self.max_frame_bytes, 'IPC bytes', 8192, 2_097_152)
        integer(self.max_prompts, 'prompt messages', 1, 1024)
