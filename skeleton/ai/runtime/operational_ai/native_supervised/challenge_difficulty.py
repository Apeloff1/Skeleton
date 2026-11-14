"""Preserve source-defined domain/severity groupings; no post hoc easy-only score."""
from __future__ import annotations
from .challenge_runner import ChallengeRun
from .challenge_oracle import DOMAINS,CRITICAL
from .errors import reject


def domain_matrix(run:ChallengeRun)->dict:
    if type(run) is not ChallengeRun:
        reject("difficulty-run")
    groups={domain:{"passed":0,"failed":0} for domain in DOMAINS}
    for item in run.results:
        if item.domain not in groups:
            reject("difficulty-domain-drift")
        key="passed" if item.passed else "failed"
        groups[item.domain][key]+=1
    missing=[d for d,x in groups.items() if sum(x.values())!=24]
    return {
        "schema":"skeleton.native-supervised.domain-matrix.v1",
        "groups":groups,
        "critical_domains":list(sorted(CRITICAL)),
        "all_domains_complete":not missing and run.complete,
        "missing_or_partial":missing,
        "selection_allowed":False,
    }
