"""Exhaustive 768-case original challenge inventory; reject dropped or substituted data."""
from __future__ import annotations
from importlib import resources
from .challenge_schema import Challenge
from .challenge_oracle import DOMAINS
from .canonical import digest
from .errors import reject

CASES_PER_DOMAIN=24
TOTAL=768


def iter_challenges():
    root=resources.files(__package__)/"challenges"/"v1"
    seen=set()
    for domain in DOMAINS:
        folder=root/domain
        count=0
        for file in sorted(folder.iterdir(),key=lambda f:f.name):
            if file.suffix!=".json" or not file.stem.startswith(domain+"_"):
                reject("challenge-unexpected-file")
            raw=file.read_bytes()
            if len(raw)>16384:
                reject("challenge-file-oversize")
            obj=Challenge.parse(raw)
            if obj.domain!=domain or obj.case_id!=file.stem:
                reject("challenge-path-identity")
            if obj.case_id in seen:
                reject("challenge-duplicate-identity")
            seen.add(obj.case_id)
            count+=1
            yield obj
        if count!=CASES_PER_DOMAIN:
            reject("challenge-domain-incomplete")
    if len(seen)!=TOTAL:
        reject("challenge-global-incomplete")


def inventory()->dict:
    all_cases=tuple(iter_challenges())
    return {
        "schema":"skeleton.native-supervised.challenge-inventory.v1",
        "count":len(all_cases),
        "domains":list(DOMAINS),
        "source_sha256":digest([item.record() for item in all_cases]),
        "entries":{item.case_id:item.sha256 for item in all_cases},
        "trained_on_challenges":False,
        "native_inference_executed":False,
        "release_certified":False,
    }


def verify_exact(cases:tuple[Challenge,...])->bool:
    if type(cases) is not tuple or len(cases)!=TOTAL:
        return False
    expected={c.case_id:c.sha256 for c in iter_challenges()}
    actual={}
    for case in cases:
        if type(case) is not Challenge or case.case_id in actual:
            return False
        actual[case.case_id]=case.sha256
    return actual==expected
