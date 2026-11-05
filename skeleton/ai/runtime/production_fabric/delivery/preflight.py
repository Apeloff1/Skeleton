"""Local preflight reports hold conditions without fabricating CI or hardware passes."""
from ..evaluation.quality import qualify

def preflight(*, evidence: dict, files: list[dict]) -> dict:
    quality = qualify(evidence)
    bad = [item.get('path', 'unknown') for item in files if item.get('size', 0) >= 100000000 or item.get('size', 0) < 0]
    return {'status': 'hold' if bad or quality['status'] == 'hold' else 'locally-admissible', 'oversize_files': bad, 'quality': quality, 'requires_exact_head_ci': True, 'release_certified': False}
