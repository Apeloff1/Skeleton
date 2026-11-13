"""Offline GGUF inference with pinned, hash-verified shards.

The backend is opt-in: requires local llama-cpp-python, Linux sealed memfd,
operator-provisioned rights-approved model shards, and enough physical memory.
No synthetic completions, implicit downloads or hosted fallback are permitted.
"""
from .manifest import Shard, GGUFModelManifest, load_manifest
from .assembly import ModelAssembly, assemble_model
from .runtime import GGUFBackend

__all__ = ["Shard", "GGUFModelManifest", "load_manifest", "ModelAssembly", "assemble_model", "GGUFBackend"]
