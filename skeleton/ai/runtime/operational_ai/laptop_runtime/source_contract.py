"""Pure installed GGUF source snapshot shape/identity validation.

This is not an installed-model inspector, rights authority, native worker,
device evidence or permission grant. It only enforces one contract shared by
laptop first-turn, cold restart and the Jeeves live publication fence.
"""
from __future__ import annotations

from .identity import ActiveModel

_SOURCE_FIELDS = frozenset((
    "model_sha256", "tokenizer_sha256", "manifest_sha256",
    "archive_sha256", "source_sha", "installed_model_bytes",
    "installed_shard_count",
))

_HEX = frozenset("0123456789abcdef")


def valid_source_snapshot(snapshot: object, principal: ActiveModel) -> bool:
    """Reject malformed source custody even if an injected witness claims success.

    The canonical installed-source inspector remains the authority for the
    operating system's descriptors, rights, isolated child and capacity lease.
    This pure shape check is deliberately narrower than that authority: it
    prevents a drift between readiness and publication guards, including
    bool-as-int inventory fields and spurious additional source keys.
    """
    if type(principal) is not ActiveModel:
        return False
    if type(snapshot) is not dict or set(snapshot) != _SOURCE_FIELDS:
        return False
    if (
        snapshot["model_sha256"] != principal.model_sha256
        or snapshot["tokenizer_sha256"] != principal.tokenizer_sha256
    ):
        return False
    for key in (
        "model_sha256", "tokenizer_sha256",
        "manifest_sha256", "archive_sha256",
    ):
        value = snapshot[key]
        if type(value) is not str or len(value) != 64 or not set(value) <= _HEX:
            return False
    source = snapshot["source_sha"]
    if type(source) is not str or len(source) not in (40, 64) or not set(source) <= _HEX:
        return False
    size = snapshot["installed_model_bytes"]
    shards = snapshot["installed_shard_count"]
    if type(size) is not int or not 1 <= size <= 10**12:
        return False
    if type(shards) is not int or not 1 <= shards <= 65536:
        return False
    return True




__all__ = ["valid_source_snapshot"]
