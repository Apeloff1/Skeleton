"""Logical artifact paths forbid traversal, Windows separators and control bytes."""
from pathlib import PurePosixPath
from ..contracts.errors import ContractError

def relative_path(raw: str) -> str:
    if not isinstance(raw, str) or not 1 <= len(raw) <= 512 or '\\' in raw or (':' in raw) or ('%' in raw) or any((ord(c) < 32 for c in raw)):
        raise ContractError('unsafe artifact path')
    path = PurePosixPath(raw)
    if path.is_absolute() or raw.startswith('-') or any((x in {'', '.', '..'} for x in raw.split('/'))) or (path.as_posix() != raw):
        raise ContractError('unsafe noncanonical artifact path')
    return raw
