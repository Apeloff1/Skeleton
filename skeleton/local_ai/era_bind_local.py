"""
Local era_bind for GameForge emit.
Force citations on execute. HOUSE_ERA binding.
"""
from typing import Dict

def bind_era(spec: Dict, citations: list) -> Dict:
    spec = dict(spec)
    spec["era"] = "HOUSE_ERA"
    spec["citations"] = citations
    return spec
