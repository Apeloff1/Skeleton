"""Bind the desktop's strict native agent to OPERATOR-SIGNED local evidence.

This adapter composes the existing audited signed manifest preflight, original
byte custody, HMAC scope, expiry, source tool and native GGUF identity. It does
not invent a second signing mechanism, copy sources into another database,
grant filesystem writes, or let model text authorize a new tool.

A desktop source grant is a two-phase operation:
  1. Before native activation, verify the actual signed source manifest,
     independent key, original bytes and operator/tenant scope.
  2. After installed GGUF activation, prove the identical model/tokenizer
     source identity and bind exactly one read-only lookup tool.

Source reads are refreshed on selection and again at the signed evidence
boundary; the original provider retains all independent revocation gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import time
from typing import Any

from .contracts import identifier, refuse


class DesktopSignedSourceHold(ValueError):
    """Explicit signed source tool has no current host-owned authorization."""


@dataclass(frozen=True, slots=True)
class SignedSourceAdmission:
    """Private in-process startup material; NEVER returned through UI/IPC."""

    root: Path
    manifest: bytes
    key: bytes
    preflight: object
    maximum_sources: int
    maximum_tool_calls: int

    def __post_init__(self):
        from skeleton.jeeves.agent.native_source_preflight import NativeSourcePreflight
        if (
            not isinstance(self.root, Path)
            or not self.root.is_absolute()
            or ".." in self.root.parts
            or "\x00" in str(self.root)
        ):
            raise DesktopSignedSourceHold("absolute canonical signed source root required")
        if (
            type(self.manifest) is not bytes
            or not 1 <= len(self.manifest) <= 32768
            or type(self.key) is not bytes
            or not 32 <= len(self.key) <= 4096
            or type(self.preflight) is not NativeSourcePreflight
        ):
            raise DesktopSignedSourceHold("exact signed source preflight required")
        if (
            type(self.maximum_sources) is not int
            or not 1 <= self.maximum_sources <= 6
            or type(self.maximum_tool_calls) is not int
            or not 1 <= self.maximum_tool_calls <= 3
            or self.preflight.source_count > self.maximum_sources
        ):
            raise DesktopSignedSourceHold("signed source call/source quota exceeded")

    @property
    def public_metadata(self) -> dict[str, object]:
        """Finite source identity only; never include paths, key or snippets."""
        return {
            "schema": "jeeves.desktop.signed-source-admission.v1",
            "manifest_sha256": sha256(self.manifest).hexdigest(),
            "source_count": self.preflight.source_count,
            "maximum_tool_calls": self.maximum_tool_calls,
            "original_source_bytes_verified": True,
            "independent_legal_rights_verified": False,
            "model_source_matched": False,
            "source_tool_active": False,
            "release_certified": False,
        }


def preflight_signed_source(
    *, root: Path, manifest_path: Path,
    tenant: str, subject: str,
    maximum_sources: int = 4,
    maximum_tool_calls: int = 3,
) -> SignedSourceAdmission:
    """Read/verify operator-signed evidence BEFORE any GGUF loading occurs.

    The private key uses the existing SKELETON_OFFLINE_OPERATOR_KEY_HEX
    environment custody. It is never accepted in command-line options, GUI
    fields, prompt text, stdout, log strings, subprocess arguments or return
    values. A missing/invalid HMAC or original-source mismatch is a hold.
    """
    from skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli import (
        _environment_key, _read_private_manifest,
    )
    from skeleton.jeeves.agent.native_source_preflight import (
        verify_sources_before_native_start,
    )
    identifier(tenant, "source tenant")
    identifier(subject, "source subject")
    if (
        not isinstance(root, Path) or not root.is_absolute()
        or ".." in root.parts or "\x00" in str(root)
        or not isinstance(manifest_path, Path) or not manifest_path.is_absolute()
        or ".." in manifest_path.parts or "\x00" in str(manifest_path)
    ):
        raise DesktopSignedSourceHold("canonical absolute signed source locations required")
    if (
        type(maximum_sources) is not int or not 1 <= maximum_sources <= 6
        or type(maximum_tool_calls) is not int or not 1 <= maximum_tool_calls <= 3
    ):
        raise DesktopSignedSourceHold("finite source lookup allowance required")
    original = _read_private_manifest(manifest_path)
    key = _environment_key()
    preflight = verify_sources_before_native_start(
        source_root=root, signed_manifest=original, operator_key=key,
        tenant=tenant, subject=subject, observed_at=int(time.time()),
        maximum_sources=maximum_sources,
    )
    result = SignedSourceAdmission(
        root, original, key, preflight,
        maximum_sources=maximum_sources,
        maximum_tool_calls=maximum_tool_calls,
    )
    return result


@dataclass(frozen=True, slots=True)
class ActivatedSignedSource:
    """Source tool bound to one already-activated canonical GGUF worker."""

    bound_tool: object
    principal: object
    admission: SignedSourceAdmission

    def __post_init__(self):
        from skeleton.jeeves.agent.native_source_tool import BoundSignedSourceTool
        from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
        if (
            type(self.bound_tool) is not BoundSignedSourceTool
            or type(self.principal) is not Identity
            or type(self.admission) is not SignedSourceAdmission
            or self.bound_tool.identity != self.principal
        ):
            raise DesktopSignedSourceHold("signed tool not bound to canonical native principal")
        self.admission.preflight.verify_active_model(self.principal)

    def assert_current(self, worker: object) -> None:
        """Re-verify original source bytes/expiry AND model on each agent run."""
        from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
        if ActiveModel.from_supervisor(worker).model_sha256 != self.principal.model_sha256:
            raise DesktopSignedSourceHold("native GGUF source changed since approval")
        active = getattr(getattr(worker, "spine", None), "identity", None)
        if active != self.principal:
            raise DesktopSignedSourceHold("operator or tokenizer source changed")
        self.admission.preflight.verify_active_model(active)
        # The canonical provider owns HMAC expiry, original hashes, path
        # custody, legal-declaration bounds and current document inventory.
        manifest, _ = self.bound_tool.provider._fresh_index()
        if (
            manifest.issued_at != self.admission.preflight.issued_at
            or manifest.expires_at != self.admission.preflight.expires_at
        ):
            raise DesktopSignedSourceHold("operator-signed source epoch revoked")

    @property
    def public_metadata(self) -> dict[str, object]:
        data = self.admission.public_metadata
        data.update({
            "model_source_matched": True,
            "source_tool_active": True,
        })
        return data


def activate_signed_source(
    admission: SignedSourceAdmission,
    worker: object,
) -> ActivatedSignedSource:
    """Bind only the existing read-only source tool; grant nothing yet."""
    from skeleton.jeeves.agent.native_signed_evidence import (
        NativeSignedEvidenceProvider,
    )
    from skeleton.jeeves.agent.native_source_tool import (
        BoundSignedSourceTool, SourceToolPolicy,
    )
    if type(admission) is not SignedSourceAdmission:
        raise DesktopSignedSourceHold("typed approved signed source admission required")
    principal = getattr(getattr(worker, "spine", None), "identity", None)
    admission.preflight.verify_active_model(principal)
    provider = NativeSignedEvidenceProvider(
        source_root=admission.root,
        raw_manifest=admission.manifest,
        operator_key=admission.key,
        scope=admission.preflight.scope,
        maximum_sources=admission.maximum_sources,
        passage_bytes=1024,
        clock=time.time,
    )
    tool = BoundSignedSourceTool(
        provider, principal,
        policy=SourceToolPolicy(
            max_sources=admission.maximum_sources,
            maximum_excerpt_bytes=4096,
            maximum_answer_bytes=16384,
            timeout_seconds=10,
        ),
    )
    result = ActivatedSignedSource(tool, principal, admission)
    result.assert_current(worker)
    return result


__all__ = [
    "DesktopSignedSourceHold", "SignedSourceAdmission",
    "ActivatedSignedSource", "preflight_signed_source",
    "activate_signed_source",
]
