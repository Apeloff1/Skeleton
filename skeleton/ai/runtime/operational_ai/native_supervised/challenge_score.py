"""Real all-domain native evaluation; critical failures cannot be averaged away."""
from __future__ import annotations
from dataclasses import dataclass
from .challenge_runner import ChallengeRun
from .challenge_oracle import DOMAINS,CRITICAL
from .challenge_catalog import TOTAL,iter_challenges
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class DomainScore:
    domain:str
    cases:int
    passed:int
    critical:bool

    @property
    def score_ppm(self)->int:
        return self.passed*1000000//self.cases if self.cases else 0

    def record(self)->dict:
        return {
            "domain":self.domain,"cases":self.cases,"passed":self.passed,
            "score_ppm":self.score_ppm,"critical":self.critical,
        }


def score(run:ChallengeRun)->dict:
    if type(run) is not ChallengeRun:
        reject("score-native-run")
    canonical=tuple(iter_challenges())
    if run.source_sha256!=digest([x.record() for x in canonical]):
        reject("score-source-drift")
    if not 1<=len(run.results)<=TOTAL:
        reject("score-empty-or-oversized")
    expected={x.case_id:x for x in canonical[run.start:run.start+len(run.results)]}
    if len(expected)!=len(run.results):
        reject("score-run-window")
    unique=set()
    for result in run.results:
        c=expected.get(result.case_id)
        if c is None or result.case_id in unique or result.case_sha256!=c.sha256:
            reject("score-case-identity")
        unique.add(result.case_id)
        if result.model_sha256!=run.model_sha256:
            reject("score-model-drift")
    domains=[]
    for domain in DOMAINS:
        cases=[x for x in run.results if x.domain==domain]
        if cases:
            domains.append(DomainScore(
                domain,len(cases),sum(x.passed for x in cases),domain in CRITICAL
            ))
    passed=sum(x.passed for x in run.results)
    critical=[x for x in run.results if x.severity=="critical"]
    return {
        "schema":"skeleton.native-supervised.score.v1",
        "total":len(run.results),"passed":passed,
        "score_ppm":passed*1000000//len(run.results),
        "critical_total":len(critical),
        "critical_failed":sum(not x.passed for x in critical),
        "domains":[x.record() for x in domains],
        "all_32_domains_measured":len(domains)==32,
        "all_768_cases_measured":run.complete,
        "no_critical_failures":bool(critical) and all(x.passed for x in critical),
        "challenge_quality_gate_met":run.complete and passed==TOTAL,
        "automatic_model_release":False,
    }
