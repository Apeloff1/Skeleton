"""All 768 original SFT challenges are evaluation-only, domain balanced."""
from __future__ import annotations
from dataclasses import dataclass
from .challenge_catalog import iter_challenges,TOTAL
from .challenge_oracle import DOMAINS,CRITICAL
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class ChallengePlan:
    cases:tuple
    critical_count:int
    normal_count:int
    catalog_sha256:str

    def report(self)->dict:
        return {
            "schema":"skeleton.native-supervised.challenge-plan.v1",
            "cases":len(self.cases),
            "critical":self.critical_count,
            "medium":self.normal_count,
            "catalog_sha256":self.catalog_sha256,
            "train_cases":0,
            "candidate_training_labels_exposed":False,
        }


def plan()->ChallengePlan:
    items=tuple(iter_challenges())
    if len(items)!=TOTAL:
        reject("challenge-plan-incomplete")
    critical=sum(x.domain in CRITICAL for x in items)
    if critical!=len(CRITICAL)*24:
        reject("challenge-critical-count")
    if any(sum(x.domain==domain for x in items)!=24 for domain in DOMAINS):
        reject("challenge-domain-scope")
    return ChallengePlan(
        items,critical,len(items)-critical,
        digest([x.record() for x in items]),
    )
