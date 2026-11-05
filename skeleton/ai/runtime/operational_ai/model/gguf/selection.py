"""Select exactly one approved GGUF inventory member without implicit model fallback."""
from __future__ import annotations
from .manifest import GGUFModelManifest,GGUFManifestError


def choose(manifests:tuple[GGUFModelManifest,...],*,model_id:str|None=None,
           max_bytes:int=1_940_000_000,context_minimum:int=1024)->GGUFModelManifest:
    if not manifests:raise GGUFManifestError('no approved local GGUF inventory')
    if len({m.model_id for m in manifests})!=len(manifests):
        raise GGUFManifestError('ambiguous duplicate model identities')
    permitted=[m for m in manifests if m.total_bytes<=max_bytes and m.context_ceiling>=context_minimum]
    if model_id is not None:
        matches=[m for m in permitted if m.model_id==model_id]
        if len(matches)!=1:raise GGUFManifestError('requested model not installed or admitted')
        return matches[0]
    if len(permitted)!=1:
        raise GGUFManifestError('ambiguous default selection; explicit model required')
    return permitted[0]
