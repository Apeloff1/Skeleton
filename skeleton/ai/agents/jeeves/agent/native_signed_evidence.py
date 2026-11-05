"""Bridge authenticated original sources into the canonical native evidence contract.

Signed source files and scopes are owned by the existing offline-cognition
custody layer. This adapter is a pure, bounded composition: it does not create
a memory store, re-sign sources, authorize source rights, fetch web content or
make a new model call. It re-reads original bytes at both source selection and
the native commit boundary to fence source swaps and expired operator approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import threading
import time
from typing import Callable

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import (
    CognitionError, Scope, hash_bytes, identifier, text,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.grounded_work import (
    GroundedPrompt, prepare, verify_prepared,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evidence_pipeline import (
    EvidenceIndex,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    SignedSourceManifest, ingest_authorized_sources, verify_signed_manifest,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.context import (
    Evidence,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity,
)


class SignedEvidenceHold(ValueError):
    """Original source contents cannot be trusted in the current epoch."""


@dataclass(frozen=True, slots=True)
class SourceSelectionReceipt:
    scope_sha256: str
    prompt_sha256: str
    source_receipt_sha256: str
    selected_passage_digests: tuple[tuple[str, str], ...]
    issued_at: int
    expires_at: int
    source_count: int

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_signed_source_selection.v1",
            "scope_sha256": self.scope_sha256,
            "prompt_sha256": self.prompt_sha256,
            "source_receipt_sha256": self.source_receipt_sha256,
            "selected_passage_digests": [
                {"source_id": source, "passage_sha256": digest}
                for source, digest in self.selected_passage_digests
            ],
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "source_count": self.source_count,
            "operator_rights_attested": True,
            "independent_license_review": False,
            "model_execution_witnessed": False,
        }


class NativeSignedEvidenceProvider:
    """One immutable signed-source identity, revetted before every native commit.

    Source byte safety and rights declarations are delegated to the original
    signed manifest code. Every invocation builds an ephemeral retrieval
    projection from *fresh* bytes rather than trusting an in-memory model
    answer, mutable cache, unsworn filesystem path or stale source list.
    """

    def __init__(
        self,
        *,
        source_root: str | Path,
        raw_manifest: bytes,
        operator_key: bytes,
        scope: Scope,
        maximum_sources: int = 4,
        passage_bytes: int = 1024,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(source_root, (str, Path)):
            raise SignedEvidenceHold("explicit private source root required")
        path = Path(source_root)
        if not path.is_absolute():
            raise SignedEvidenceHold("private source root must be absolute")
        if type(raw_manifest) is not bytes or len(raw_manifest) > 32768:
            raise SignedEvidenceHold("signed manifest bytes exceed budget")
        if type(operator_key) is not bytes or not 32 <= len(operator_key) <= 4096:
            raise SignedEvidenceHold("bounded independent operator key required")
        if not isinstance(scope, Scope):
            raise SignedEvidenceHold("typed source principal and model scope required")
        if type(maximum_sources) is not int or not 1 <= maximum_sources <= 6:
            raise SignedEvidenceHold("source count outside native ceiling")
        if type(passage_bytes) is not int or not 16 <= passage_bytes <= 4096:
            raise SignedEvidenceHold("source passage exceeds bounded native capacity")
        if not callable(clock):
            raise SignedEvidenceHold("monotonic-independent source clock required")
        manifest = verify_signed_manifest(
            raw_manifest, operator_key, observed_at=int(clock()),
        )
        scope.assert_same(manifest.scope)
        self._source_root = path
        self._raw_manifest = raw_manifest
        self._operator_key = operator_key
        self.scope = scope
        self.maximum_sources = maximum_sources
        self.passage_bytes = passage_bytes
        self.clock = clock
        self.manifest_sha256 = sha256(raw_manifest).hexdigest()
        self._thread = threading.local()
        self._manifest = manifest

    def _fresh_index(self) -> tuple[SignedSourceManifest, EvidenceIndex]:
        at = int(self.clock())
        current = verify_signed_manifest(
            self._raw_manifest, self._operator_key, observed_at=at,
        )
        if current != self._manifest:
            raise SignedEvidenceHold("operator source authorization epoch changed")
        index = ingest_authorized_sources(
            self._source_root, current, scope=self.scope, observed_at=at,
        )
        return current, index

    def _confirm_identity(self, identity: Identity) -> None:
        if not isinstance(identity, Identity):
            raise SignedEvidenceHold("typed native execution principal required")
        if (identity.tenant, identity.subject,
            identity.model_sha256, identity.tokenizer_sha256) != (
            self.scope.tenant, self.scope.subject,
            self.scope.model_sha256, self.scope.tokenizer_sha256
        ):
            raise SignedEvidenceHold("signed source scope does not match active model")

    def __call__(self, identity: Identity, prompt: str) -> tuple[Evidence, ...]:
        """Assemble original source excerpts without granting output authority."""
        self._confirm_identity(identity)
        text(prompt, maximum=4096)
        manifest, index = self._fresh_index()
        prepared = prepare(
            index, self.scope, prompt, mode="lexical",
            limit=min(self.maximum_sources, len(manifest.sources)),
            max_prompt_bytes=32768,
            window_bytes=self.passage_bytes,
            grounding_required=True,
        )
        verify_prepared(prepared, index)
        passages: list[Evidence] = []
        for span in prepared.spans:
            original = index.documents[span.source_id]
            before = original.payload[:span.start].decode("utf-8", "strict")
            quoted = original.payload[span.start:span.end].decode("utf-8", "strict")
            passages.append(Evidence(
                source_id=span.source_id,
                revision=0,
                content=quoted,
                sha256=span.passage_sha256,
                owner_tenant=identity.tenant,
                owner_subject=identity.subject,
                document_sha256=span.source_sha256,
                start=len(before),
                end=len(before) + len(quoted),
                trust="local-document",
                rights="signed-operator-attestation-not-independent-license-proof",
            ))
        selection = SourceSelectionReceipt(
            scope_sha256=self.scope.digest(),
            prompt_sha256=prepared.prompt_sha256,
            source_receipt_sha256=prepared.source_receipt_sha256,
            selected_passage_digests=tuple(
                (span.source_id, span.passage_sha256) for span in prepared.spans
            ),
            issued_at=manifest.issued_at,
            expires_at=manifest.expires_at,
            source_count=len(prepared.spans),
        )
        self._thread.selected = selection
        self._thread.last_question = prompt
        return tuple(passages)

    def require_current(self, conn, source_receipts: tuple[dict, ...]) -> None:
        """Fail closed inside the existing spine transaction before commit.

        This method has no authority to mutate the supplied connection;
        it proves that the exact selected passage bytes and scope remain
        independently authentic at commit time. If any input/source changes,
        the native request is left pending for explicit reconciliation.
        """
        selected = getattr(self._thread, "selected", None)
        question = getattr(self._thread, "last_question", None)
        if not isinstance(selected, SourceSelectionReceipt) or not isinstance(question, str):
            raise SignedEvidenceHold("unmatched or cross-thread source selection")
        if type(source_receipts) not in (tuple, list):
            raise SignedEvidenceHold("native context source receipts missing")
        expected = dict(selected.selected_passage_digests)
        actual: dict[str, str] = {}
        for item in source_receipts:
            if type(item) is not dict:
                raise SignedEvidenceHold("invalid native source receipt")
            source_id = item.get("source_id")
            digest = item.get("sha256")
            if type(source_id) is not str or type(digest) is not str:
                raise SignedEvidenceHold("native source receipt identity missing")
            if source_id in actual:
                raise SignedEvidenceHold("duplicate native source receipt")
            actual[source_id] = digest
        if actual != expected:
            raise SignedEvidenceHold("native projected source selection differs from signed source")
        current, index = self._fresh_index()
        if current.issued_at != selected.issued_at or current.expires_at != selected.expires_at:
            raise SignedEvidenceHold("source authorization revision changed")
        reconstructed = prepare(
            index, self.scope, question, mode="lexical",
            limit=min(self.maximum_sources, len(current.sources)),
            max_prompt_bytes=32768,
            window_bytes=self.passage_bytes,
            grounding_required=True,
        )
        verify_prepared(reconstructed, index)
        if (reconstructed.source_receipt_sha256 != selected.source_receipt_sha256
            or reconstructed.prompt_sha256 != selected.prompt_sha256
            or tuple((span.source_id, span.passage_sha256)
                     for span in reconstructed.spans) != selected.selected_passage_digests):
            raise SignedEvidenceHold("signed source was replaced, revoked or re-ranked before commit")

    def last_selection(self) -> dict[str, object] | None:
        value = getattr(self._thread, "selected", None)
        return value.to_record() if isinstance(value, SourceSelectionReceipt) else None


def attach_signed_native_evidence(worker, provider: NativeSignedEvidenceProvider):
    """Install an existing ExecutionSpine evidence callback, never a new owner."""
    if not isinstance(provider, NativeSignedEvidenceProvider):
        raise SignedEvidenceHold("signed source provider required")
    identity = getattr(getattr(worker, "spine", None), "identity", None)
    provider._confirm_identity(identity)
    if getattr(worker.spine, "evidence_provider", None) is not None:
        raise SignedEvidenceHold("native evidence provider already configured")
    worker.spine.evidence_provider = provider
    return worker


__all__ = [
    "SignedEvidenceHold", "SourceSelectionReceipt",
    "NativeSignedEvidenceProvider", "attach_signed_native_evidence",
]
