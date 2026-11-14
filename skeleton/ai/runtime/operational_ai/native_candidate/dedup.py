"""Source and normalized text deduplication before any candidate training."""
from __future__ import annotations
import hashlib
import unicodedata
from .records import TrainingExample
from .strict import digest
from .errors import deny


def normalized(value: str) -> str:
    if type(value) is not str:
        deny("normalize-text")
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def text_digest(value: str) -> str:
    return hashlib.sha256(normalized(value).encode("utf-8")).hexdigest()


def require_unique(examples: tuple[TrainingExample, ...]) -> dict:
    seen_ids = set()
    seen_prompts = set()
    seen_pairs = set()
    seen_sources = set()
    for entry in examples:
        if type(entry) is not TrainingExample:
            deny("dedup-record")
        if entry.item_id in seen_ids:
            deny("dedup-identity")
        prompt_hash = text_digest(entry.prompt)
        pair_hash = digest({"prompt": normalized(entry.prompt),
                            "completion": normalized(entry.completion)})
        if prompt_hash in seen_prompts or pair_hash in seen_pairs:
            deny("dedup-text")
        if entry.source_digest in seen_sources:
            deny("dedup-source")
        seen_ids.add(entry.item_id)
        seen_prompts.add(prompt_hash)
        seen_pairs.add(pair_hash)
        seen_sources.add(entry.source_digest)
    return {
        "total": len(examples),
        "unique_items": len(seen_ids),
        "unique_prompts": len(seen_prompts),
        "unique_pairs": len(seen_pairs),
        "unique_sources": len(seen_sources),
        "dedup_sha256": digest(sorted(seen_pairs)),
    }
