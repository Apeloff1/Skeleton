"""Source-bound real laptop startup: approved installer receipt before GGUF activation.

This adds a missing installation-custody fence to the production activation
entry point; it does not weaken any existing process isolation or model cap.
"""
from __future__ import annotations
from pathlib import Path
from .contracts import refuse
from .identity import ActiveModel


def _require_private_absolute_path(value: object, label: str) -> None:
    """Refuse unsafe roots without resolving symlinks or reading any source.

    Descriptor-anchored installation and state ownership remain downstream
    authorities; this check only prevents misleading path spellings from
    reaching an installer probe or native startup in the first place.
    """
    if not isinstance(value, (str, Path)):
        refuse("absolute private " + label + " required")
    try:
        path = Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError("invalid private " + label + " type") from exc
    if (not path.is_absolute() or ".." in path.parts
            or chr(0) in str(value)):
        refuse("absolute private " + label + " required")



def activate_checked(*,model_root,state_dir,tenant,subject,
                     n_ctx=2048,max_new_tokens=256,n_threads=4,
                     gpu_layers=0,capacity_root=None,capacity_slots=1,
                     capacity_budget_bytes=8000000000,
                     isolated=True,inference_ms=90000):
    from skeleton.ai.runtime.operational_ai.deployment.install.doctor import inspect_installed_model
    from skeleton.ai.runtime.operational_ai.deployment.production.startup import activate
    from skeleton.ai.runtime.operational_ai.model.admission.paths import create_default_root
    from .contracts import identifier,nonnegative
    from .preflight import validate_native_shape
    identifier(tenant,"tenant");identifier(subject,"subject")
    _require_private_absolute_path(model_root, "model root")
    _require_private_absolute_path(state_dir, "SQLite state root")
    if capacity_root is not None:
        _require_private_absolute_path(capacity_root, "capacity root")
    validate_native_shape(
        n_ctx=n_ctx, max_new_tokens=max_new_tokens,
        n_threads=n_threads, gpu_layers=gpu_layers,
        capacity_budget_bytes=capacity_budget_bytes,
        capacity_slots=capacity_slots, inference_ms=inference_ms,
    )
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
    # Each hash is read from the *actual installed bytes* in the source-bound
    # installer receipt before any model backend can be activated.
    verified=inspect_installed_model(model_root)
    if (verified.content_verified is not True
        or verified.rights_approved is not True
        or not verified.archive_sha256 or not verified.source_sha):
        refuse("real installed model source or rights approval absent")
    root=capacity_root if capacity_root is not None else create_default_root()
    _require_private_absolute_path(root, "effective capacity root")
    stack,worker=activate(model_root=model_root,state_dir=state_dir,
                          tenant=tenant,subject=subject,n_ctx=n_ctx,
                          max_new_tokens=max_new_tokens,n_threads=n_threads,
                          gpu_layers=gpu_layers,isolated=True,
                          inference_ms=inference_ms,capacity_root=root,
                          capacity_slots=capacity_slots,
                          capacity_budget_bytes=capacity_budget_bytes)
    try:
        expected=verified.model_sha256
        active=ActiveModel.from_supervisor(worker)
        if (active.tenant, active.subject)!=(tenant,subject):
            refuse("activated native worker belongs to another principal")
        if active.model_sha256!=expected:
            refuse("activated model differs from trusted installer receipt")
        return stack,worker,verified
    except BaseException:
        stack.close()
        raise
