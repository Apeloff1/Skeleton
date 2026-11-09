"""Atomic operator-evidence bundle with same-identity/model, expiry and digest checks."""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from ..contracts import Rejected,fail,canonical,sha256
from ..engine import validate
from ..catalog import domains

@dataclass(frozen=True,slots=True)
class BundleReceipt:
    domains:tuple[str,...]
    identity_sha256:str
    evidence_sha256:str
    source_only:bool=True
    release_certified:bool=False

class EvidenceBundle:
    def __init__(self,*,maximum=40):
        if type(maximum) is not int or not 1<=maximum<=40:
            fail("invalid bounded evidence bundle size")
        self._max=maximum
        self._lock=RLock()
        self._rows={}
        self._sealed=False
        self._identity=None
        self._valid_at=None

    def add(self,domain,record):
        if domain not in domains():fail("unknown evidence domain")
        receipt=validate(domain,record)
        identity=record["identity"]
        scoped=(identity["tenant"],identity["subject"],identity["model_sha256"],identity["scope"])
        observed=record["timing"]["observed_ns"]
        with self._lock:
            if self._sealed:fail("sealed bundle cannot mutate")
            if domain in self._rows:fail("duplicate domain input")
            if len(self._rows)>=self._max:fail("evidence bundle capacity reached")
            if self._identity is not None and scoped!=self._identity:
                fail("evidence domains disagree about caller or model epoch")
            if self._valid_at is not None and observed!=self._valid_at:
                fail("evidence collected at inconsistent logical time")
            self._identity=scoped
            self._valid_at=observed
            self._rows[domain]={"record":record,"receipt":receipt}
            return dict(receipt)

    def seal(self,*,required):
        if type(required) not in (set,frozenset,tuple,list):
            fail("explicit bounded domain list required")
        if not 1<=len(required)<=40 or any(type(item) is not str for item in required):
            fail("required domain names must be bounded strings")
        required=set(required)
        if not required or not required.issubset(set(domains())):
            fail("unknown or empty required assurance domain set")
        with self._lock:
            if self._sealed:fail("evidence already sealed")
            if not required.issubset(self._rows):
                fail("incomplete evidence controls")
            if self._identity is None:fail("evidence bundle is empty")
            envelope={"schema":"ai-reliability-bundle.v1",
                "identity":list(self._identity),"observed_ns":self._valid_at,
                "receipts":{name:self._rows[name]["receipt"]["record_sha256"]
                    for name in sorted(self._rows)}}
            digest=sha256(canonical(envelope))
            identity_sha=sha256(canonical(list(self._identity)))
            self._sealed=True
            return BundleReceipt(tuple(sorted(self._rows)),identity_sha,digest)

    def snapshot(self):
        with self._lock:
            return {"domains":tuple(sorted(self._rows)),"sealed":self._sealed,
                    "identity":self._identity,"observed_ns":self._valid_at}
