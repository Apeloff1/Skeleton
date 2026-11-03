"""Source-bound real laptop startup: approved installer receipt before GGUF activation.

This adds a missing installation-custody fence to the production activation
entry point; it does not weaken any existing process isolation or model cap.
"""
from __future__ import annotations
from pathlib import Path
from .contracts import refuse

def activate_checked(*,model_root,state_dir,tenant,subject,
                     n_ctx=2048,max_new_tokens=256,n_threads=4,
                     gpu_layers=0,capacity_root=None,capacity_slots=1,
                     capacity_budget_bytes=8000000000,
                     isolated=True,inference_ms=90000):
    from skeleton.ai.runtime.operational_ai.deployment.install.doctor import inspect_installed_model
    from skeleton.ai.runtime.operational_ai.deployment.production.startup import activate
    from skeleton.ai.runtime.operational_ai.model.admission.paths import create_default_root
    from .contracts import identifier,nonnegative
    identifier(tenant,"tenant");identifier(subject,"subject")
    for name,value,ceiling in (
        ("context",n_ctx,131072),("output tokens",max_new_tokens,8192),
        ("threads",n_threads,64),("gpu layers",gpu_layers,128),
        ("capacity slots",capacity_slots,64),
        ("capacity bytes",capacity_budget_bytes,20000000000),
        ("inference timeout",inference_ms,600000)):
        nonnegative(value,maximum=ceiling)
    if n_ctx<128 or not 1<=max_new_tokens<n_ctx or n_threads<1:
        refuse("impossible local native resource configuration")
    if type(isolated) is not bool or not isolated:
        refuse("first-laptop-use requires a killable isolated native backend")
    if type(model_root) not in (str,Path) or type(state_dir) not in (str,Path):
        refuse("explicit local model and state paths required")
    # Each hash is read from the *actual installed bytes* in the source-bound
    # installer receipt before any model backend can be activated.
    verified=inspect_installed_model(model_root)
    if (not verified.content_verified or not verified.rights_approved
        or not verified.archive_sha256 or not verified.source_sha):
        refuse("real installed model source or rights approval absent")
    root=capacity_root if capacity_root is not None else create_default_root()
    stack,worker=activate(model_root=model_root,state_dir=state_dir,
                          tenant=tenant,subject=subject,n_ctx=n_ctx,
                          max_new_tokens=max_new_tokens,n_threads=n_threads,
                          gpu_layers=gpu_layers,isolated=True,
                          inference_ms=inference_ms,capacity_root=root,
                          capacity_slots=capacity_slots,
                          capacity_budget_bytes=capacity_budget_bytes)
    try:
        expected=verified.model_sha256
        active=worker.spine.identity
        if active.model_sha256!=expected or worker.spine.backend.model_digest!=expected:
            refuse("activated model differs from trusted installer receipt")
        if active.tokenizer_sha256!=worker.spine.backend.tokenizer_digest:
            refuse("activated tokenizer identity changed")
        return stack,worker,verified
    except BaseException:
        stack.close()
        raise
