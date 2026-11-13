"""Trust-boundary validation of already-authoritative conversation history."""
from __future__ import annotations
from hashlib import sha256
from ..contracts import SpineError, SpineLimits, Identity, canonical
from ..context import Evidence
from .contracts import CapacityPolicy


def validate_history(history: tuple[dict, ...], limits: SpineLimits) -> str:
    if type(history) is not tuple or len(history) % 2 or len(history) > 2 * limits.max_history:
        raise SpineError('invalid history span supplied to context admission')
    for index, item in enumerate(history):
        if type(item) is not dict or set(item) != {'role', 'content'}:
            raise SpineError('malformed history message')
        if item['role'] != ('user' if index % 2 == 0 else 'assistant'):
            raise SpineError('historical role drift')
        content = item['content']
        if not isinstance(content, str) or not content.strip():
            raise SpineError('invalid historical message content')
        # Bounds must apply BEFORE canonical() serializes the entire history.
        if len(content.encode('utf8', errors='strict')) > limits.response_bytes:
            raise SpineError('history entry exceeds source size ceiling')
    raw = canonical(history, ceiling=16_777_216)
    return sha256(raw).hexdigest()


def validate_sources(identity: Identity, evidence: tuple[Evidence, ...],
                     policy: CapacityPolicy) -> str:
    if type(evidence) is not tuple or len(evidence) > policy.max_source_candidates:
        raise SpineError('unbounded candidate evidence')
    fingerprints: set[tuple[str, int]] = set()
    source_ids: set[str] = set()
    for item in evidence:
        if not isinstance(item, Evidence):
            raise SpineError('invalid source evidence object')
        if item.owner_tenant != identity.tenant or item.owner_subject != identity.subject:
            raise SpineError('source principal mismatch')
        identity_key = (item.source_id, item.revision)
        if identity_key in fingerprints or item.source_id in source_ids:
            raise SpineError('duplicate or revision-conflicting evidence source')
        fingerprints.add(identity_key)
        source_ids.add(item.source_id)
    return sha256(canonical([{
        'source': item.source_id, 'revision': item.revision, 'passage_sha256': item.sha256,
        'document_sha256': item.document_sha256, 'owner': identity.key(),
    } for item in evidence], ceiling=1_048_576)).hexdigest()


def bounded_sources(source, policy: CapacityPolicy) -> tuple[Evidence, ...]:
    """Consume a capped iterable once; reject rather than silently ignoring tail."""
    result = []
    iterator = iter(source)
    for index, item in enumerate(iterator):
        if index == policy.max_source_candidates:
            raise SpineError('candidate evidence exceeds finite source ceiling')
        result.append(item)
    return tuple(result)
