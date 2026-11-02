"""Actual first-boot GGUF -> durable native inference -> restart -> replay.

This probe uses the production startup path and executes precisely one new
chat turn, then exits and activates the same model and state a second time.
Its result is proof of a bounded *execution path*, not semantic model quality.
"""
from __future__ import annotations
from pathlib import Path
import secrets
from .contracts import QualificationInput,QualificationError
from .proof import construct
from ...orchestration.execution_spine.doctor import inspect


def probe_first_boot(plan: QualificationInput, *, activation=None) -> dict:
    """Never makes or accepts a synthetic model without an explicit test injection.

    Tests may inject an activation factory. The output is then permanently
    marked fixture-only, and cannot be laundered into a production qualification.
    """
    if not isinstance(plan,QualificationInput):
        raise QualificationError('qualification plan required')
    real = activation is None
    if real:
        from ..production.startup import activate as activation
    activate_args = dict(model_root=plan.model_root,state_dir=plan.state_dir,
        tenant=plan.tenant,subject=plan.subject,n_ctx=plan.n_ctx,
        max_new_tokens=plan.max_new_tokens,n_threads=plan.n_threads,
        gpu_layers=plan.gpu_layers)
    session = 'q_'+secrets.token_hex(12)
    request = 'q_'+secrets.token_hex(12)
    first = None
    with_activation = activation(**activate_args)
    stack,worker=with_activation
    with stack:
        if worker.spine.identity.tenant != plan.tenant or worker.spine.identity.subject != plan.subject:
            raise QualificationError('model activation principal mismatch')
        worker.spine.create(session)
        first=worker.turn(session,request,plan.prompt,seed=plan.seed)
        proof_identity=(worker.spine.identity.model_sha256,worker.spine.identity.tokenizer_sha256)
        inspect(worker.spine.db)
    # Reconstruct from the persisted authority, not a retained in-memory model.
    stack_again,second=activation(**activate_args)
    with stack_again:
        if second.spine.identity.tenant != plan.tenant or second.spine.identity.subject != plan.subject:
            raise QualificationError('checkpoint principal changed on restart')
        if proof_identity != (second.spine.identity.model_sha256,
                              second.spine.identity.tokenizer_sha256):
            raise QualificationError('checkpoint identity changed on restart')
        replayed=second.turn(session,request,plan.prompt,seed=plan.seed)
        saved=second.spine.history(session)
        diagnostic=inspect(second.spine.db)
        return construct(proof_identity[0],proof_identity[1],session,request,
                         first,replayed,saved,diagnostic,exact_native=real)
