"""Atomic, evidence-bound publication of completed training artifacts."""
from __future__ import annotations
from dataclasses import dataclass
import hmac
from .registry import ModelArtifact, ModelDevelopmentRegistry, TrainingRun, LineageError, RegistryError, canonical_digest
from .training import TrainingExecution, TrainingError

class PublicationError(RegistryError): pass
class CompletionMismatch(PublicationError): pass

@dataclass(frozen=True)
class TrainingCompletion:
    run_digest:str
    final_state_digest:str
    receipt_digests:tuple[str,...]
    seed:int
    tokens:int
    compute_units:int
    authority_scope:str="research-only"
    def __post_init__(self):
        vals=(self.run_digest,self.final_state_digest,*self.receipt_digests)
        if any(not isinstance(x,str) or len(x)!=64 or any(c not in "0123456789abcdef" for c in x) for x in vals):
            raise PublicationError("invalid completion digest")
        if not isinstance(self.seed,int) or isinstance(self.seed,bool): raise PublicationError("invalid seed")
        if any(not isinstance(x,int) or isinstance(x,bool) or x<0 for x in (self.tokens,self.compute_units)):
            raise PublicationError("invalid completion accounting")
        if self.authority_scope!="research-only": raise PublicationError("completion cannot grant production authority")
    @property
    def completion_digest(self):
        return canonical_digest({"run_digest":self.run_digest,"final_state_digest":self.final_state_digest,"receipt_digests":list(self.receipt_digests),"seed":self.seed,"tokens":self.tokens,"compute_units":self.compute_units,"authority_scope":self.authority_scope})

def complete_execution(execution:TrainingExecution)->TrainingCompletion:
    if not isinstance(execution,TrainingExecution): raise PublicationError("TrainingExecution required")
    if execution._closed: raise PublicationError("execution already completed")
    receipts=tuple(r.receipt_digest for r in execution._receipts)
    tokens,compute=execution.totals
    execution._closed=True
    final=execution.state_digest
    return TrainingCompletion(execution.run_digest,final,receipts,execution.seed,tokens,compute)

class ArtifactPublisher:
    """Verifies completion evidence before the single registry publication mutation."""
    def __init__(self,registry:ModelDevelopmentRegistry):
        if not isinstance(registry,ModelDevelopmentRegistry): raise PublicationError("ModelDevelopmentRegistry required")
        self.registry=registry
        self._published={}
    def publish(self,run:TrainingRun,completion:TrainingCompletion,artifact:ModelArtifact):
        if not isinstance(run,TrainingRun) or not isinstance(completion,TrainingCompletion) or not isinstance(artifact,ModelArtifact):
            raise PublicationError("typed run, completion and artifact required")
        if run.status!="completed": raise PublicationError("run must be completed")
        if not hmac.compare_digest(run.run_digest,completion.run_digest): raise CompletionMismatch("completion run mismatch")
        if run.seed!=completion.seed: raise CompletionMismatch("completion seed mismatch")
        if not hmac.compare_digest(artifact.training_run_digest,run.run_digest): raise CompletionMismatch("artifact run mismatch")
        existing=self._published.get(completion.completion_digest)
        if existing is not None:
            if existing!=artifact.artifact_digest: raise CompletionMismatch("completion already bound to different artifact")
            return existing
        # All checks precede registry mutation. add_artifact itself verifies registered completed lineage.
        digest=self.registry.add_artifact(artifact)
        self._published[completion.completion_digest]=digest
        return digest
    def verify(self,completion:TrainingCompletion,artifact_digest:str)->bool:
        bound=self._published.get(completion.completion_digest)
        return bound is not None and hmac.compare_digest(bound,artifact_digest)
