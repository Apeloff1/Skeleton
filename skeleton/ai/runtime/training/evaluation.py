"""Immutable training evaluation suites and independent verifier gates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any, Mapping, Sequence

from skeleton.ai.runtime.inference import LocalInferenceEngine, LocalInferenceRequest, LocalModelBackend


def _canonical(value: object) -> str:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_digest(value: str, *, field: str) -> str:
    text=str(value).strip().lower()
    if len(text)!=64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be lowercase sha256")
    return text


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    prompt: str
    expected_substring: str
    max_output_tokens: int = 16

    def __post_init__(self)->None:
        if not self.case_id.strip() or not self.prompt.strip() or not self.expected_substring.strip():
            raise ValueError("evaluation case fields must be non-empty")
        if not 1<=self.max_output_tokens<=8192:
            raise ValueError("max_output_tokens out of range")

    def as_dict(self)->dict[str,object]:
        return {
            "case_id":self.case_id,
            "prompt":self.prompt,
            "expected_substring":self.expected_substring,
            "max_output_tokens":self.max_output_tokens,
        }


@dataclass(frozen=True, slots=True)
class EvaluationSuite:
    suite_id: str
    version: str
    cases: tuple[EvaluationCase,...]
    population: str
    contamination_fingerprint: str

    def __post_init__(self)->None:
        if not self.suite_id.strip() or not self.version.strip() or not self.population.strip():
            raise ValueError("evaluation suite identity must be non-empty")
        if not self.cases:
            raise ValueError("evaluation suite requires cases")
        ids=[item.case_id for item in self.cases]
        if len(ids)!=len(set(ids)):
            raise ValueError("evaluation case ids must be unique")
        object.__setattr__(
            self,
            "contamination_fingerprint",
            _require_digest(self.contamination_fingerprint,field="contamination_fingerprint"),
        )

    @property
    def digest(self)->str:
        return _digest(self.as_dict(include_digest=False))

    def as_dict(self,*,include_digest:bool=True)->dict[str,object]:
        payload={
            "suite_id":self.suite_id,
            "version":self.version,
            "cases":[item.as_dict() for item in self.cases],
            "population":self.population,
            "contamination_fingerprint":self.contamination_fingerprint,
        }
        if include_digest: payload["suite_digest"]=self.digest
        return payload


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    candidate_model_digest: str
    suite_digest: str
    passed_case_ids: tuple[str,...]
    failed_case_ids: tuple[str,...]
    outputs: Mapping[str,str]

    def __post_init__(self)->None:
        object.__setattr__(self,"candidate_model_digest",_require_digest(self.candidate_model_digest,field="candidate_model_digest"))
        object.__setattr__(self,"suite_digest",_require_digest(self.suite_digest,field="suite_digest"))
        passed=tuple(self.passed_case_ids)
        failed=tuple(self.failed_case_ids)
        if (
            any(not isinstance(case_id,str) or not case_id.strip() for case_id in (*passed,*failed))
            or len(passed)!=len(set(passed))
            or len(failed)!=len(set(failed))
            or set(passed)&set(failed)
        ):
            raise ValueError("evaluation case partition must be unique and disjoint")
        outputs=dict(self.outputs)
        if (
            set(outputs)!=(set(passed)|set(failed))
            or any(not isinstance(value,str) for value in outputs.values())
        ):
            raise ValueError("evaluation outputs must exactly cover evaluated case ids")
        object.__setattr__(self,"passed_case_ids",passed)
        object.__setattr__(self,"failed_case_ids",failed)
        object.__setattr__(self,"outputs",outputs)

    @property
    def total(self)->int:
        return len(self.passed_case_ids)+len(self.failed_case_ids)

    @property
    def accuracy(self)->float:
        return 0.0 if self.total==0 else len(self.passed_case_ids)/self.total

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {
            "candidate_model_digest":self.candidate_model_digest,
            "suite_digest":self.suite_digest,
            "passed_case_ids":list(self.passed_case_ids),
            "failed_case_ids":list(self.failed_case_ids),
            "outputs":dict(sorted(self.outputs.items())),
            "accuracy":self.accuracy,
        }


@dataclass(frozen=True, slots=True)
class VerifierReport:
    verifier_id: str
    verifier_model_digest: str
    candidate_model_digest: str
    calibration_error: float
    false_accept_rate: float
    false_reject_rate: float
    sample_count: int

    def __post_init__(self)->None:
        if not self.verifier_id.strip():
            raise ValueError("verifier_id must be non-empty")
        object.__setattr__(self,"verifier_model_digest",_require_digest(self.verifier_model_digest,field="verifier_model_digest"))
        object.__setattr__(self,"candidate_model_digest",_require_digest(self.candidate_model_digest,field="candidate_model_digest"))
        for name in ("calibration_error","false_accept_rate","false_reject_rate"):
            value=float(getattr(self,name))
            if not math.isfinite(value) or not 0<=value<=1:
                raise ValueError(f"{name} must be in [0,1]")
            object.__setattr__(self,name,value)
        if self.sample_count<=0:
            raise ValueError("sample_count must be positive")

    @property
    def independent(self)->bool:
        return self.verifier_model_digest!=self.candidate_model_digest

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {
            "verifier_id":self.verifier_id,
            "verifier_model_digest":self.verifier_model_digest,
            "candidate_model_digest":self.candidate_model_digest,
            "calibration_error":self.calibration_error,
            "false_accept_rate":self.false_accept_rate,
            "false_reject_rate":self.false_reject_rate,
            "sample_count":self.sample_count,
            "independent":self.independent,
        }


@dataclass(frozen=True, slots=True)
class CandidateQualification:
    candidate_model_digest: str
    evaluation_result_digest: str
    verifier_report_digest: str
    status: str
    reasons: tuple[str,...]

    def __post_init__(self)->None:
        for name in ("candidate_model_digest","evaluation_result_digest","verifier_report_digest"):
            object.__setattr__(self,name,_require_digest(getattr(self,name),field=name))
        if self.status not in {"qualified_candidate","rejected"}:
            raise ValueError("unsupported qualification status")
        reasons=tuple(str(reason) for reason in self.reasons)
        if self.status=="qualified_candidate" and reasons:
            raise ValueError("qualified candidate cannot carry rejection reasons")
        if self.status=="rejected" and not reasons:
            raise ValueError("rejected candidate requires at least one reason")
        object.__setattr__(self,"reasons",reasons)

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict[str,object]:
        return {
            "candidate_model_digest":self.candidate_model_digest,
            "evaluation_result_digest":self.evaluation_result_digest,
            "verifier_report_digest":self.verifier_report_digest,
            "status":self.status,
            "reasons":list(self.reasons),
            "production_promotion_authorized":False,
        }


class EvaluationHarness:
    async def evaluate(
        self,
        model: LocalModelBackend,
        suite: EvaluationSuite,
        *,
        seed: int = 0,
    ) -> EvaluationResult:
        if model.model_digest is None:
            raise ValueError("model must expose immutable identity")
        engine=LocalInferenceEngine(model,cache_size=0)
        passed=[];failed=[];outputs={}
        for index,case in enumerate(suite.cases):
            response=await engine.generate(
                LocalInferenceRequest(
                    prompt=case.prompt,
                    max_output_tokens=case.max_output_tokens,
                    seed=seed+index,
                )
            )
            text=response.text or ""
            outputs[case.case_id]=text
            if case.expected_substring.lower() in text.lower():
                passed.append(case.case_id)
            else:
                failed.append(case.case_id)
        return EvaluationResult(
            candidate_model_digest=model.model_digest,
            suite_digest=suite.digest,
            passed_case_ids=tuple(passed),
            failed_case_ids=tuple(failed),
            outputs=outputs,
        )


class TrainingEvaluationGate:
    def __init__(
        self,
        *,
        min_accuracy: float,
        max_calibration_error: float,
        max_false_accept_rate: float,
    )->None:
        for name,value in (
            ("min_accuracy",min_accuracy),
            ("max_calibration_error",max_calibration_error),
            ("max_false_accept_rate",max_false_accept_rate),
        ):
            if not math.isfinite(float(value)) or not 0<=float(value)<=1:
                raise ValueError(f"{name} must be in [0,1]")
        self.min_accuracy=float(min_accuracy)
        self.max_calibration_error=float(max_calibration_error)
        self.max_false_accept_rate=float(max_false_accept_rate)

    def qualify(
        self,
        result:EvaluationResult,
        verifier:VerifierReport,
    )->CandidateQualification:
        if result.candidate_model_digest!=verifier.candidate_model_digest:
            raise ValueError("verifier candidate identity mismatch")
        reasons=[]
        if result.accuracy<self.min_accuracy:
            reasons.append("evaluation_accuracy_below_threshold")
        if not verifier.independent:
            reasons.append("verifier_not_independent")
        if verifier.calibration_error>self.max_calibration_error:
            reasons.append("verifier_calibration_exceeded")
        if verifier.false_accept_rate>self.max_false_accept_rate:
            reasons.append("verifier_false_accept_rate_exceeded")
        return CandidateQualification(
            candidate_model_digest=result.candidate_model_digest,
            evaluation_result_digest=result.digest,
            verifier_report_digest=verifier.digest,
            status="qualified_candidate" if not reasons else "rejected",
            reasons=tuple(reasons),
        )


class EvaluationLedger:
    """Durable immutable suite/result/qualification evidence ledger."""

    def __init__(self,path:str|Path=":memory:")->None:
        self._lock=threading.RLock()
        self._db=sqlite3.connect(str(path),check_same_thread=False)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS eval_suite (
                suite_key TEXT PRIMARY KEY,
                suite_digest TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS eval_result (
                result_digest TEXT PRIMARY KEY,
                candidate_model_digest TEXT NOT NULL,
                suite_digest TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verifier_report (
                report_digest TEXT PRIMARY KEY,
                verifier_id TEXT NOT NULL,
                verifier_model_digest TEXT NOT NULL,
                candidate_model_digest TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS qualification (
                qualification_digest TEXT PRIMARY KEY,
                candidate_model_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    def register_suite(self,suite:EvaluationSuite)->str:
        key=f"{suite.suite_id}@{suite.version}"
        encoded=_canonical(suite.as_dict())
        with self._lock:
            row=self._db.execute("SELECT suite_digest,payload FROM eval_suite WHERE suite_key=?",(key,)).fetchone()
            if row is not None:
                if row[0]!=suite.digest or row[1]!=encoded:
                    raise ValueError("evaluation suite id/version is immutable")
                return suite.digest
            self._db.execute("INSERT INTO eval_suite(suite_key,suite_digest,payload) VALUES (?,?,?)",(key,suite.digest,encoded))
            self._db.commit()
        return suite.digest

    def record_result(self,result:EvaluationResult)->str:
        encoded=_canonical(result.as_dict())
        with self._lock:
            suite=self._db.execute(
                "SELECT payload FROM eval_suite WHERE suite_digest=?",
                (result.suite_digest,),
            ).fetchone()
            if suite is None:
                raise ValueError("evaluation suite is not registered")
            suite_payload=json.loads(suite[0])
            claimed_suite_digest=suite_payload.get("suite_digest")
            digest_payload=dict(suite_payload)
            digest_payload.pop("suite_digest",None)
            if (
                claimed_suite_digest!=result.suite_digest
                or _digest(digest_payload)!=result.suite_digest
            ):
                raise ValueError("stored evaluation suite digest mismatch")

            expected_case_ids=[
                str(case["case_id"])
                for case in suite_payload.get("cases",[])
                if isinstance(case,dict) and "case_id" in case
            ]
            observed_case_ids=list(result.passed_case_ids)+list(result.failed_case_ids)
            if (
                len(expected_case_ids)!=len(observed_case_ids)
                or set(expected_case_ids)!=set(observed_case_ids)
            ):
                raise ValueError(
                    "evaluation result must cover every registered suite case exactly once"
                )

            prior=self._db.execute(
                "SELECT payload FROM eval_result WHERE result_digest=?",
                (result.digest,),
            ).fetchone()
            if prior is not None:
                if prior[0]!=encoded:
                    raise ValueError("evaluation result digest collision")
                return result.digest

            self._db.execute(
                "INSERT INTO eval_result(result_digest,candidate_model_digest,suite_digest,payload) VALUES (?,?,?,?)",
                (result.digest,result.candidate_model_digest,result.suite_digest,encoded),
            )
            self._db.commit()
        return result.digest

    def record_verifier(self,report:VerifierReport)->str:
        encoded=_canonical(report.as_dict())
        with self._lock:
            prior=self._db.execute(
                "SELECT payload FROM verifier_report WHERE report_digest=?",
                (report.digest,),
            ).fetchone()
            if prior is not None:
                if prior[0]!=encoded:
                    raise ValueError("verifier report digest collision")
                return report.digest
            self._db.execute(
                "INSERT INTO verifier_report("
                "report_digest,verifier_id,verifier_model_digest,"
                "candidate_model_digest,payload"
                ") VALUES (?,?,?,?,?)",
                (
                    report.digest,
                    report.verifier_id,
                    report.verifier_model_digest,
                    report.candidate_model_digest,
                    encoded,
                ),
            )
            self._db.commit()
        return report.digest

    def record_qualification(self,qualification:CandidateQualification)->str:
        with self._lock:
            result=self._db.execute(
                "SELECT candidate_model_digest FROM eval_result "
                "WHERE result_digest=?",
                (qualification.evaluation_result_digest,),
            ).fetchone()
            if result is None:
                raise ValueError("evaluation result is not registered")
            if result[0]!=qualification.candidate_model_digest:
                raise ValueError("qualification candidate does not match evaluation result")

            verifier=self._db.execute(
                "SELECT candidate_model_digest,verifier_model_digest "
                "FROM verifier_report WHERE report_digest=?",
                (qualification.verifier_report_digest,),
            ).fetchone()
            if verifier is None:
                raise ValueError("verifier report is not registered")
            if verifier[0]!=qualification.candidate_model_digest:
                raise ValueError("qualification candidate does not match verifier report")
            if (
                qualification.status=="qualified_candidate"
                and verifier[1]==qualification.candidate_model_digest
            ):
                raise ValueError("qualified candidate requires an independent verifier")

            self._db.execute(
                "INSERT OR IGNORE INTO qualification(qualification_digest,candidate_model_digest,status,payload) VALUES (?,?,?,?)",
                (qualification.digest,qualification.candidate_model_digest,qualification.status,_canonical(qualification.as_dict())),
            )
            self._db.commit()
        return qualification.digest
