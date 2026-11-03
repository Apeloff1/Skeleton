"""Measured source-token coverage by the source-derived native vocabulary."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.cortex.port import tokens
from .vocabulary import NativeVocabulary
from .source import GenesisSource
from .errors import refuse


@dataclass(frozen=True, slots=True)
class VocabCoverage:
    total: int
    recognized: int
    unknown: int
    fraction_ppm: int
    source_partition: str

    def report(self) -> dict:
        return {
            "total": self.total,"recognized":self.recognized,
            "unknown":self.unknown,"fraction_ppm":self.fraction_ppm,
            "source_partition":self.source_partition,
            "actual_tokenizer_compatibility_measured":True,
            "model_quality_scored":False,
        }


def inspect(source: GenesisSource,vocabulary: NativeVocabulary,
            *, partition: str = "train") -> VocabCoverage:
    if type(source) is not GenesisSource or type(vocabulary) is not NativeVocabulary:
        refuse("vocab-coverage-types")
    if partition not in ("train","validation","holdout"):
        refuse("vocab-coverage-partition")
    entries=set(vocabulary.entries)
    if partition == "train":
        lines=source.training_lines
    else:
        # Read evaluation examples for measurement only. Never fit on them.
        lines=tuple(item.render() for item in getattr(source.partitions,partition))
    total=recognized=0
    for line in lines:
        observed=tokens(line)
        total+=len(observed)
        recognized+=sum(part in entries for part in observed)
    if total==0:
        refuse("vocab-coverage-empty")
    return VocabCoverage(total,recognized,total-recognized,
                         recognized*1000000//total,partition)
