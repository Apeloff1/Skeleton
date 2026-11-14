"""Deterministic group-disjoint train/validation/holdout split with no leakage."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib

from .catalog import DOMAINS, CASES_PER_DOMAIN, TOTAL_EXAMPLES
from .records import TrainingExample
from .strict import digest, identity
from .errors import deny


@dataclass(frozen=True, slots=True)
class Partition:
    train: tuple[TrainingExample, ...]
    validation: tuple[TrainingExample, ...]
    holdout: tuple[TrainingExample, ...]

    @property
    def digest(self) -> str:
        return digest({
            "schema": "skeleton.native-candidate.partitions.v1",
            "train": [e.source_digest for e in self.train],
            "validation": [e.source_digest for e in self.validation],
            "holdout": [e.source_digest for e in self.holdout],
        })

    def record(self) -> dict:
        return {
            "train": len(self.train), "validation": len(self.validation),
            "holdout": len(self.holdout), "digest": self.digest,
        }


def partition(examples: tuple[TrainingExample, ...], *, salt: str = "skeleton_candidate_v1") -> Partition:
    identity(salt, "split-salt")
    if type(examples) is not tuple or len(examples) != TOTAL_EXAMPLES:
        deny("partition-incomplete")
    domains = {domain: [] for domain in DOMAINS}
    group_owners = {}
    for item in examples:
        if type(item) is not TrainingExample or item.domain not in domains:
            deny("partition-domain")
        if item.group_id in group_owners and group_owners[item.group_id] != item.domain:
            deny("partition-cross-domain-group")
        group_owners[item.group_id] = item.domain
        domains[item.domain].append(item)
    train, valid, held = [], [], []
    for domain in DOMAINS:
        items = domains[domain]
        if len(items) != CASES_PER_DOMAIN:
            deny("partition-domain-count")
        # Keep group clusters intact; a group can never land in multiple splits.
        groups = {}
        for item in items:
            groups.setdefault(item.group_id, []).append(item)
        if len(groups) != CASES_PER_DOMAIN:
            deny("partition-group-collision")
        ordered = sorted(groups.values(), key=lambda group: hashlib.sha256(
            (salt + ":" + group[0].group_id).encode("ascii")).digest())
        for index, group in enumerate(ordered):
            if index < 18:
                train.extend(group)
            elif index < 21:
                valid.extend(group)
            else:
                held.extend(group)
    train = tuple(sorted(train, key=lambda e: (e.domain, e.item_id)))
    valid = tuple(sorted(valid, key=lambda e: (e.domain, e.item_id)))
    held = tuple(sorted(held, key=lambda e: (e.domain, e.item_id)))
    if (len(train), len(valid), len(held)) != (432, 72, 72):
        deny("partition-count")
    ids = [e.item_id for e in train + valid + held]
    if len(ids) != len(set(ids)):
        deny("partition-overlap")
    return Partition(train, valid, held)
