"""Read-only local AI startup readiness; no model load and no state repair.

This is an operator diagnostic, not a release / semantic quality attestation.
Model shard hashing and binding custody must pass independently before a
runtime can be described as ready to attempt genuine native inference.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
from typing import Any

from .identity import PrincipalBinding, inspect_binding
from ..install.doctor import inspect_installed_model
from ...context.sealed_memory.keys import load_key_file
from ...model.gguf.service import load_approved_manifest


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    state_bound: bool
    installed_model_verified: bool
    key_custody_verified: bool
    local_backend_importable: bool
    eligible_for_live_inference_attempt: bool
    model_sha256: str
    release_certified: bool = False

    def to_record(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


def inspect_readiness(model_root: str | Path, state_root: str | Path,
                      key_file: str | Path, *, tenant: str, user: str) -> ReadinessReport:
    """Refuse missing/unsafe inputs without creating or mutating anything."""
    model = inspect_installed_model(model_root)
    manifest = load_approved_manifest(model_root)
    binding = PrincipalBinding(tenant, user, model.model_sha256, model.model_sha256)
    inspect_binding(state_root, binding)
    # Material remains local; no plaintext key or derived secret is returned.
    load_key_file(key_file)
    backend_present = importlib.util.find_spec("llama_cpp") is not None
    return ReadinessReport(True, model.content_verified, True, backend_present,
                           bool(backend_present and model.content_verified),
                           manifest.model_sha256)
