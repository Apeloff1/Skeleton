"""Vocabulary is derived exclusively from approved TRAIN partition text.

No validation, holdout, benchmark, external text or generated model outputs
may enter tokenizer fitting. The native tokenization grammar is reused
verbatim; unknown lexical forms remain unknown during independent tests.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from skeleton.cortex.port import tokens as cortex_tokens
from .canonical import digest
from .errors import refuse
from .policy import GenesisPolicy
from .source import GenesisSource


@dataclass(frozen=True, slots=True)
class NativeVocabulary:
    entries: tuple[str, ...]
    total_observed: int
    unique_documents: int
    minimum_document_frequency: int
    training_source_sha256: str
    digest: str

    def report(self) -> dict:
        return {
            "schema": "skeleton.native-genesis.vocabulary.v1",
            "entries": len(self.entries),
            "observed_tokens": self.total_observed,
            "source_documents": self.unique_documents,
            "minimum_document_frequency": self.minimum_document_frequency,
            "training_source_sha256": self.training_source_sha256,
            "vocabulary_sha256": self.digest,
            "trained_on_validation": False,
            "trained_on_holdout": False,
            "trained_on_benchmark": False,
        }


def build_vocabulary(source: GenesisSource, policy: GenesisPolicy) -> NativeVocabulary:
    if type(source) is not GenesisSource or type(policy) is not GenesisPolicy:
        refuse("vocabulary-contract")
    count = Counter()
    observed = 0
    if len(source.training_lines) != 432:
        refuse("training-partition-required")
    for line in source.training_lines:
        if type(line) is not str or len(line.encode("utf-8")) > 4096:
            refuse("vocabulary-line-budget")
        words = cortex_tokens(line)
        if not words or len(words) > 4096:
            refuse("vocabulary-token-budget")
        observed += len(words)
        count.update(set(words))
    included = tuple(sorted(
        key for key, frequency in count.items()
        if frequency >= policy.minimum_document_frequency
    ))
    if len(included) < 32 or len(included) > policy.max_vocab:
        refuse("vocabulary-capacity")
    # One native <unknown> token is added by TinyTransformer separately.
    if "__unk__" in included:
        refuse("reserved-token-collision")
    approved = digest({
        "vocabulary": list(included),
        "source_sha256": source.source_sha256,
        "partition_sha256": source.partitions_sha256,
        "frequency_floor": policy.minimum_document_frequency,
        "tokenizer_grammar": "skeleton.cortex.port.tokens",
    })
    return NativeVocabulary(
        included, observed, len(source.training_lines),
        policy.minimum_document_frequency, source.source_sha256, approved,
    )
