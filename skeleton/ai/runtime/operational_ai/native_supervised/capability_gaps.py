"""Combine independent tokenizer diagnostics without masking poor model output."""
from __future__ import annotations
from .representability import full_audit
from .lexical_gaps import inspect as lexical
from .errors import reject


def describe(runtime)->dict:
    formats=full_audit(runtime)
    vocabulary=lexical(runtime)
    if formats["cases"]!=768 or len(vocabulary["domains"])!=32:
        reject("gap-incomplete")
    return {
        "schema":"skeleton.native-supervised.capability-gaps.v1",
        "model_sha256":runtime.model_digest,
        "formats":formats,
        "vocabulary":vocabulary,
        "model_generation_tested":False,
        "automatic_case_exemptions":0,
        "future_tokenizer_rework_needed":formats["unrenderable"]>0,
        "release_certified":False,
    }
