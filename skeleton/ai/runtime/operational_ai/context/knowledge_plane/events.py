"""Hash-chained append-only mutation receipts sharing the spine transaction."""
from __future__ import annotations
import json
from hashlib import sha256
from .contracts import KnowledgeError
from ...orchestration.execution_spine.contracts import canonical
from ...orchestration.execution_spine.outbox import emit

ZERO = '0' * 64
MAX_EVENTS = 65536


def inspect(conn, principal: str, *, limit: int = MAX_EVENTS) -> tuple[dict, ...]:
    if type(limit) is not int or not 1 <= limit <= MAX_EVENTS:
        raise KnowledgeError('invalid history scan ceiling')
    rows = conn.execute('SELECT ordinal,event_json,event_sha256,previous_sha256 '
                        'FROM ai_kb_events WHERE principal=? ORDER BY ordinal LIMIT ?',
                        (principal, limit+1)).fetchall()
    if len(rows) > limit:
        raise KnowledgeError('knowledge mutation log exceeds verification budget')
    result, previous = [], ZERO
    for ordinal, raw, recorded, prior in rows:
        if (type(raw) is not bytes or type(ordinal) is not int
            or ordinal != len(result) + 1 or prior != previous
            or sha256(raw).hexdigest() != recorded):
            raise KnowledgeError('knowledge mutation chain damaged')
        try:
            data = json.loads(raw)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise KnowledgeError('knowledge mutation JSON damaged') from exc
        if (canonical(data) != raw or data.get('principal') != principal
            or data.get('ordinal') != ordinal or data.get('previous_sha256') != previous
            or data.get('schema') != 'skeleton.ai.knowledge-event.v1'
            or data.get('action') not in ('ingested', 'forgotten', 'index-rebuilt')):
            raise KnowledgeError('knowledge mutation event identity mismatch')
        key = 'kb_' + sha256(f'{principal}:{ordinal}'.encode('ascii')).hexdigest()
        outbox = conn.execute('SELECT stream,kind,event_json,event_sha256 FROM outbox '
                              'WHERE event_key=?', (key,)).fetchone()
        if (outbox is None or outbox[0] != principal or outbox[1] != 'ai_knowledge'
            or outbox[2] != raw or outbox[3] != recorded):
            raise KnowledgeError('knowledge audit and transactional outbox disagree')
        result.append(data | {'event_sha256':recorded})
        previous = recorded
    return tuple(result)


def append(conn, principal: str, *, action: str, doc_id: str, revision: int,
           raw_sha256: str, normalized_sha256: str, chunks: int) -> dict:
    if action not in ('ingested', 'forgotten', 'index-rebuilt'):
        raise KnowledgeError('unknown knowledge mutation')
    events = inspect(conn, principal)
    if len(events) >= MAX_EVENTS:
        raise KnowledgeError('knowledge mutation ledger reached its bound')
    ordinal = len(events) + 1
    previous = events[-1]['event_sha256'] if events else ZERO
    document = {'schema':'skeleton.ai.knowledge-event.v1', 'principal':principal,
        'ordinal':ordinal, 'previous_sha256':previous, 'action':action,
        'doc_id':doc_id, 'revision':revision, 'raw_sha256':raw_sha256,
        'normalized_sha256':normalized_sha256, 'chunks':chunks}
    # Hash is OUTSIDE of the canonical object (no recursive fixed point).
    raw = canonical(document)
    record_sha = sha256(raw).hexdigest()
    conn.execute('INSERT INTO ai_kb_events VALUES(?,?,?,?,?)',
                 (principal, ordinal, raw, record_sha, previous))
    key = 'kb_' + sha256(f'{principal}:{ordinal}'.encode('ascii')).hexdigest()
    emit(conn, key, principal, 'ai_knowledge', document)
    return document | {'event_sha256':record_sha}
