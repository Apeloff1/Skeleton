"""Read-only signed-source retrieval and context projection for local Jeeves.

This module composes the existing HMAC-approved, descriptor-anchored source
provider with the deterministic native-fabric lexical index and context
compiler. It does not open paths supplied by a model, grant tool permissions,
generate text, or produce an independent source-rights opinion.

Every selected citation is first verified against the canonical signed
manifest and must be rechecked against the actual original bytes immediately
before any native use. Selected excerpts stay UNTRUSTED DATA, never system
instructions. All omissions are explicit in public diagnostic receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity,
)
from skeleton.jeeves.agent.native_signed_evidence import (
    NativeSignedEvidenceProvider, SignedEvidenceHold,
)
from .contracts import ContractHold, Scope, digest, exact_integer, identifier, text
from .context import Segment, ContextEnvelope, build_context
from .retrieval import SourceChunk, BoundedLexicalIndex, split_source


class SignedRetrievalHold(ContractHold):
    """An original-source, scope, context or citation boundary was rejected."""


@dataclass(frozen=True, slots=True)
class OriginalSpan:
    source_id: str
    document_sha256: str
    passage_sha256: str
    excerpt_start_char: int
    excerpt_end_char: int
    local_chunk_id: str
    chunk_sha256: str
    chunk_start_byte: int
    chunk_end_byte: int
    rank: int

    def __post_init__(self):
        identifier(self.source_id, "source")
        identifier(self.local_chunk_id, "chunk")
        for value in (
            self.document_sha256, self.passage_sha256, self.chunk_sha256,
        ):
            digest(value)
        for value in (
            self.excerpt_start_char, self.excerpt_end_char,
            self.chunk_start_byte, self.chunk_end_byte,
        ):
            exact_integer(value, maximum=2**40)
        if (self.excerpt_end_char < self.excerpt_start_char
            or self.chunk_end_byte <= self.chunk_start_byte):
            raise SignedRetrievalHold("invalid original-source quote offsets")
        exact_integer(self.rank, minimum=1, maximum=512)

    def public_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_source_span.v1",
            "source_id": self.source_id,
            "document_sha256": self.document_sha256,
            "passage_sha256": self.passage_sha256,
            "chunk_sha256": self.chunk_sha256,
            "chunk_start_byte": self.chunk_start_byte,
            "chunk_end_byte": self.chunk_end_byte,
            "rank": self.rank,
            "independent_rights_review": False,
            "semantic_truth_proven": False,
        }


@dataclass(frozen=True, slots=True)
class SignedProjection:
    query_sha256: str
    scope_sha256: str
    selection_receipt_sha256: str
    original_source_receipts: tuple[tuple[str, str], ...]
    spans: tuple[OriginalSpan, ...]
    context: ContextEnvelope
    source_count: int
    omitted_source_ids: tuple[str, ...]

    def __post_init__(self):
        for value in (
            self.query_sha256, self.scope_sha256,
            self.selection_receipt_sha256,
        ):
            digest(value)
        if not isinstance(self.context, ContextEnvelope):
            raise SignedRetrievalHold("typed context compilation required")
        if self.context.scope_sha256 != self.scope_sha256:
            raise SignedRetrievalHold("context belongs to different source principal")
        exact_integer(self.source_count, minimum=1, maximum=6)
        if len({x.source_id for x in self.spans}) > self.source_count:
            raise SignedRetrievalHold("selected source count exceeds authenticated receipt")
        if len(self.original_source_receipts) != self.source_count:
            raise SignedRetrievalHold("unmatched signed manifest source count")

    def diagnostic(self) -> dict[str, object]:
        return {
            "schema": "jeeves.signed_retrieval_projection.v1",
            "scope_sha256": self.scope_sha256,
            "query_sha256": self.query_sha256,
            "selection_receipt_sha256": self.selection_receipt_sha256,
            "selected_span_count": len(self.spans),
            "source_count": self.source_count,
            "omitted_source_ids": list(self.omitted_source_ids),
            "context": self.context.to_public_record(),
            "spans": [item.public_record() for item in self.spans],
            "model_executed": False,
            "independent_rights_review": False,
            "release_certified": False,
        }


class NativeSignedRetrieval:
    """Single-owner, ephemeral retrieval over original bytes, never a cache.

    The original provider retains the exact signed source selection in
    thread-local custody. This wrapper does not parallelize or persist
    selections between its selection and commit-time recheck.
    """

    def __init__(
        self,
        provider: NativeSignedEvidenceProvider,
        identity: Identity,
        *, workspace: str = "default",
        maximum_chunks: int = 48,
        maximum_selected: int = 6,
    ):
        if not isinstance(provider, NativeSignedEvidenceProvider):
            raise SignedRetrievalHold("signed and bound source provider required")
        if not isinstance(identity, Identity):
            raise SignedRetrievalHold("typed native model identity required")
        provider._confirm_identity(identity)
        identifier(workspace, "workspace")
        exact_integer(maximum_chunks, minimum=1, maximum=256)
        exact_integer(maximum_selected, minimum=1, maximum=6)
        self.provider = provider
        self.identity = identity
        self.scope = Scope(
            identity.tenant, identity.subject,
            identity.model_sha256, identity.tokenizer_sha256,
            workspace=workspace,
        )
        self.maximum_chunks = maximum_chunks
        self.maximum_selected = min(maximum_selected, provider.maximum_sources)

    def select(
        self, query: str, *, host_system_instruction: str,
        context_tokens: int,
        reserved_output_tokens: int,
    ) -> SignedProjection:
        text(query, maximum_bytes=4096)
        text(host_system_instruction, maximum_bytes=8192)
        exact_integer(context_tokens, minimum=128, maximum=131072)
        exact_integer(reserved_output_tokens, minimum=1, maximum=8192)
        if context_tokens <= reserved_output_tokens:
            raise SignedRetrievalHold("output reservation cannot consume context")
        self.provider._confirm_identity(self.identity)
        original = self.provider(self.identity, query)
        if not 1 <= len(original) <= self.maximum_selected:
            raise SignedRetrievalHold("source selection exceeds operator allowlist")
        selection = self.provider.last_selection()
        if (type(selection) is not dict or
            selection.get("schema") != "jeeves.native_signed_source_selection.v1"):
            raise SignedRetrievalHold("signed source receipt missing after retrieval")
        source_receipts = tuple(
            (entry.source_id, entry.sha256) for entry in original
        )
        if len(set(x[0] for x in source_receipts)) != len(source_receipts):
            raise SignedRetrievalHold("signed source has duplicate IDs")
        if selection["source_count"] != len(original):
            raise SignedRetrievalHold("signed source selection count changed")
        if tuple((x["source_id"], x["passage_sha256"])
                 for x in selection["selected_passage_digests"]) != source_receipts:
            raise SignedRetrievalHold("source provider and selection receipt disagree")
        chunks = []
        owners = {}
        for excerpt in original:
            if (excerpt.owner_tenant != self.identity.tenant or
                excerpt.owner_subject != self.identity.subject or
                excerpt.document_sha256 is None or
                excerpt.trust != "local-document"):
                raise SignedRetrievalHold("unsigned or foreign source evidence")
            source_raw = excerpt.content.encode("utf-8", "strict")
            if sha256(source_raw).hexdigest() != excerpt.sha256:
                raise SignedRetrievalHold("original passage digest differs")
            # The signed original is the only source authority. Splitting
            # *already selected excerpts* is only a local ranking operation.
            selected = split_source(
                excerpt.content,
                source_id=excerpt.source_id,
                scope_sha256=self.scope.binding,
                chunk_bytes=1024, overlap_bytes=128,
                maximum_chunks=self.maximum_chunks,
            )
            chunks.extend(selected)
            owners[excerpt.source_id] = excerpt
            if len(chunks) > self.maximum_chunks:
                raise SignedRetrievalHold("source projection exceeds bounded chunk inventory")
        index = BoundedLexicalIndex(
            tuple(chunks), scope_sha256=self.scope.binding,
            maximum_chunks=self.maximum_chunks,
        )
        hits = index.search(query, maximum_results=min(len(chunks), self.maximum_selected))
        if not hits:
            raise SignedRetrievalHold("original source selection produced no lexical evidence")
        context_segments = [
            Segment(
                segment_id="system",
                content=host_system_instruction,
                kind="system",
                source_sha256=sha256(host_system_instruction.encode("utf-8")).hexdigest(),
                scope_sha256=self.scope.binding,
                priority=1000000, mandatory=True,
                trusted_instruction=True,
            ),
            Segment(
                segment_id="user",
                content=query, kind="user",
                source_sha256=sha256(query.encode("utf-8")).hexdigest(),
                scope_sha256=self.scope.binding,
                priority=100000, mandatory=True,
                trusted_instruction=False,
            ),
        ]
        spans = []
        for hit in hits:
            chunk = hit.chunk
            origin_id = chunk.chunk_id.split(":c", 1)[0]
            if origin_id not in owners:
                raise SignedRetrievalHold("chunk cannot be traced to signed passage")
            original_source = owners[origin_id]
            raw=chunk.content.encode("utf-8","strict")
            offset=chunk.offset_bytes
            spans.append(OriginalSpan(
                source_id=origin_id,
                document_sha256=original_source.document_sha256,
                passage_sha256=original_source.sha256,
                excerpt_start_char=original_source.start,
                excerpt_end_char=original_source.end,
                local_chunk_id=chunk.chunk_id,
                chunk_sha256=sha256(raw).hexdigest(),
                chunk_start_byte=offset,
                chunk_end_byte=offset+len(raw),
                rank=hit.rank,
            ))
            context_segments.append(Segment(
                segment_id=chunk.chunk_id,
                content=chunk.content,
                kind="source",
                source_sha256=sha256(raw).hexdigest(),
                scope_sha256=self.scope.binding,
                priority=max(0,1000-hit.rank), mandatory=False,
                trusted_instruction=False,
            ))
        context=build_context(
            context_segments,scope_sha256=self.scope.binding,
            input_ceiling_tokens=context_tokens,
            reserved_output_tokens=reserved_output_tokens,
        )
        included = {x.segment_id for x in context.selected}
        included_spans=tuple(x for x in spans if x.local_chunk_id in included)
        omitted=tuple(sorted({x.source_id for x in spans if x.local_chunk_id not in included}))
        # No cached original bytes are accepted at commit: this method must
        # also be invoked immediately prior to the native effect/receipt.
        self.provider.require_current(
            None,tuple({"source_id":sid,"sha256":sha} for sid,sha in source_receipts),
        )
        return SignedProjection(
            query_sha256=sha256(query.encode("utf-8")).hexdigest(),
            scope_sha256=self.scope.binding,
            selection_receipt_sha256=selection["source_receipt_sha256"],
            original_source_receipts=source_receipts,
            spans=included_spans,
            context=context,
            source_count=len(original),
            omitted_source_ids=omitted,
        )

    def recheck_before_native_use(self,projection:SignedProjection):
        if not isinstance(projection,SignedProjection):
            raise SignedRetrievalHold("typed signed projection required")
        if projection.scope_sha256!=self.scope.binding:
            raise SignedRetrievalHold("projection principal/model changed")
        self.provider._confirm_identity(self.identity)
        self.provider.require_current(
            None,tuple({"source_id":sid,"sha256":sha}
                       for sid,sha in projection.original_source_receipts),
        )
        return {
            "schema":"jeeves.signed_retrieval_recheck.v1",
            "source_receipt_sha256":projection.selection_receipt_sha256,
            "verified_original_sources":projection.source_count,
            "model_executed":False,
            "independent_license_review":False,
        }


__all__=["SignedRetrievalHold","OriginalSpan","SignedProjection","NativeSignedRetrieval"]
