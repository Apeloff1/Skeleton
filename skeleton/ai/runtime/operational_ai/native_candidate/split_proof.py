"""Independent checks for group, text and source isolation across partitions."""
from __future__ import annotations
from .dedup import text_digest
from .splits import Partition
from .strict import digest
from .errors import deny


def verify(partition: Partition) -> dict:
    if type(partition) is not Partition:
        deny("split-type")
    collections = (partition.train, partition.validation, partition.holdout)
    ids = [set(e.item_id for e in group) for group in collections]
    sources = [set(e.source_digest for e in group) for group in collections]
    prompts = [set(text_digest(e.prompt) for e in group) for group in collections]
    groups = [set(e.group_id for e in group) for group in collections]
    for dimension in (ids, sources, prompts, groups):
        for i in range(len(dimension)):
            for j in range(i+1, len(dimension)):
                if dimension[i] & dimension[j]:
                    deny("split-leak")
    if tuple(map(len, collections)) != (432, 72, 72):
        deny("split-count")
    return {
        "train": 432, "validation": 72, "holdout": 72,
        "source_disjoint": True, "group_disjoint": True,
        "normalized_prompt_disjoint": True,
        "digest": digest({"ids": [sorted(x) for x in ids], "groups": [sorted(x) for x in groups]}),
        "real_model_evaluated": False,
    }
