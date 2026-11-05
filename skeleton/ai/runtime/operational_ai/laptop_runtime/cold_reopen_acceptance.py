"""A real cold-reopen check of the canonical native GGUF and SQLite spine.

This uses the *same* source-verified activate_checked() routine twice. The
first installed worker is closed before a second independently admitted
native worker reads its committed turn from the existing principal-bound
SQLite database. No synthetic generation, second inference, migration,
network provider, memory/tool grant or implicit recovery is permitted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .contracts import identifier, utf8, refuse
from .preflight import validate_native_shape
from .identity import ActiveModel
from .startup import activate_checked
from .first_turn_acceptance import run as first_turn
from .installed_witness import require_activated_source
from .source_contract import valid_source_snapshot
from .replay_probe import inspect_replay


def run(
    *, model_root: Path, state_dir: Path, tenant: str, subject: str,
    prompt: str, approved: bool = False, n_ctx: int = 2048,
    max_new_tokens: int = 256, n_threads: int = 4,
    gpu_layers: int = 0, capacity_root: Path | None = None,
    capacity_slots: int = 1, capacity_budget_bytes: int = 8_000_000_000,
    inference_ms: int = 90000,
    publisher: Callable[[object, object, dict[str, object]], None]
    | None = None,
) -> dict[str, object]:
    """Witness one native turn, terminate it, then replay after cold startup.

    The operator must explicitly approve two local model activations. A
    valid source receipt is rechecked on BOTH activations; a changed model,
    tokenizer, owner, source archive or SQLite answer denies qualification.
    """
    if approved is not True:
        refuse("explicit native cold-reopen acceptance approval required")
    if publisher is not None and not callable(publisher):
        refuse("native output publisher must be callable")
    if (not isinstance(model_root, Path) or not model_root.is_absolute()
            or ".." in model_root.parts or chr(0) in str(model_root)):
        refuse("absolute private installed model root required")
    if (not isinstance(state_dir, Path) or not state_dir.is_absolute()
            or ".." in state_dir.parts or chr(0) in str(state_dir)):
        refuse("absolute principal-bound SQLite root required")
    if capacity_root is not None and (
        not isinstance(capacity_root, Path) or not capacity_root.is_absolute()
        or ".." in capacity_root.parts or chr(0) in str(capacity_root)
    ):
        refuse("absolute private capacity root required")
    tenant = identifier(tenant, "tenant")
    subject = identifier(subject, "subject")
    # All input errors and basic device-shape errors must be held before
    # even the first model activation or durable SQLite write.
    prompt = utf8(prompt, maximum=32768)
    validate_native_shape(
        n_ctx=n_ctx, max_new_tokens=max_new_tokens, n_threads=n_threads,
        gpu_layers=gpu_layers, capacity_slots=capacity_slots,
        capacity_budget_bytes=capacity_budget_bytes,
        inference_ms=inference_ms,
    )
    options = {
        "model_root": model_root, "state_dir": state_dir,
        "tenant": tenant, "subject": subject, "n_ctx": n_ctx,
        "max_new_tokens": max_new_tokens, "n_threads": n_threads,
        "gpu_layers": gpu_layers, "capacity_root": capacity_root,
        "capacity_slots": capacity_slots,
        "capacity_budget_bytes": capacity_budget_bytes, "isolated": True,
        "inference_ms": inference_ms,
    }
    stack, worker, installed = activate_checked(**options)
    with stack:
        # The installed-model digest alone is not an authorization boundary:
        # a different tenant/subject may use identical model weights.
        # Reject a worker substituted after activation before SQLite creates
        # any durable session or observes a private operator prompt.
        first_principal = ActiveModel.from_supervisor(worker)
        if (first_principal.tenant, first_principal.subject) != (tenant, subject):
            refuse("first native worker belongs to another principal")
        first = first_turn(
            worker, prompt=prompt, approved=True,
            installed_receipt=installed, require_real=True,
        )
        if (first.get("native_model_observed") is not True
                or first.get("installed_source_bound") is not True
                or first.get("replayed_without_generation") is not True
                or first.get("release_certified") is not False):
            refuse("first native source/SQLite generation not qualified")
        source = first["installed_source"]
        session = first["session_id"]
        request = first["request_id"]
        digest = first["output_sha256"]
    # The first context is completely closed before the following source
    # and device admission. Crash/pending custody is never retried.
    second_stack, second_worker, second_installed = activate_checked(**options)
    if second_stack is stack:
        refuse("cold native reopen reused a closed activation context")
    with second_stack:
        # A second independently activated context must always close, even
        # if the adapter mistakenly returns the first worker instance.
        if second_worker is worker:
            refuse("cold native reopen must use an independently activated worker")
        reopened_source = require_activated_source(
            second_worker, second_installed,
        )
        if (not valid_source_snapshot(reopened_source, first_principal)
                or reopened_source != source):
            refuse("installed source changed across cold native restart")
        bound = ActiveModel.from_supervisor(second_worker)
        if (bound.tenant, bound.subject) != (tenant, subject):
            refuse("cold native worker belongs to another principal")
        if bound != first_principal:
            refuse("cold native model/tokenizer/principal changed")
        if (bound.model_sha256 != first["model_sha256"]
                or bound.tokenizer_sha256 != first["tokenizer_sha256"]):
            refuse("cold native model/tokenizer changed")
        # Only read the second process's SQLite committed record. Do NOT
        # call native generation again, even when replay is missing.
        replay = inspect_replay(
            second_worker, session, request, prompt,
            seed=17, temperature=0.8,
        )
        if (replay.get("committed") is not True
                or replay.get("no_second_generation") is not True
                or replay.get("output_sha256") != digest):
            refuse("cold native SQLite replay not authoritative")
        if ActiveModel.from_supervisor(second_worker) != bound:
            refuse("cold native principal changed before output report")
        # Read the actual live child and lease one more time AFTER the SQLite
        # snapshot. A backend that dies, is cancelled or changes its source
        # mid-replay must not yield a successful cold-reopen witness.
        final_source = require_activated_source(
            second_worker, second_installed,
        )
        if (not valid_source_snapshot(final_source, bound)
                or final_source != source):
            refuse("native source or resource lease changed after replay")
        record = {
            "schema": "laptop-native-cold-reopen-e2e.v1",
            "session_id": session, "request_id": request,
            "model_sha256": first["model_sha256"],
            "tokenizer_sha256": first["tokenizer_sha256"],
            "output_sha256": digest,
            "first_turn_generated_tokens": first["generated_tokens"],
            "source_verified_twice": True,
            "sqlite_replay_after_cold_reopen": True,
            "second_generation_attempted": False,
            "private_prompt_disclosed": False,
            "physical_device_qualified": False,
            "release_certified": False,
        }
        # The second live, independently admitted native worker owns
        # publication. Output after stack teardown is not source-verified.
        if publisher is not None:
            publisher(second_worker, second_installed, record)
        return record


__all__ = ["run"]
