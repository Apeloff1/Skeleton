"""Bounded, deterministic crawl-trap circuit for *already admitted* URLs.

This gate can only veto discovered URLs; it never adds a source, changes
hosts, issues a request, relaxes robots, changes the immutable CrawlPolicy
or grants rights. It operates on the current canonical run's seen/frontier
identities, so snapshot replay gives identical decisions without new state.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from .frontier_antichain import vet_url_antichain

_MAX_SEEN=512
_MAX_FAMILY_VARIANTS=24
_MAX_QUERY_PAIRS=32
_MAX_URL_BYTES=4096
_REPEATED_SEGMENT_LIMIT=4
_SENSITIVE_KEYS=frozenset({
    "token","access_token","refresh_token","id_token","api_key","apikey",
    "authorization","auth","password","passwd","secret","session",
    "sessionid","session_id","sid","jwt","client_secret","signature",
    "x-amz-signature","x-goog-signature","private_key","credential",
})
_SENSITIVE_PATTERN=re.compile(
    r"(?i)(?:^|[_-])(?:api[_-]?key|token|secret|password|passwd|"
    r"authorization|credential|session|signature|bearer)(?:$|[_-])"
)
_DIGITS=re.compile(r"^[0-9]{1,20}$")
_HEX_ID=re.compile(r"^(?:[a-f0-9]{16,64}|[a-f0-9]{8}-[a-f0-9-]{27,})$",re.I)
_QUERY_PAGE_KEYS=frozenset({"page","p","offset","start","index","cursorpage"})
_PAGE_MAX=1_000_000


@dataclass(frozen=True)
class FrontierCircuitDecision:
    allowed:bool
    reason:str
    family_digest:str
    family_variants:int
    max_variants:int
    existing_authority_required:bool=True
    network_executed:bool=False


def _family(url:str)->tuple[str,tuple[str,...]]:
    split=urlsplit(url)
    sections=[]
    for segment in split.path.split("/"):
        label=unquote(segment).casefold()
        if _DIGITS.fullmatch(label) or _HEX_ID.fullmatch(label):
            sections.append("{id}")
        else:
            sections.append(label)
    query=tuple(sorted(k.casefold() for k,_ in parse_qsl(
        split.query,keep_blank_values=True,max_num_fields=_MAX_QUERY_PAIRS,
    )))
    key=f"{split.scheme}://{split.netloc}/"+"/".join(sections)
    return key,query


def _fingerprint(family:tuple[str,tuple[str,...]])->str:
    return hashlib.sha256(
        (family[0]+"?"+",".join(family[1])).encode("utf-8")
    ).hexdigest()


def _hazard(url:str)->str|None:
    parsed=urlsplit(url)
    if (parsed.scheme not in ("http","https") or not parsed.hostname
            or len(url.encode("utf-8"))>_MAX_URL_BYTES):
        return "unapproved_or_oversized_url"
    segments=[unquote(x).casefold() for x in parsed.path.split("/") if x]
    repeats=Counter(segments)
    if any(repeats[x]>_REPEATED_SEGMENT_LIMIT for x in repeats):
        return "repeated_path_segment_trap"
    try:
        pairs=parse_qsl(parsed.query,keep_blank_values=True,max_num_fields=_MAX_QUERY_PAIRS)
    except ValueError:
        return "query_pair_capacity_exceeded"
    for key,value in pairs:
        key=key.strip().casefold()
        if not key or key in _SENSITIVE_KEYS or _SENSITIVE_PATTERN.search(key):
            return "credential_or_unbounded_query_key"
        if key in _QUERY_PAGE_KEYS and value.isdecimal():
            try:
                number=int(value)
            except ValueError:
                return "pagination_numeric_value_invalid"
            if number>_PAGE_MAX:
                return "pagination_numeric_trap"
    if len(set(k.casefold() for k,_ in pairs))>24:
        return "faceted_query_key_trap"
    return None


def evaluate_frontier_candidate(
    candidate:str,*,seen:tuple[str,...]|list[str],
    frontier:tuple[str,...]|list[str],max_variants:int=_MAX_FAMILY_VARIANTS,
)->FrontierCircuitDecision:
    if (not isinstance(candidate,str) or not isinstance(seen,(tuple,list))
            or not isinstance(frontier,(tuple,list))
            or len(seen)>_MAX_SEEN or len(frontier)>_MAX_SEEN
            or type(max_variants) is not int
            or not 1<=max_variants<=_MAX_FAMILY_VARIANTS):
        raise ValueError("invalid crawl-trap circuit source inputs")
    hazard=_hazard(candidate)
    if hazard:
        return FrontierCircuitDecision(
            False,hazard,_fingerprint((candidate[:4096],())),0,max_variants,
        )
    antichain = vet_url_antichain(candidate, seen=seen, frontier=frontier)
    if not antichain.allowed:
        return FrontierCircuitDecision(
            False, antichain.reason, antichain.structural_digest,
            antichain.known_path_variants, max_variants,
        )
    family=_family(candidate)
    identity=_fingerprint(family)
    # The snapshot owns every existing identity. Only the canonical URL
    # family is counted; text, page instructions and arbitrary model scores
    # have no effect on permission, identity or request billing.
    existing=set()
    for raw in (*seen,*frontier):
        if not isinstance(raw,str):
            raise ValueError("non-URL canonical frontier entry")
        if _family(raw)==family:
            existing.add(raw)
    variants=len(existing)
    if candidate in existing:
        return FrontierCircuitDecision(
            False,"exact_url_already_known",identity,variants,max_variants,
        )
    if variants>=max_variants:
        return FrontierCircuitDecision(
            False,"family_variant_circuit_open",identity,variants,max_variants,
        )
    return FrontierCircuitDecision(
        True,"bounded_new_candidate",identity,variants,max_variants,
    )
