"""Fail-closed request filters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class FilterVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    CHALLENGE = "challenge"


@dataclass(frozen=True)
class FilterResult:
    verdict: FilterVerdict
    reason: str
    filter_name: str

    def as_dict(self) -> Dict[str, str]:
        return {"verdict": self.verdict.value, "reason": self.reason, "filter": self.filter_name}


@dataclass
class FilterChain:
    name: str
    max_header_bytes: int = 16_384
    max_body_bytes: int = 1_048_576
    block_empty_ua: bool = False

    def check_headers(self, headers: Dict[str, str]) -> FilterResult:
        raw = sum(len(k) + len(v) for k, v in headers.items())
        if raw > self.max_header_bytes:
            return FilterResult(FilterVerdict.DENY, "headers_too_large", self.name)
        if self.block_empty_ua and not headers.get("user-agent"):
            return FilterResult(FilterVerdict.CHALLENGE, "missing_ua", self.name)
        return FilterResult(FilterVerdict.ALLOW, "ok", self.name)

    def check_body_len(self, content_length: Optional[int]) -> FilterResult:
        if content_length is None:
            return FilterResult(FilterVerdict.ALLOW, "unknown_length", self.name)
        if content_length > self.max_body_bytes:
            return FilterResult(FilterVerdict.DENY, "body_too_large", self.name)
        return FilterResult(FilterVerdict.ALLOW, "ok", self.name)


def run_filters(
    chain: FilterChain,
    *,
    headers: Dict[str, str],
    content_length: Optional[int] = None,
) -> FilterResult:
    h = chain.check_headers(headers)
    if h.verdict is not FilterVerdict.ALLOW:
        return h
    return chain.check_body_len(content_length)

def filter_chain_forge() -> FilterChain:
    return FilterChain(name="forge", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_forge_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_forge().check_headers(headers)

def filter_forge_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_forge().check_body_len(content_length)

def filter_chain_gameforge() -> FilterChain:
    return FilterChain(name="gameforge", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_gameforge_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_gameforge().check_headers(headers)

def filter_gameforge_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_gameforge().check_body_len(content_length)

def filter_chain_swarm() -> FilterChain:
    return FilterChain(name="swarm", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_swarm_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_swarm().check_headers(headers)

def filter_swarm_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_swarm().check_body_len(content_length)

def filter_chain_jeeves() -> FilterChain:
    return FilterChain(name="jeeves", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_jeeves_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_jeeves().check_headers(headers)

def filter_jeeves_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_jeeves().check_body_len(content_length)

def filter_chain_memory() -> FilterChain:
    return FilterChain(name="memory", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_memory_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_memory().check_headers(headers)

def filter_memory_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_memory().check_body_len(content_length)

def filter_chain_retrieval() -> FilterChain:
    return FilterChain(name="retrieval", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_retrieval_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_retrieval().check_headers(headers)

def filter_retrieval_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_retrieval().check_body_len(content_length)

def filter_chain_pipeline() -> FilterChain:
    return FilterChain(name="pipeline", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_pipeline_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_pipeline().check_headers(headers)

def filter_pipeline_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_pipeline().check_body_len(content_length)

def filter_chain_intelligence() -> FilterChain:
    return FilterChain(name="intelligence", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_intelligence_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_intelligence().check_headers(headers)

def filter_intelligence_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_intelligence().check_body_len(content_length)

def filter_chain_resilience() -> FilterChain:
    return FilterChain(name="resilience", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_resilience_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_resilience().check_headers(headers)

def filter_resilience_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_resilience().check_body_len(content_length)

def filter_chain_context() -> FilterChain:
    return FilterChain(name="context", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_context_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_context().check_headers(headers)

def filter_context_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_context().check_body_len(content_length)

def filter_chain_ledger() -> FilterChain:
    return FilterChain(name="ledger", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_ledger_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_ledger().check_headers(headers)

def filter_ledger_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_ledger().check_body_len(content_length)

def filter_chain_scheduler() -> FilterChain:
    return FilterChain(name="scheduler", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_scheduler_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_scheduler().check_headers(headers)

def filter_scheduler_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_scheduler().check_body_len(content_length)

def filter_chain_genesis() -> FilterChain:
    return FilterChain(name="genesis", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_genesis_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_genesis().check_headers(headers)

def filter_genesis_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_genesis().check_body_len(content_length)

def filter_chain_capabilities() -> FilterChain:
    return FilterChain(name="capabilities", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_capabilities_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_capabilities().check_headers(headers)

def filter_capabilities_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_capabilities().check_body_len(content_length)

def filter_chain_interface() -> FilterChain:
    return FilterChain(name="interface", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_interface_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_interface().check_headers(headers)

def filter_interface_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_interface().check_body_len(content_length)

def filter_chain_auth() -> FilterChain:
    return FilterChain(name="auth", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_auth_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_auth().check_headers(headers)

def filter_auth_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_auth().check_body_len(content_length)

def filter_chain_cognition() -> FilterChain:
    return FilterChain(name="cognition", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_cognition_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_cognition().check_headers(headers)

def filter_cognition_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_cognition().check_body_len(content_length)

def filter_chain_fabric() -> FilterChain:
    return FilterChain(name="fabric", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_fabric_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_fabric().check_headers(headers)

def filter_fabric_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_fabric().check_body_len(content_length)

def filter_chain_legions() -> FilterChain:
    return FilterChain(name="legions", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_legions_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_legions().check_headers(headers)

def filter_legions_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_legions().check_body_len(content_length)

def filter_chain_governance() -> FilterChain:
    return FilterChain(name="governance", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_governance_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_governance().check_headers(headers)

def filter_governance_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_governance().check_body_len(content_length)

def filter_chain_lafs() -> FilterChain:
    return FilterChain(name="lafs", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_lafs_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_lafs().check_headers(headers)

def filter_lafs_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_lafs().check_body_len(content_length)

def filter_chain_studio() -> FilterChain:
    return FilterChain(name="studio", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_studio_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_studio().check_headers(headers)

def filter_studio_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_studio().check_body_len(content_length)

def filter_chain_court() -> FilterChain:
    return FilterChain(name="court", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_court_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_court().check_headers(headers)

def filter_court_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_court().check_body_len(content_length)

def filter_chain_treasury() -> FilterChain:
    return FilterChain(name="treasury", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_treasury_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_treasury().check_headers(headers)

def filter_treasury_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_treasury().check_body_len(content_length)

def filter_chain_reputation() -> FilterChain:
    return FilterChain(name="reputation", max_header_bytes=16_384, max_body_bytes=1_048_576)

def filter_reputation_headers(headers: Dict[str, str]) -> FilterResult:
    return filter_chain_reputation().check_headers(headers)

def filter_reputation_body(content_length: Optional[int]) -> FilterResult:
    return filter_chain_reputation().check_body_len(content_length)

