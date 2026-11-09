"""Safety-first local quality rubric; unknown evidence is a hold, never a pass."""
from ..contracts.errors import ContractError
CRITERIA = ('structural', 'ending_reachability', 'replay_integrity', 'rights', 'content_provenance', 'adversarial')

def qualify(evidence: dict[str, bool | None]) -> dict:
    if not isinstance(evidence, dict) or any((k not in CRITERIA for k in evidence)):
        raise ContractError('unknown qualification evidence')
    missing = [k for k in CRITERIA if evidence.get(k) is not True]
    return {'status': 'hold' if missing else 'locally-qualified', 'blocking': missing, 'release_ready': False, 'external_security_review_required': True}
