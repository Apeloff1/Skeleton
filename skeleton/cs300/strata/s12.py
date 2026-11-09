"""CS300-S12 runners. stored_prose stays 0."""
from __future__ import annotations
import hashlib, json
from typing import Any

class StratumReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

LAYERS = {
    "CS300-111": "exactly_once_processing",
    "CS300-112": "event_time_watermarks",
    "CS300-113": "late_data_reconciliation",
    "CS300-114": "backpressure_propagation",
    "CS300-115": "incremental_computation_engine",
    "CS300-116": "differential_dataflow_layer",
    "CS300-117": "complex_event_processing",
    "CS300-118": "stateful_stream_recovery",
    "CS300-119": "adaptive_stream_join",
    "CS300-120": "dataflow_finality_gate",
}

def admit(layer_id: str, card: dict[str, Any]) -> dict[str, Any]:
    if layer_id not in LAYERS:
        raise StratumReject('unknown layer')
    if not isinstance(card, dict) or card.get('layer') != layer_id:
        raise StratumReject('identity mismatch')
    if card.get('stored_prose') not in (0, None):
        raise StratumReject('stored prose')
    if not isinstance(card.get('bound'), int) or not 1 <= card['bound'] <= 1024:
        raise StratumReject('bound')
    key = LAYERS[layer_id]
    value = card.get(key)
    if value in (None, '', [], {}):
        raise StratumReject(f'missing:{key}')
    if isinstance(value, int) and value > card['bound']:
        raise StratumReject('over bound')
    if layer_id.endswith('0') and card.get('finality') in (None, ''):
        raise StratumReject('finality')
    body = {'layer': layer_id, 'key': key, 'bound': card['bound']}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'layer': layer_id, 'key': key, 'digest': digest, 'admitted': True, 'stored_prose': 0}
