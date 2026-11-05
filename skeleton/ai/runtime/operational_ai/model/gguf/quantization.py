"""Policy metadata for known GGUF quantization families; does not fabricate weights."""
from __future__ import annotations
from dataclasses import dataclass
from .manifest import GGUFManifestError

@dataclass(frozen=True,slots=True)
class Quantization:
    name:str
    bits_per_weight:float
    documented:bool
    deployable:bool

_INFO={
 'F32':32.0,'F16':16.0,'BF16':16.0,
 'Q8_0':8.5,'Q6_K':6.57,'Q5_K_M':5.67,'Q4_K_M':4.85,
 'Q4_0':4.5,'Q3_K_M':3.89,'Q2_K':2.9,
}

def inspect_quantization(name:str)->Quantization:
    if not isinstance(name,str) or len(name)>64:
        raise GGUFManifestError('invalid quantization descriptor')
    if name not in _INFO:
        return Quantization(name,0.0,False,False)
    return Quantization(name,_INFO[name],True,True)
