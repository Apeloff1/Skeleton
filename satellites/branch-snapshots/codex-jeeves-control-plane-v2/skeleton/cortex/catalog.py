"""House catalog — every family Jeeves is willing to gate.

Not a download list. A bind table. Each row is a gate id, modality set,
and acquire path. Remote weights stay remote until a gate is bound and
contact writes the house copy. Closed-world mouths are first-class too.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

Family = Dict[str, Any]

FAMILIES: Tuple[Family, ...] = (
    {"id": "xai.grok", "house": "xAI", "models": ("grok-4", "grok-3", "grok-2", "grok-2-vision"),
     "modalities": ("text", "image"), "gate": "openai_compat", "env": "XAI_API_KEY",
     "base": "https://api.x.ai/v1"},
    {"id": "moonshot.kimi", "house": "Moonshot", "models": ("kimi-k2-0711-preview", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
     "modalities": ("text",), "gate": "kimi", "env": "KIMI_API_KEY",
     "base": "https://api.moonshot.ai/v1"},
    {"id": "openai.gpt", "house": "OpenAI", "models": ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3", "o4-mini", "whisper-1", "tts-1"),
     "modalities": ("text", "image", "audio"), "gate": "openai_compat", "env": "OPENAI_API_KEY",
     "base": "https://api.openai.com/v1"},
    {"id": "anthropic.claude", "house": "Anthropic", "models": ("claude-opus-4", "claude-sonnet-4", "claude-3-5-haiku"),
     "modalities": ("text", "image"), "gate": "anthropic", "env": "ANTHROPIC_API_KEY",
     "base": "https://api.anthropic.com"},
    {"id": "google.gemini", "house": "Google", "models": ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"),
     "modalities": ("text", "image", "audio", "video"), "gate": "gemini", "env": "GEMINI_API_KEY",
     "base": "https://generativelanguage.googleapis.com"},
    {"id": "meta.llama", "house": "Meta", "models": ("llama-4-scout", "llama-3.3-70b", "llama-3.1-8b"),
     "modalities": ("text", "image"), "gate": "huggingface", "env": "HF_TOKEN",
     "base": "https://huggingface.co"},
    {"id": "mistral.mixtral", "house": "Mistral", "models": ("mistral-large", "mistral-small", "pixtral-large", "codestral"),
     "modalities": ("text", "image"), "gate": "openai_compat", "env": "MISTRAL_API_KEY",
     "base": "https://api.mistral.ai/v1"},
    {"id": "deepseek.v3", "house": "DeepSeek", "models": ("deepseek-chat", "deepseek-reasoner"),
     "modalities": ("text",), "gate": "openai_compat", "env": "DEEPSEEK_API_KEY",
     "base": "https://api.deepseek.com"},
    {"id": "alibaba.qwen", "house": "Alibaba", "models": ("qwen2.5", "qwen2.5-vl", "qwen-max"),
     "modalities": ("text", "image"), "gate": "huggingface", "env": "HF_TOKEN",
     "base": "https://huggingface.co"},
    {"id": "cohere.command", "house": "Cohere", "models": ("command-r-plus", "command-r", "command-a"),
     "modalities": ("text",), "gate": "cohere", "env": "COHERE_API_KEY",
     "base": "https://api.cohere.com"},
    {"id": "huggingface.hub", "house": "HuggingFace", "models": ("sshleifer/tiny-gpt2", "gpt2", "openai/whisper-tiny", "openai/clip-vit-base-patch32"),
     "modalities": ("text", "image", "audio"), "gate": "huggingface", "env": "HF_TOKEN",
     "base": "https://huggingface.co"},
    {"id": "house.skeleton", "house": "Skeleton", "models": ("pfc", "midbrain", "left", "right", "neo", "neo_rms"),
     "modalities": ("text", "image", "audio", "video"), "gate": "local", "env": "",
     "base": "local"},
)

MODALITIES = ("text", "image", "audio", "video")


def catalog() -> List[Dict[str, Any]]:
    return [dict(f) for f in FAMILIES]


def by_id(fid: str) -> Dict[str, Any]:
    key = (fid or "").lower()
    for f in FAMILIES:
        if f["id"] == key or key in {m.lower() for m in f["models"]} or key == f["house"].lower():
            return dict(f)
    return dict(FAMILIES[-1])


def all_model_ids() -> Tuple[str, ...]:
    out: List[str] = []
    for f in FAMILIES:
        out.extend(str(m) for m in f["models"])
    return tuple(dict.fromkeys(out))
