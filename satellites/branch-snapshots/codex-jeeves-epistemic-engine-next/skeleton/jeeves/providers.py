"""
Skeleton Jeeves — LLM provider abstraction

Provides:
- LLMProvider: Interface for language model backends
- LocalEchoProvider: Dependency-free fallback (extractive, uses memory planes)
- OpenAIProvider / AnthropicProvider: Stubs wired for real API keys
- get_provider: Factory honoring SKELETON_LLM_PROVIDER env var

Providers return plain text; JeevesCore handles session state,
tool dispatch, and event emission around them.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Protocol


class LLMProvider(Protocol):
    """Interface all LLM backends must satisfy."""

    name: str

    def complete(self, prompt: str, context: Optional[List[str]] = None, max_tokens: int = 512) -> str:
        ...

    def available(self) -> bool:
        ...


class LocalEchoProvider:
    """Dependency-free fallback provider.

    Extractive responder: pulls the most relevant memory-plane chunks
    for the query and composes an answer from them. No network, no
    keys — always available. Quality is limited but the pipeline
    (context → provider → response) is fully exercised.
    """

    name = "local-echo"

    def __init__(self, retriever: Optional[Any] = None):
        self._retriever = retriever  # QuadRetriever or MemoryTrinity

    def available(self) -> bool:
        return True

    def complete(self, prompt: str, context: Optional[List[str]] = None, max_tokens: int = 512) -> str:
        fragments: List[str] = []

        if self._retriever is not None:
            try:
                if hasattr(self._retriever, "retrieve"):
                    results = self._retriever.retrieve(prompt, k=3)
                    fragments = [getattr(r, "content", "") for r in results]
                elif hasattr(self._retriever, "query_unified"):
                    result = self._retriever.query_unified(prompt, top_k_per_tier=3)
                    fragments = [c.chunk.text for c in result.facts]
            except Exception:
                fragments = []

        fragments = [f for f in fragments if f.strip()]
        if fragments:
            body = " ".join(fragments)
            return f"Based on what I know: {body[:max_tokens]}"

        if context:
            return f"Following on from earlier: {context[-1][:max_tokens]}"

        return f"I don't have relevant context for that yet. (prompt: {prompt[:80]})"


class OpenAIProvider:
    """OpenAI chat-completions backend. Requires SKELETON_OPENAI_API_KEY."""

    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self._key = os.getenv("SKELETON_OPENAI_API_KEY", "")

    def available(self) -> bool:
        return bool(self._key)

    def complete(self, prompt: str, context: Optional[List[str]] = None, max_tokens: int = 512) -> str:
        import json
        import urllib.request

        messages = []
        for turn in (context or [])[-6:]:
            messages.append({"role": "user", "content": turn})
        messages.append({"role": "user", "content": prompt})

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps({"model": self.model, "messages": messages, "max_tokens": max_tokens}).encode(),
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]


class AnthropicProvider:
    """Anthropic messages backend. Requires SKELETON_ANTHROPIC_API_KEY."""

    name = "anthropic"

    def __init__(self, model: str = "claude-haiku-4-5"):
        self.model = model
        self._key = os.getenv("SKELETON_ANTHROPIC_API_KEY", "")

    def available(self) -> bool:
        return bool(self._key)

    def complete(self, prompt: str, context: Optional[List[str]] = None, max_tokens: int = 512) -> str:
        import json
        import urllib.request

        messages = [{"role": "user", "content": t} for t in (context or [])[-6:]]
        messages.append({"role": "user", "content": prompt})

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({"model": self.model, "messages": messages, "max_tokens": max_tokens}).encode(),
            headers={
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["content"][0]["text"]


def get_provider(retriever: Optional[Any] = None, preferred: Optional[str] = None) -> LLMProvider:
    """Factory: pick a provider by preference, env var, or availability.

    Order: explicit `preferred` → SKELETON_LLM_PROVIDER → first available
    (openai → anthropic → local-echo).
    """
    choice = (preferred or os.getenv("SKELETON_LLM_PROVIDER", "")).lower()

    candidates: Dict[str, Any] = {
        "openai": OpenAIProvider(),
        "anthropic": AnthropicProvider(),
        "local": LocalEchoProvider(retriever),
        "local-echo": LocalEchoProvider(retriever),
    }

    if choice and choice in candidates:
        provider = candidates[choice]
        if provider.available():
            return provider

    for name in ("openai", "anthropic"):
        if candidates[name].available():
            return candidates[name]

    return candidates["local"]
