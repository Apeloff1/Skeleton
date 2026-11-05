"""Portable game definitions with content digest and no executable extraction."""
from ..contracts.canonical import digest, dumps, loads
from ..contracts.spec import parse_world, to_data
from ..contracts.errors import IntegrityError

def export_world(data: dict) -> bytes:
    world = parse_world(data)
    normalized = to_data(world)
    return dumps({'schema_version': 1, 'world': normalized, 'sha256': digest(normalized)})

def import_world(raw: bytes) -> dict:
    value = loads(raw)
    if not isinstance(value, dict) or set(value) != {'schema_version', 'world', 'sha256'} or value['schema_version'] != 1:
        raise IntegrityError('unsupported world archive')
    world = parse_world(value['world'])
    canonical = to_data(world)
    if value['sha256'] != digest(canonical):
        raise IntegrityError('world archive digest mismatch')
    return canonical
