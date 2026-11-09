"""Refuse a repeated claim whose provenance digest drifted. Parent #80."""
from __future__ import annotations

import hmac

from skeleton.ai.pr_seams.crawler_provenance_bind import CrawlPointer, bind

_HEX = set("0123456789abcdef")


class HoldoutError(ValueError):
    pass


def _hex64(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise HoldoutError("invalid provenance digest")
    return value


class ProvenanceHoldout:
    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def admit(self, pointer: CrawlPointer, context_id: str) -> dict[str, object]:
        if not isinstance(pointer, CrawlPointer):
            raise HoldoutError("CrawlPointer required")
        digest = _hex64(pointer.digest)
        prior = self._seen.get(pointer.url)
        if prior is not None and not hmac.compare_digest(prior, digest):
            raise HoldoutError("provenance digest drift")
        bound = bind(pointer, context_id)
        self._seen[pointer.url] = digest
        return {
            "kind": "crawler-holdout",
            "parent": "#80",
            "stored_prose": 0,
            "hit": 1,
            "url": pointer.url,
            "digest": digest,
            "bind_id": bound.bind_id,
        }


__all__ = ["HoldoutError", "ProvenanceHoldout"]
