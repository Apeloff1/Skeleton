"""Bind model, tokenizer-bytes and deployment settings to a stable identity.

This does not assert independent tokenizer attestation. In GGUF the tokenizer
metadata is embedded in the same authenticated model image.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .manifest import GGUFModelManifest,GGUFManifestError

@dataclass(frozen=True,slots=True)
class DeploymentIdentity:
    manifest_sha:str
    model_sha:str
    tokenizer_binding_sha:str
    configuration_sha:str


def deployment_identity(manifest:GGUFModelManifest,*,n_ctx:int,n_threads:int,n_gpu_layers:int)->DeploymentIdentity:
    if type(n_ctx) is not int or not 128<=n_ctx<=manifest.context_ceiling:
        raise GGUFManifestError('context exceeds model contract')
    if type(n_threads) is not int or not 1<=n_threads<=64:
        raise GGUFManifestError('invalid CPU worker count')
    if type(n_gpu_layers) is not int or not 0<=n_gpu_layers<=manifest.gpu_layers_ceiling:
        raise GGUFManifestError('GPU layer ceiling exceeded')
    record={'model_sha':manifest.model_sha256,'manifest_sha':manifest.manifest_digest,
            'context':n_ctx,'threads':n_threads,'gpu_layers':n_gpu_layers}
    identity=sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return DeploymentIdentity(manifest.manifest_digest,manifest.model_sha256,
                              manifest.model_sha256,identity)
