"""Trust-aware bounded context assembly with RAM project recall."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable

from skeleton.kernel.ram.context_plane import (
    ContextMemoryPlane,
    get_default_context_memory_plane,
)

from .contracts import (
    AssistantContractError,
    AssistantRequest,
    CompiledContext,
    ContextCandidate,
    TrustTier,
    digest_json,
)


_TRUST_ORDER = {
    TrustTier.TRUSTED_CONTROL: 0,
    TrustTier.AUTHORIZED_USER: 1,
    TrustTier.PRIVATE_RETRIEVED: 2,
    TrustTier.PUBLIC_EVIDENCE: 3,
    TrustTier.TOOL_OUTPUT: 4,
    TrustTier.MODEL_DERIVED: 5,
}
_MEMORY_TRUST = frozenset(TrustTier) - {TrustTier.TRUSTED_CONTROL}


def _scope(request: AssistantRequest) -> str | None:
    for name in ("project_id", "workspace_id", "repository_id"):
        value = request.metadata.get(name)
        if isinstance(value, str) and value.strip():
            raw = f"{request.tenant_id}\n{name}\n{value.strip()}"
            return "assistant-context:" + hashlib.sha256(raw.encode()).hexdigest()
    if request.conversation_id:
        raw = f"{request.tenant_id}\nconversation_id\n{request.conversation_id}"
        return "assistant-context:" + hashlib.sha256(raw.encode()).hexdigest()
    return None


def _candidate_key(candidate: ContextCandidate) -> str:
    return hashlib.sha256(candidate.source_id.encode()).hexdigest()


def _encode(candidate: ContextCandidate) -> bytes:
    return json.dumps(
        {
            "v": 1,
            "source_id": candidate.source_id,
            "content": candidate.content,
            "trust": candidate.trust.value,
            "relevance": candidate.relevance,
            "priority": candidate.priority,
            "provenance": list(candidate.provenance),
            "observed_at": candidate.observed_at.isoformat(),
            "expires_at": (
                candidate.expires_at.isoformat() if candidate.expires_at else None
            ),
            "instruction_like": candidate.contains_instruction_like_text,
            "data_class": candidate.data_class,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _decode(raw: bytes) -> ContextCandidate:
    value = json.loads(raw.decode())
    if value.get("v") != 1:
        raise ValueError("unsupported RAM context schema")
    return ContextCandidate(
        source_id=value["source_id"],
        content=value["content"],
        trust=TrustTier(value["trust"]),
        relevance=float(value["relevance"]),
        priority=int(value["priority"]),
        provenance=tuple(value["provenance"]),
        observed_at=datetime.fromisoformat(value["observed_at"]),
        expires_at=(
            datetime.fromisoformat(value["expires_at"])
            if value.get("expires_at") else None
        ),
        contains_instruction_like_text=bool(value.get("instruction_like")),
        data_class=value["data_class"],
    )


class ContextCompiler:
    """Compile context without allowing cached evidence to become authority."""

    def __init__(
        self,
        *,
        reserve_control_chars: int = 8_192,
        max_candidates: int = 512,
        memory_plane: ContextMemoryPlane | None = None,
        use_ram_context: bool = True,
    ) -> None:
        if reserve_control_chars < 0:
            raise ValueError("reserve_control_chars must be non-negative")
        if not 1 <= max_candidates <= 4096:
            raise ValueError("max_candidates outside hard bounds")
        self.reserve_control_chars = reserve_control_chars
        self.max_candidates = max_candidates
        self.use_ram_context = bool(use_ram_context)
        self.memory_plane = (
            memory_plane
            if memory_plane is not None
            else (get_default_context_memory_plane() if use_ram_context else None)
        )

    @staticmethod
    def _dedupe(candidates: Iterable[ContextCandidate]) -> list[ContextCandidate]:
        by_content: dict[str, ContextCandidate] = {}
        for candidate in candidates:
            if not isinstance(candidate, ContextCandidate):
                raise TypeError("context candidates must be ContextCandidate")
            key = hashlib.sha256(candidate.content.encode()).hexdigest()
            prior = by_content.get(key)
            rank = (
                _TRUST_ORDER[candidate.trust],
                -candidate.priority,
                -candidate.relevance,
                candidate.source_id,
            )
            if prior is None:
                by_content[key] = candidate
            else:
                old = (
                    _TRUST_ORDER[prior.trust],
                    -prior.priority,
                    -prior.relevance,
                    prior.source_id,
                )
                if rank < old:
                    by_content[key] = candidate
        return list(by_content.values())

    @staticmethod
    def _sort_key(candidate: ContextCandidate) -> tuple[object, ...]:
        return (
            _TRUST_ORDER[candidate.trust],
            -candidate.priority,
            -candidate.relevance,
            -candidate.observed_at.timestamp(),
            candidate.source_id,
        )

    def _remember(self, namespace: str, candidates: Iterable[ContextCandidate]) -> None:
        if self.memory_plane is None:
            return
        for candidate in candidates:
            if candidate.trust not in _MEMORY_TRUST:
                continue
            try:
                self.memory_plane.put(
                    namespace,
                    _candidate_key(candidate),
                    _encode(candidate),
                    priority=candidate.priority,
                )
            except (MemoryError, OSError, RuntimeError, TypeError, ValueError):
                pass

    def _recall(
        self,
        namespace: str,
        *,
        now: datetime,
        allow_restricted: bool,
        limit: int,
    ) -> list[ContextCandidate]:
        if self.memory_plane is None or limit <= 0:
            return []
        output: list[ContextCandidate] = []
        try:
            entries = self.memory_plane.scan(namespace, limit=limit)
        except (OSError, RuntimeError, TypeError, ValueError):
            return []
        for entry, raw in entries:
            try:
                candidate = _decode(raw)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeError):
                self.memory_plane.delete(namespace, entry.logical_key)
                continue
            if candidate.trust not in _MEMORY_TRUST:
                self.memory_plane.delete(namespace, entry.logical_key)
                continue
            if candidate.is_expired(now):
                self.memory_plane.delete(namespace, entry.logical_key)
                continue
            if candidate.data_class == "restricted" and not allow_restricted:
                continue
            output.append(candidate)
        return output

    def compile(
        self,
        request: AssistantRequest,
        candidates: Iterable[ContextCandidate],
        *,
        now: datetime | None = None,
        allow_restricted: bool = False,
    ) -> CompiledContext:
        if not isinstance(request, AssistantRequest):
            raise TypeError("request must be AssistantRequest")
        instant = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)

        normalized = self._dedupe(candidates)
        if len(normalized) > self.max_candidates:
            raise AssistantContractError("context candidate count exceeds hard bound")

        omitted: list[str] = []
        current: list[ContextCandidate] = []
        for candidate in normalized:
            if candidate.is_expired(instant):
                omitted.append(candidate.source_id)
            elif candidate.data_class == "restricted" and not allow_restricted:
                omitted.append(candidate.source_id)
            else:
                current.append(candidate)

        namespace = _scope(request) if self.use_ram_context else None
        if namespace and self.memory_plane is not None:
            self._remember(namespace, current)
            recalled = self._recall(
                namespace,
                now=instant,
                allow_restricted=allow_restricted,
                limit=max(1, self.max_candidates - len(current)),
            ) if len(current) < self.max_candidates else []
            eligible = self._dedupe((*current, *recalled))[: self.max_candidates]
        else:
            eligible = current
        eligible.sort(key=self._sort_key)

        controls = [x for x in eligible if x.trust is TrustTier.TRUSTED_CONTROL]
        others = [x for x in eligible if x.trust is not TrustTier.TRUSTED_CONTROL]
        budget = request.max_context_chars
        selected: list[ContextCandidate] = []
        used = 0
        control_size = sum(len(x.content) for x in controls)
        if control_size > budget:
            raise AssistantContractError(
                "trusted control context exceeds request context budget"
            )
        control_budget = min(budget, max(self.reserve_control_chars, control_size))
        for item in controls:
            size = len(item.content)
            if used + size <= control_budget:
                selected.append(item)
                used += size
            else:
                omitted.append(item.source_id)
        for item in others:
            size = len(item.content)
            if used + size <= budget:
                selected.append(item)
                used += size
            else:
                omitted.append(item.source_id)

        selected.sort(key=self._sort_key)
        omitted = list(dict.fromkeys(omitted))
        payload = {
            "request_digest": request.digest,
            "candidates": [
                {
                    "source_id": item.source_id,
                    "content": item.content,
                    "trust": item.trust.value,
                    "provenance": list(item.provenance),
                }
                for item in selected
            ],
            "omitted_source_ids": omitted,
        }
        return CompiledContext(
            request_digest=request.digest,
            candidates=tuple(selected),
            omitted_source_ids=tuple(omitted),
            char_count=used,
            digest=digest_json(payload),
        )


__all__ = ["ContextCompiler"]
