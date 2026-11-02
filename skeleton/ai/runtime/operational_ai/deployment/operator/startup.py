"""No-download executable GGUF startup; deterministic doctor then real loader."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ..operator.doctor import doctor
from ...model.gguf.service import load_approved_manifest,activate_model
from ...model.gguf.manifest import GGUFManifestError
from ...model.gguf.runtime import GGUFBackend

@dataclass(slots=True)
class Activation:
    backend:GGUFBackend
    model_digest:str
    preflight:str
    def close(self):self.backend.close()
    def __enter__(self):return self
    def __exit__(self,*_:object):self.close()


def activate_gguf_operator(root:str|Path,state_dir:str|Path,*,context:int=2048,
                           gpu_layers:int=0,threads:int=4)->Activation:
    report=doctor(model_root=root,state_dir=state_dir,require_gguf=True)
    if report.state!='preflight-passed-not-live-tested':
        raise GGUFManifestError('operator preflight blocked model activation')
    manifest=load_approved_manifest(root)
    backend=activate_model(root,manifest,n_ctx=context,n_gpu_layers=gpu_layers,n_threads=threads)
    return Activation(backend,manifest.model_sha256,report.state)
