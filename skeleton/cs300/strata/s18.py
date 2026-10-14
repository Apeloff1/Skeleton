"""CS300-S18 runners. stored_prose stays 0."""
from __future__ import annotations
import hashlib, json
from typing import Any

class StratumReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

LAYERS = {
    "CS300-171": "opentelemetry_semantic_contract",
    "CS300-172": "causal_trace_correlation",
    "CS300-173": "continuous_profiling_plane",
    "CS300-174": "ebpf_performance_attribution",
    "CS300-175": "tail_latency_budgeting",
    "CS300-176": "queueing_theory_capacity",
    "CS300-177": "slo_error_budget",
    "CS300-178": "performance_regression_bisector",
    "CS300-179": "cost_per_useful",
    "CS300-180": "performance_finality_gate",
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
