from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.evaluation.model_eval_harness import ModelEvalCase,ModelEvalError,ModelEvalResult,ModelEvaluationReport,build_model_report

def d(x): return hashlib.sha256(x.encode()).hexdigest()

def test_model_eval_report_requires_exact_case_coverage():
    cases=(ModelEvalCase("c1",d("input"),"rubric"),ModelEvalCase("c2",d("input2"),"rubric"))
    results=(ModelEvalResult("c1","m",900000,True,d("e1")),ModelEvalResult("c2","m",400000,False,d("e2")))
    report=build_model_report(model_id="m",benchmark_id="bench",quality_vector_digest=d("q"),cases=cases,results=results)
    assert report.pass_rate_ppm==500000
    assert report.promotion_authority is False
    assert len(report.digest)==64

def test_missing_case_result_fails_closed():
    cases=(ModelEvalCase("c1",d("i"),"r"),ModelEvalCase("c2",d("j"),"r"))
    with pytest.raises(ModelEvalError,match="exactly cover"):
        build_model_report(model_id="m",benchmark_id="b",quality_vector_digest=d("q"),cases=cases,results=(ModelEvalResult("c1","m",1,False,d("e")),))

def test_result_model_identity_mismatch_is_rejected():
    with pytest.raises(ModelEvalError,match="model identity mismatch"):
        ModelEvaluationReport("m","b",d("q"),(ModelEvalResult("c","other",1,False,d("e")),),0)

def test_report_cannot_claim_promotion_authority():
    with pytest.raises(ModelEvalError,match="cannot grant"):
        ModelEvaluationReport("m","b",d("q"),(ModelEvalResult("c","m",1000000,True,d("e")),),1000000,True)
