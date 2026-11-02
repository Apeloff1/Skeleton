"""Identity-pinned model generation with request and output receipts."""
from __future__ import annotations
from dataclasses import dataclass
import threading
import time
from typing import Protocol
from ..authority.budgets import Limits,BudgetLedger
from ..authority.canonical import ContractViolation,sha256
from .native import Generated
from .admission import InferenceAdmission
from .circuit import CircuitBreaker


class Backend(Protocol):
    @property
    def model_digest(self)->str:...
    @property
    def tokenizer_digest(self)->str:...
    def generate(self,messages:list[dict[str,str]],*,max_output_tokens:int,
                 seed:int,temperature:float)->Generated:...


@dataclass(frozen=True,slots=True)
class Completion:
    generation: Generated
    elapsed_ns: int
    input_digest: str
    remaining: dict[str,int]


class ModelGateway:
    def __init__(self,backend:Backend,admission:InferenceAdmission|None=None,
                 circuit:CircuitBreaker|None=None):
        if (not isinstance(getattr(backend,"model_digest",None),str)
                or not isinstance(getattr(backend,"tokenizer_digest",None),str)):
            raise ContractViolation("explicit model and tokenizer identity required")
        self.backend=backend
        self.admission=admission or InferenceAdmission()
        self.circuit=circuit or CircuitBreaker()

    def complete(self,messages:list[dict[str,str]],limits:Limits,*,seed:int=0,
                 temperature:float=1.0,cancel:threading.Event|None=None)->Completion:
        if type(seed) is not int or not 0<=seed<=2**32-1:
            raise ContractViolation("invalid deterministic sampling seed")
        if type(temperature) is not float and type(temperature) is not int:
            raise ContractViolation("invalid temperature")
        if not 0<temperature<=2.0:
            raise ContractViolation("invalid bounded temperature")
        ledger=BudgetLedger(limits)
        from ..authority.canonical import canonical_bytes
        raw=canonical_bytes(messages,ceiling=2_097_152)
        ledger.charge(input_bytes=len(raw))
        started=time.monotonic_ns()
        self.circuit.admit()
        try:
            with self.admission.slot(deadline_ns=started+limits.deadline_ms*1_000_000,cancel=cancel):
                result=self.backend.generate(messages,max_output_tokens=limits.output_tokens,
                                             seed=seed,temperature=float(temperature))
            # Native output is untrusted until every receipt constraint passes.
            # A mismatched digest, budget overrun or failed deadline is a model
            # failure and MUST count toward the breaker, not a silent success.
            ledger.deadline()
            if not isinstance(result,Generated):
                raise ContractViolation("model backend supplied no verifiable generation receipt")
            if (result.model_digest!=self.backend.model_digest or
                result.tokenizer_digest!=self.backend.tokenizer_digest):
                raise ContractViolation("model/tokenizer identity mismatch after inference")
            if result.output_digest!=sha256(result.text.encode("utf-8")):
                raise ContractViolation("native output digest does not match generated text")
            if result.generated_tokens>limits.output_tokens:
                raise ContractViolation("model output token budget exceeded")
            ledger.charge(output_bytes=len(result.text.encode("utf-8")),
                          output_tokens=result.generated_tokens)
            if result.prompt_tokens+result.generated_tokens>limits.context_tokens:
                raise ContractViolation("native context-token overrun")
            ledger.charge(context_tokens=result.prompt_tokens+result.generated_tokens)
        except Exception:
            self.circuit.failure()
            raise
        self.circuit.success()
        return Completion(result,time.monotonic_ns()-started,sha256(raw),
            {key:ledger.remaining(key) for key in ledger.spent})
