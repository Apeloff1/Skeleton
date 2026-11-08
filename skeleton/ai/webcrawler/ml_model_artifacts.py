"""Explicit bounded nonexecuting native ML model/source inventories."""
from __future__ import annotations

from .safetensors_metadata import SAFETENSORS_TYPES,extract_safetensors
from .gguf_metadata import GGUF_TYPES,extract_gguf
from .onnx_metadata import ONNX_TYPES,extract_onnx
from .research_projection import ResearchFormatError,ResearchProjection

ML_MODEL_TYPES=SAFETENSORS_TYPES | GGUF_TYPES | ONNX_TYPES


def extract_ml_model(
    body:bytes,mime:str,*,max_chars:int,
)->ResearchProjection:
    for types,parser in (
        (SAFETENSORS_TYPES,extract_safetensors),
        (GGUF_TYPES,extract_gguf),
        (ONNX_TYPES,extract_onnx),
    ):
        if mime in types:
            return parser(body,max_chars=max_chars)
    raise ResearchFormatError("unadmitted ML model source type")
