"""Exact-model startup path, no remote provider or synthetic model fallback."""
from __future__ import annotations
from pathlib import Path
from contextlib import ExitStack
import os
from ...model.gguf.service import load_approved_manifest,activate_model
from ...orchestration.execution_spine.contracts import Identity,SpineLimits,SpineError
from ...orchestration.execution_spine.database import SpineDatabase
from ...orchestration.execution_spine.lease import SessionGate
from ...orchestration.execution_spine.coordinator import ExecutionSpine
from ...orchestration.execution_spine.supervisor import SupervisedAI
from ...orchestration.execution_spine.path_policy import open_private_root
from ..boot.identity import PrincipalBinding,establish_binding

def activate(*,model_root:str|Path,state_dir:str|Path,tenant:str,subject:str,
             n_ctx:int=2048,max_new_tokens:int=256,n_threads:int=4,
             gpu_layers:int=0,isolated:bool=False,inference_ms:int=90000,
             capacity_root:str|Path|None=None,capacity_slots:int=1,
             capacity_budget_bytes:int=8_000_000_000):
    """Return an ExitStack and working supervised execution spine.

    Caller must close stack on failure and after serving. This does not claim
    a model qualified unless real llama.cpp successfully activates.
    """
    stack=ExitStack()
    try:
        root_fd=open_private_root(state_dir)
        try:
            try:os.mkdir('execution_gates',0o700,dir_fd=root_fd)
            except FileExistsError:pass
        finally:os.close(root_fd)
        manifest=load_approved_manifest(model_root)
        capacity_lease=None
        if capacity_root is not None:
            from ...model.admission import CapacityBroker,CapacityPolicy
            from ...model.admission.estimates import reservation_for
            from ...model.admission.wrapper import AdmittedBackend
            policy=CapacityPolicy(capacity_slots,capacity_budget_bytes)
            broker=stack.enter_context(CapacityBroker(capacity_root,policy))
            capacity_lease=stack.enter_context(broker.acquire(reservation_for(
                manifest,tenant=tenant,subject=subject,policy=policy)))
        if type(isolated) is not bool:
            raise SpineError('invalid native isolation option')
        if isolated:
            from ...model.isolation.client import IsolatedGGUFBackend
            model=stack.enter_context(IsolatedGGUFBackend(
                Path(model_root).absolute(),manifest,n_ctx=n_ctx,n_threads=n_threads,
                n_gpu_layers=gpu_layers,inference_ms=inference_ms,
                capacity_lease=capacity_lease))
        else:
            model=stack.enter_context(activate_model(model_root,manifest,
                n_ctx=n_ctx,n_threads=n_threads,n_gpu_layers=gpu_layers))
        if capacity_lease is not None:
            model=AdmittedBackend(model,capacity_lease)
        identity=Identity(tenant,subject,model.model_digest,model.tokenizer_digest)
        # A preexisting unbound spine database must never be adopted by a new
        # tenant identity, even if older state-binder versions do not know it.
        state_fd=open_private_root(state_dir)
        try:
            try:os.stat('state.identity.json',dir_fd=state_fd,follow_symlinks=False)
            except FileNotFoundError:
                for name in ('ai-spine.sqlite','ai-spine.sqlite-wal','ai-spine.sqlite-shm',
                             'ai-spine.sqlite-journal'):
                    try:os.stat(name,dir_fd=state_fd,follow_symlinks=False)
                    except FileNotFoundError:continue
                    raise SpineError('unbound previous AI spine requires explicit migration')
        finally:os.close(state_fd)
        establish_binding(state_dir,PrincipalBinding(identity.tenant,identity.subject,
            identity.model_sha256,identity.tokenizer_sha256))
        db=stack.enter_context(SpineDatabase(state_dir))
        gate=stack.enter_context(SessionGate(Path(state_dir)/'execution_gates'))
        limits=SpineLimits(context_tokens=n_ctx,max_output_tokens=max_new_tokens)
        # The knowledge plane lives in the SAME durable SQLite custody as the
        # inference spine. No remote embeddings or model-generated memory.
        # FTS5 absence, migration ambiguity or owner mismatch refuses boot.
        from ...context.knowledge_plane.service import KnowledgePlane
        knowledge=KnowledgePlane(db,identity)
        # No live inference is exposed with corrupted source custody, missing
        # mutation receipts or mismatched FTS5 postings. These are explicit
        # startup holds; doctor never fabricates source or model confidence.
        knowledge.doctor(maximum=65536)
        knowledge.check_index()
        runtime=ExecutionSpine(db=db,session_gate=gate,backend=model,
                               identity=identity,limits=limits,
                               evidence_provider=knowledge.evidence_provider())
        return stack, SupervisedAI(runtime)
    except BaseException:
        stack.close();raise
