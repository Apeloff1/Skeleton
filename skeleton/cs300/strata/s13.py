"""CS300-S13 runners. stored_prose stays 0."""
from __future__ import annotations
import hashlib, json
from typing import Any

class StratumReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

LAYERS = {
    "CS300-121": "entropy_accounting_plane",
    "CS300-122": "adaptive_compression_selection",
    "CS300-123": "columnar_codec_stack",
    "CS300-124": "forward_error_correction",
    "CS300-125": "fountain_code_transport",
    "CS300-126": "network_coding_algebra",
    "CS300-127": "content_defined_chunking",
    "CS300-128": "semantic_compression_research",
    "CS300-129": "rate_distortion_budgeting",
    "CS300-130": "coding_theory_finality",
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
