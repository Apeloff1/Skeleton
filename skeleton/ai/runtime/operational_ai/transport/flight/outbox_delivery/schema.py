"""Closed, privacy-preserving schemas for externally visible *local* AI events.

The spool is a trust boundary. A generic denylist is not sufficient to keep
future database fields from silently exporting private model/user text.
Exact field sets and types must be reviewed when the upstream event evolves.
"""
from __future__ import annotations
import re
from .contracts import DeliveryHeld, digest, event_id

_BOOT = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
FLIGHT_FIELDS = {
    'submitted': {'principal', 'request_sha256', 'priority'},
    'claimed': {'worker', 'fence', 'boot'},
    'model-started': {'fence', 'worker'},
    'heartbeat': {'fence', 'worker'},
    'completed': {'receipt_sha256'},
    'held': {'reason', 'fence'},
    'cancel-requested': {'fence'},
    'cancelled': {'fence'},
    'unstarted-requeued': {'previous_fence'},
    'receipt-recovered': {'receipt_sha256'},
    'uncertain-held': {'previous_fence'},
}
_TURN = {'schema','session','request_id','revision','request_sha256',
         'output_sha256','model_sha256','tokenizer_sha256','prompt_tokens',
         'generated_tokens','finish_reason','principal','context_sha256',
         'omitted_turns','evidence_refs'}
_CAPACITY = {'schema','projection_sha256','history_sha256','candidate_evidence_sha256',
             'selected_evidence_sha256','retained_turns','omitted_turns',
             'evidence_candidates','retained_sources','omitted_sources',
             'planning_trials','token_admission','native_prompt_tokens',
             'conservative_estimated_tokens','proof_sha256'}

def _integer(value, maximum=2**63-1):
    if type(value) is not int or value < 0 or value > maximum:
        raise DeliveryHeld('outbound AI metric is not a bounded unsigned integer')
    return value


def _safe_principal(value):
    # Principal is derived by an authoritative owner-bound Identity, not an
    # arbitrary nickname. It is not a cryptographic authentication signature.
    if not isinstance(value,str) or not 1 <= len(value) <= 1024 or any(ord(c)<33 or ord(c)>126 for c in value):
        raise DeliveryHeld('invalid outbound principal binding')


def _flight(payload:dict)->None:
    if set(payload) != {'schema','job_id','ordinal','kind','fields','prior_digest'} or payload['schema']!='skeleton.ai.flight-event.v1':
        raise DeliveryHeld('unknown flight event schema; export not approved')
    event_id(payload['job_id']);_integer(payload['ordinal']);digest(payload['prior_digest'])
    if payload['ordinal'] < 1:
        raise DeliveryHeld('flight transition requires positive ordinal')
    kind=payload['kind']
    if type(kind) is not str or kind not in FLIGHT_FIELDS:
        raise DeliveryHeld('unknown flight event transition')
    fields=payload['fields']
    if type(fields) is not dict or set(fields)!=FLIGHT_FIELDS[kind]:
        raise DeliveryHeld('flight transition field change requires privacy review')
    for name,value in fields.items():
        if name in ('worker','reason'):
            event_id(value)
        elif name == 'principal':
            _safe_principal(value)
        elif name in ('request_sha256','receipt_sha256'):
            digest(value)
        elif name == 'boot':
            if type(value) is not str or _BOOT.fullmatch(value) is None:
                raise DeliveryHeld('invalid flight boot fence')
        elif name == 'priority':
            _integer(value,9)
        else:
            _integer(value)


def _capacity(record:dict)->None:
    if type(record) is not dict or set(record) != _CAPACITY or record['schema']!='skeleton.ai.context-capacity.v1':
        raise DeliveryHeld('unreviewed context capacity schema')
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.capacity.proofs import validate_decision
    try:
        validate_decision(record)
    except Exception as exc:
        raise DeliveryHeld('invalid context capacity proof') from exc


def _turn(payload:dict)->None:
    if type(payload) is not dict or set(payload) not in (_TURN, _TURN|{'context_capacity'}):
        raise DeliveryHeld('unknown native turn schema; export not approved')
    if payload['schema']!='spine.turn.v1':
        raise DeliveryHeld('unrecognized native turn record')
    event_id(payload['session']);event_id(payload['request_id'])
    _safe_principal(payload['principal'])
    for name in ('request_sha256','output_sha256','model_sha256','tokenizer_sha256','context_sha256'):
        digest(payload[name])
    for name in ('revision','prompt_tokens','generated_tokens','omitted_turns'):
        _integer(payload[name])
    if payload['revision'] < 1 or payload['finish_reason'] not in ('stop','length','eos'):
        raise DeliveryHeld('invalid native completion state')
    refs=payload['evidence_refs']
    if type(refs) is not list or len(refs)>64:
        raise DeliveryHeld('unbounded source provenance in AI turn')
    for item in refs:
        if type(item) is not dict or set(item)!={'id','revision','passage_sha256','document_sha256'}:
            raise DeliveryHeld('unknown source provenance field')
        event_id(item['id']);_integer(item['revision']);digest(item['passage_sha256'])
        if item['document_sha256'] is not None:digest(item['document_sha256'])
    if 'context_capacity' in payload:
        _capacity(payload['context_capacity'])


def validate_external(event:dict)->None:
    if type(event) is not dict or set(event)!={'sequence','event_key','stream','kind','payload','event_sha256'}:
        raise DeliveryHeld('unexpected outbound event fields')
    event_id(event['event_key']);event_id(event['stream']);digest(event['event_sha256'])
    _integer(event['sequence'])
    if event['sequence']<1:raise DeliveryHeld('nonpositive outbound sequence')
    if event['kind']=='ai_flight':
        _flight(event['payload'])
        if event['stream']!=event['payload']['job_id']:
            raise DeliveryHeld('flight event stream identity mismatch')
    elif event['kind']=='ai_turn':
        _turn(event['payload'])
        if event['stream']!=event['payload']['session']:
            raise DeliveryHeld('native turn stream identity mismatch')
    else:
        raise DeliveryHeld('unsupported private AI event export type')
