"""CS300-S22 runners. stored_prose stays 0."""
from __future__ import annotations
import hashlib, json
from typing import Any

class StratumReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

LAYERS = {
    "CS300-211": "portable_accelerator_abstraction",
    "CS300-212": "cuda_hip_sycl",
    "CS300-213": "kernel_fusion_planner",
    "CS300-214": "tensor_core_precision",
    "CS300-215": "gpu_memory_hierarchy",
    "CS300-216": "asynchronous_stream_scheduler",
    "CS300-217": "collective_communication_engine",
    "CS300-218": "multi_gpu_topology",
    "CS300-219": "accelerator_fault_isolation",
    "CS300-220": "accelerator_finality_gate",
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
