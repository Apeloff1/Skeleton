"""Originality and provenance inventory must be explicit before artifact publication."""

def attest_entries(entries: list[dict]) -> dict:
    missing = []
    for i, item in enumerate(entries):
        if not isinstance(item, dict) or not item.get('source') or (not item.get('license')) or (item.get('rights_approved') is not True):
            missing.append(i)
    return {'admitted': not missing, 'incomplete': missing, 'independent_rights_audit_complete': False}
