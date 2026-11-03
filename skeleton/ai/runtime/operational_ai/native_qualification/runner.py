"""Real offline model invocation, source-bound per-case receipts and exact checks.

Production only accepts OfflineAIService with NativeBackend and process fence.
No model responses are synthesized. Any failed inference or empty generation
is a measured failure; a retry is never silently counted as a new pass.
"""
from __future__ import annotations

import secrets
from typing import Sequence

from .canonical import encode, sha256
from .cases import QualificationCase
from .checks import evaluate
from .clock import elapsed_ms, mono_ns, utc_stamp
from .contracts import ModelIdentity, ExecutionLimits
from .corpus import verify_exact_complete
from .errors import deny
from .model_gate import require_real_service
from .policy import Threshold
from .report import QualificationReport
from .results import CaseResult, StepResult
from .response_integrity import inspect as inspect_output


def _receipt_identity(receipt, *, model: ModelIdentity, session: str, request_id: str) -> None:
    if (receipt.session_id != session or receipt.request_id != request_id
            or receipt.model_digest != model.model_sha256
            or receipt.tokenizer_digest != model.tokenizer_sha256):
        deny("native-receipt-identity")
    if receipt.replayed is not False:
        deny("native-replayed-generation")
    if not isinstance(receipt.text, str) or not receipt.text:
        deny("native-empty-generation")


class NativeQualificationRunner:
    def __init__(
        self,
        service,
        *,
        model: ModelIdentity,
        limits: ExecutionLimits | None = None,
        threshold: Threshold | None = None,
    ):
        self.service = require_real_service(service)
        self.model = model
        self.limits = limits or ExecutionLimits()
        self.threshold = threshold or Threshold()
        if (model.model_sha256 != service.actor.model_digest
                or model.tokenizer_sha256 != service.actor.tokenizer_digest
                or model.tenant != service.actor.tenant
                or model.user != service.actor.user):
            deny("model-owner-identity")
        self._closed = False

    def run_case(self, case: QualificationCase, *, run_id: str) -> CaseResult:
        if type(case) is not QualificationCase:
            deny("case-type")
        if len(case.steps) > self.limits.max_steps_per_case:
            deny("case-step-budget")
        session = self.service.create()
        results = []
        error = None
        begun = mono_ns()
        for index, step in enumerate(case.steps):
            request = f"eval_{run_id}_{case.case_id}_{index}"
            try:
                if elapsed_ms(begun, mono_ns()) > self.limits.max_case_wall_ms:
                    deny("case-timeout")
                start = mono_ns()
                receipt = self.service.turn(
                    session=session, request_id=request, question=step.prompt,
                    seed=case.seed, temperature=case.temperature,
                )
                elapsed = elapsed_ms(start, mono_ns())
                _receipt_identity(receipt, model=self.model, session=session, request_id=request)
                if len(receipt.text) > self.limits.max_output_chars:
                    deny("response-oversize")
                if receipt.revision != index + 1:
                    deny("native-revision")
                integrity = inspect_output(receipt.text)
                marks = [evaluate(check, receipt.text) for check in step.checks]
                successes = sum(r.passed for r in marks)
                results.append(StepResult(
                    step=index, session_id=session, request_id=request,
                    revision=receipt.revision,
                    model_digest=receipt.model_digest,
                    tokenizer_digest=receipt.tokenizer_digest,
                    output_sha256=integrity.utf8_sha256,
                    runtime_output_digest=receipt.output_digest,
                    output_chars=integrity.characters,
                    prompt_tokens=receipt.prompt_tokens,
                    generated_tokens=receipt.generated_tokens,
                    latency_ms=elapsed, checks_passed=successes,
                    checks_total=len(marks),
                    failed_checks=tuple(r.kind for r in marks if not r.passed),
                    audit_status=receipt.audit_status, replayed=receipt.replayed,
                ))
                if elapsed > self.limits.max_case_wall_ms:
                    error = "case-latency-exceeded"
                    break
            except Exception as exc:
                # A fixture failure must remain failed. Do not hide errors as passes.
                error = getattr(exc, "code", "native-call-failed")
                break
        return CaseResult(
            case_id=case.case_id, domain=case.domain, severity=case.severity,
            source_sha256=case.content_sha256, steps=tuple(results), error_code=error,
        )

    def run(self, cases: Sequence[QualificationCase], *, complete_corpus: bool) -> QualificationReport:
        if self._closed:
            deny("runner-single-use")
        self._closed = True
        if type(complete_corpus) is not bool:
            deny("corpus-completeness-flag")
        if not cases or len(cases) > self.limits.max_cases:
            deny("run-case-budget")
        ids = [c.case_id for c in cases]
        if len(set(ids)) != len(ids):
            deny("run-duplicate-case")
        if complete_corpus:
            complete_corpus = verify_exact_complete(tuple(cases))
        corpus_hash = sha256(encode([c.record() for c in cases]))
        run_id = "run_" + secrets.token_hex(10)
        started = utc_stamp()
        began = mono_ns()
        results = []
        for case in cases:
            if elapsed_ms(began, mono_ns()) > self.limits.max_total_wall_ms:
                results.append(CaseResult(
                    case.case_id, case.domain, case.severity, case.content_sha256,
                    (), "run-time-budget",
                ))
                continue
            results.append(self.run_case(case, run_id=run_id))
        finished = utc_stamp()
        return QualificationReport(
            run_id=run_id, model=self.model, corpus_sha256=corpus_hash,
            cases=tuple(results), started_utc=started, finished_utc=finished,
            checkpoint_verified=True, real_native_execution=True,
            complete_corpus=complete_corpus, threshold=self.threshold,
        )
