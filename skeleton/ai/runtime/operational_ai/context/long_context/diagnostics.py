"""Context utilization without logging private text."""
from __future__ import annotations
from .projection import Projection
from .budget import Window


def diagnostic(projection:Projection,window:Window)->dict:
    return {'tokenizer_digest':projection.tokenizer_digest,'context_tokens':projection.tokens,
            'budget_ceiling':window.input_ceiling,'reserved_output':window.output_reserved,
            'evidence_sources':len(projection.source_hashes),
            'omitted_sources':len(projection.omitted_ids),
            'projection_digest':projection.projection_digest,'status':'compiled-not-native-evaluated'}
