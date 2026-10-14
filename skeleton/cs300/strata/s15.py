"""CS300-S15 runners. stored_prose stays 0."""
from __future__ import annotations
import hashlib, json
from typing import Any

class StratumReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

LAYERS = {
    "CS300-141": "executable_specification_kernel",
    "CS300-142": "property_based_contract",
    "CS300-143": "model_checking_pipeline",
    "CS300-144": "temporal_logic_verification",
    "CS300-145": "smt_backed_invariant",
    "CS300-146": "proof_carrying_artifact",
    "CS300-147": "refinement_proof_chain",
    "CS300-148": "verified_state_machine",
    "CS300-149": "mechanized_security_theorems",
    "CS300-150": "formal_methods_finality",
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
