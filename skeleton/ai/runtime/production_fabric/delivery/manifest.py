"""Deterministic source manifest (not a cryptographic signature or release)."""
from ..contracts.canonical import digest
from ..contracts.errors import ContractError
from ..security.pathguard import relative_path

def make(entries: list[dict], *, source_ref: str) -> dict:
    if not isinstance(entries, list) or len(entries) > 100000 or (not isinstance(source_ref, str)) or (not source_ref):
        raise ContractError('invalid delivery inventory')
    keys = set()
    ordered = []
    for item in entries:
        if set(item) != {'path', 'sha256', 'size', 'wave'}:
            raise ContractError('invalid source entry')
        path = relative_path(item['path'])
        seal = item['sha256']
        if not isinstance(seal, str) or len(seal) != 64 or any((ch not in '0123456789abcdef' for ch in seal)):
            raise ContractError('entry SHA-256 must be lowercase hex')
        if path in keys:
            raise ContractError('duplicate inventory path')
        keys.add(path)
        if type(item['size']) is not int or not 0 <= item['size'] < 100000000 or item['wave'] not in [f'MBW-{i:02}' for i in range(8)]:
            raise ContractError('source exceeds per-file limit or invalid wave')
        ordered.append(dict(item))
    ordered.sort(key=lambda x: (x['wave'], x['path']))
    payload = {'schema_version': 1, 'source_ref': source_ref, 'entries': ordered}
    return {'payload': payload, 'sha256': digest(payload), 'release_attested': False}
