"""Typed, non-secret retry instructions for Dragon Family source adapters.

Trusted host transport policies convert HTTP/network/rights outcomes into
these bounded exceptions. Raw exception text, redirect targets, credentials,
headers and response bodies are never persisted in the Dragon Nest journal.
The family itself never performs HTTP, bypasses provider controls or decides
whether an unlicensed source is safe.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class IdleResearchFailure(Exception):
    category: str
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.category not in ("policy_blocked","rate_limited","transient"):
            raise ValueError("unrecognized host research failure")
        delay=self.retry_after_seconds
        if delay is not None and (
                type(delay) not in (int,float) or not isfinite(delay)
                or not 60<=delay<=86400):
            raise ValueError("untrusted or unbounded source Retry-After")
        if self.category!="rate_limited" and delay is not None:
            raise ValueError("only rate-limited research accepts Retry-After")

    def __str__(self) -> str:
        return self.category


def source_policy_denied() -> IdleResearchFailure:
    """License, robots, destination, media grant or human-review hard denial."""
    return IdleResearchFailure("policy_blocked")


def source_rate_limited(retry_after_seconds: float) -> IdleResearchFailure:
    """Provider Retry-After without forwarding headers or source secrets."""
    return IdleResearchFailure("rate_limited",retry_after_seconds)


def source_transport_failed() -> IdleResearchFailure:
    """Temporary network failure; bounded exponential retry still applies."""
    return IdleResearchFailure("transient")
