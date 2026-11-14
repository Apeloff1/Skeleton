"""Original, evaluation-only SFT challenge schema: no training or grading shortcuts."""
from __future__ import annotations
from dataclasses import dataclass
from .challenge_oracle import synthesize,DOMAINS,CRITICAL
from .canonical import digest,decode,encode,require_id,require_int,require_text
from .errors import reject

SCHEMA="skeleton.native-supervised.challenge.v1"
LICENSE="skeleton_original"
PURPOSE="offline_native_sft_evaluation"
PROVENANCE="original_synthetic_authored"


@dataclass(frozen=True,slots=True)
class Challenge:
    case_id:str
    domain:str
    ordinal:int
    arguments:dict
    prompt:str
    expected:str
    severity:str
    license_id:str=LICENSE
    purpose:str=PURPOSE
    provenance:str=PROVENANCE

    def __post_init__(self)->None:
        require_id(self.case_id,"case")
        if self.domain not in DOMAINS:
            reject("case-domain")
        require_int(self.ordinal,"ordinal",1,24)
        if self.case_id!=f"{self.domain}_{self.ordinal:02}":
            reject("case-id-mismatch")
        if self.severity!=("critical" if self.domain in CRITICAL else "medium"):
            reject("case-severity")
        if self.license_id!=LICENSE or self.purpose!=PURPOSE or self.provenance!=PROVENANCE:
            reject("case-rights")
        if type(self.arguments) is not dict or len(self.arguments)>16:
            reject("case-arguments")
        require_text(self.prompt,"prompt",4096)
        require_text(self.expected,"expected",4096)
        args,prompt,expected=synthesize(self.domain,self.ordinal)
        if self.arguments!=args or self.prompt!=prompt or self.expected!=expected:
            reject("case-independent-oracle-mismatch")

    @classmethod
    def parse(cls,raw:bytes)->"Challenge":
        record=decode(raw)
        fields={"schema","id","domain","ordinal","arguments","prompt",
                "expected","severity","license_id","purpose","provenance"}
        if type(record) is not dict or set(record)!=fields or record["schema"]!=SCHEMA:
            reject("case-schema")
        return cls(
            record["id"],record["domain"],record["ordinal"],
            record["arguments"],record["prompt"],record["expected"],
            record["severity"],record["license_id"],record["purpose"],record["provenance"],
        )

    def record(self)->dict:
        return {
            "schema":SCHEMA,"id":self.case_id,"domain":self.domain,
            "ordinal":self.ordinal,"arguments":self.arguments,
            "prompt":self.prompt,"expected":self.expected,
            "severity":self.severity,"license_id":self.license_id,
            "purpose":self.purpose,"provenance":self.provenance,
        }

    @property
    def sha256(self)->str:
        return digest(self.record())

    @property
    def prompt_sha256(self)->str:
        return digest({"prompt":self.prompt})

    @property
    def expected_sha256(self)->str:
        return digest({"expected":self.expected})
