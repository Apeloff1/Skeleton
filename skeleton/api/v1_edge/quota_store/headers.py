"""Client-facing quota headers.

Follows the IETF ``RateLimit`` header fields draft in its widely deployed
form — separate ``RateLimit-Limit``, ``RateLimit-Remaining`` and
``RateLimit-Reset`` (delta seconds) — plus ``RateLimit-Policy`` listing every
bucket the request was charged against, and ``Retry-After`` on 429/503.

When several buckets apply, the *most restrictive* one (fewest remaining
tokens, then longest reset) is what Limit/Remaining/Reset describe, since
that is the one the client will hit first.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Tuple

from .policy import Bucket
from .store import TakeResult

H_LIMIT = "ratelimit-limit"
H_REMAINING = "ratelimit-remaining"
H_RESET = "ratelimit-reset"
H_POLICY = "ratelimit-policy"
H_RETRY_AFTER = "retry-after"
H_SCOPE = "x-ratelimit-scope"

MAX_RETRY_AFTER_S = 86_400


def ceil_s(seconds: float) -> int:
    if not math.isfinite(seconds):
        return MAX_RETRY_AFTER_S
    return min(MAX_RETRY_AFTER_S, max(0, int(math.ceil(seconds - 1e-9))))


def retry_after_value(seconds: float) -> str:
    return str(max(1, ceil_s(seconds)))


def most_restrictive(pairs: Iterable[Tuple[Bucket, TakeResult]]) -> Optional[Tuple[Bucket, TakeResult]]:
    best = None
    for b, r in pairs:
        if best is None:
            best = (b, r)
            continue
        _, br = best
        if (r.remaining_int, -r.reset_after_s) < (br.remaining_int, -br.reset_after_s):
            best = (b, r)
    return best


def policy_value(pairs: Iterable[Tuple[Bucket, TakeResult]]) -> str:
    items: List[str] = []
    for b, _ in pairs:
        items.append(f'"{b.scope}";q={b.limit.burst};w={b.limit.window_s}')
    return ", ".join(items)


def quota_headers(pairs: List[Tuple[Bucket, TakeResult]]) -> Dict[str, str]:
    pick = most_restrictive(pairs)
    if pick is None:
        return {}
    b, r = pick
    return {
        H_LIMIT: str(b.limit.burst),
        H_REMAINING: str(r.remaining_int),
        H_RESET: str(ceil_s(r.reset_after_s)),
        H_POLICY: policy_value(pairs),
    }


def denial_headers(pairs: List[Tuple[Bucket, TakeResult]], denied: Tuple[Bucket, TakeResult]) -> Dict[str, str]:
    b, r = denied
    hdrs = quota_headers(pairs)
    hdrs[H_LIMIT] = str(b.limit.burst)
    hdrs[H_REMAINING] = "0"
    hdrs[H_RESET] = str(max(1, ceil_s(max(r.retry_after_s, 0.0))))
    hdrs[H_RETRY_AFTER] = retry_after_value(r.retry_after_s)
    hdrs[H_SCOPE] = b.scope
    return hdrs


def merge_legacy(legacy: Dict[str, str], new: Dict[str, str]) -> Dict[str, str]:
    """Merge headers from the v1 edge's own TenantQuotas with distributed ones.

    Legacy-only headers (``x-quota-remaining`` for rolling windows) pass
    through; for the shared RateLimit fields the lower remaining wins.
    """
    out = dict(legacy)
    if not new:
        return out
    try:
        legacy_rem = int(legacy.get(H_REMAINING, "")) if H_REMAINING in legacy else None
    except ValueError:
        legacy_rem = None
    new_rem = int(new.get(H_REMAINING, "0"))
    if legacy_rem is None or new_rem <= legacy_rem:
        out.update(new)
    else:
        for k, v in new.items():
            if k not in (H_LIMIT, H_REMAINING, H_RESET):
                out[k] = v
    return out
