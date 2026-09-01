"""Reputable source registry — pointers only.

House shelves never store article or post prose. Each row is a
citation handle: id, house, url pattern, license note. Social SOTA
is measured by how many of these handles a pulse can bind, not by
scraping feeds.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

Source = Dict[str, Any]

SOURCES: Tuple[Source, ...] = (
    {"id": "arxiv", "house": "arXiv", "kind": "paper",
     "base": "https://arxiv.org/abs/", "match": ("arxiv.org/abs/", "arxiv.org/html/", "arxiv.org/pdf/"),
     "note": "open preprint"},
    {"id": "xarchive", "house": "Xarchive", "kind": "archive",
     "base": "https://xarchive.net/", "match": ("xarchive.net",),
     "note": "wayback CDX index; stores no post copies"},
    {"id": "wayback", "house": "Internet Archive", "kind": "archive",
     "base": "https://web.archive.org/", "match": ("web.archive.org", "web.archive.org/cdx/search/cdx"),
     "note": "CDX capture pointer"},
    {"id": "x-status", "house": "X", "kind": "post",
     "base": "https://x.com/", "match": ("x.com/", "twitter.com/"),
     "note": "status URL pointer; no body stored"},
    {"id": "xai", "house": "xAI", "kind": "lab",
     "base": "https://x.ai/", "match": ("x.ai/", "docs.x.ai"),
     "note": "lab primary"},
    {"id": "anthropic", "house": "Anthropic", "kind": "lab",
     "base": "https://www.anthropic.com/", "match": ("anthropic.com",),
     "note": "lab primary"},
    {"id": "openai", "house": "OpenAI", "kind": "lab",
     "base": "https://openai.com/", "match": ("openai.com",),
     "note": "lab primary"},
    {"id": "deepmind", "house": "Google DeepMind", "kind": "lab",
     "base": "https://deepmind.google/", "match": ("deepmind.google", "deepmind.com"),
     "note": "lab primary"},
    {"id": "meta-ai", "house": "Meta", "kind": "lab",
     "base": "https://ai.meta.com/", "match": ("ai.meta.com", "arxiv.org"),
     "note": "lab + papers"},
    {"id": "stanford-crfm", "house": "Stanford CRFM", "kind": "lab",
     "base": "https://crfm.stanford.edu/", "match": ("crfm.stanford.edu",),
     "note": "academic"},
    {"id": "openai-index", "house": "OpenAI", "kind": "article",
     "base": "https://openai.com/index/", "match": ("openai.com/index/",),
     "note": "lab article"},
    {"id": "hf-papers", "house": "Hugging Face", "kind": "paper",
     "base": "https://huggingface.co/papers/", "match": ("huggingface.co/papers",),
     "note": "paper card"},
    {"id": "github-oss", "house": "GitHub", "kind": "code",
     "base": "https://github.com/", "match": ("github.com/",),
     "note": "repo pointer"},
)

# Seed SOTA pointer set — house dialect topics, not abstracts.
SOTA_POINTERS: Tuple[Dict[str, str], ...] = (
    {"topic": "proactive-memory-agent", "url": "https://arxiv.org/abs/2607.08716", "house": "arXiv"},
    {"topic": "mindmemos", "url": "https://arxiv.org/abs/2608.12428", "house": "arXiv"},
    {"topic": "o-mem", "url": "https://arxiv.org/html/2511.13593", "house": "arXiv"},
    {"topic": "graph-agent-memory", "url": "https://arxiv.org/abs/2602.05665", "house": "arXiv"},
    {"topic": "recuris-rsi", "url": "https://arxiv.org/abs/2608.24876", "house": "arXiv"},
    {"topic": "memgen", "url": "https://arxiv.org/abs/2509.24704", "house": "arXiv"},
    {"topic": "context-codec", "url": "https://arxiv.org/abs/2605.17304", "house": "arXiv"},
    {"topic": "dual-layer-memory", "url": "https://arxiv.org/abs/2608.22215", "house": "arXiv"},
    {"topic": "x-archive-rag", "url": "https://github.com/mameshivaa/x-archive-rag", "house": "GitHub"},
    {"topic": "xf-archive-search", "url": "https://github.com/Dicklesworthstone/xf", "house": "GitHub"},
    {"topic": "xarchive", "url": "https://xarchive.net/about", "house": "Xarchive"},
    {"topic": "wayback-cdx", "url": "https://web.archive.org/cdx/search/cdx", "house": "Internet Archive"},
    {"topic": "mem0", "url": "https://github.com/mem0ai/mem0", "house": "GitHub"},
    {"topic": "graphiti", "url": "https://github.com/getzep/graphiti", "house": "GitHub"},
    {"topic": "letta", "url": "https://github.com/letta-ai/letta", "house": "GitHub"},
    {"topic": "cognee", "url": "https://github.com/topoteretes/cognee", "house": "GitHub"},
    {"topic": "budgeted-memory", "url": "https://arxiv.org/abs/2607.16848", "house": "arXiv"},
    {"topic": "graphmemix", "url": "https://arxiv.org/abs/2608.26983", "house": "arXiv"},
    {"topic": "parametric-kg-memory", "url": "https://arxiv.org/abs/2608.25489", "house": "arXiv"},
    {"topic": "graph-selection-integrity", "url": "https://arxiv.org/abs/2606.12290", "house": "arXiv"},
    {"topic": "dmas-ltm-cost", "url": "https://arxiv.org/abs/2601.07978", "house": "arXiv"},
    {"topic": "memory-depth-evaf", "url": "https://arxiv.org/abs/2606.26806", "house": "arXiv"},
    {"topic": "procl-program-memory", "url": "https://arxiv.org/abs/2605.13162", "house": "arXiv"},
    {"topic": "retain-or-consolidate", "url": "https://arxiv.org/abs/2607.17545", "house": "arXiv"},
    {"topic": "agent-native-memory", "url": "https://arxiv.org/abs/2606.24775", "house": "arXiv"},
    {"topic": "routed-graph-handoff", "url": "https://arxiv.org/abs/2608.25277", "house": "arXiv"},
    {"topic": "mragent-reconstruct", "url": "https://arxiv.org/abs/2606.06036", "house": "arXiv"},
    {"topic": "entity-memory-graph", "url": "https://arxiv.org/abs/2608.27925", "house": "arXiv"},
    {"topic": "sage-graph-memory", "url": "https://arxiv.org/abs/2605.12061", "house": "arXiv"},
    {"topic": "lms-need-sleep", "url": "https://arxiv.org/abs/2606.03979", "house": "arXiv"},
    {"topic": "scm-sleep-forget", "url": "https://arxiv.org/abs/2604.20943", "house": "arXiv"},
    {"topic": "faulty-consolidation", "url": "https://arxiv.org/abs/2605.12978", "house": "arXiv"},
    {"topic": "recuris-rsi-memory", "url": "https://arxiv.org/abs/2608.24876", "house": "arXiv"},
    {"topic": "human-inspired-memory", "url": "https://arxiv.org/abs/2605.08538", "house": "arXiv"},
    {"topic": "agent-memory-survey", "url": "https://arxiv.org/abs/2602.06052", "house": "arXiv"},
    {"topic": "fsfm-selective-forget", "url": "https://arxiv.org/abs/2604.20300", "house": "arXiv"},
    {"topic": "forget-control-plane", "url": "https://arxiv.org/abs/2606.15903", "house": "arXiv"},
    {"topic": "reversible-forgetting", "url": "https://arxiv.org/abs/2608.18177", "house": "arXiv"},
)


def catalog() -> List[Dict[str, Any]]:
    return [dict(s) for s in SOURCES]


def classify(url: str) -> Optional[Source]:
    u = (url or "").lower()
    for src in SOURCES:
        if any(m in u for m in src["match"]):
            return dict(src)
    return None
