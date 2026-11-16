"""Explicit local semantic artifact configuration; no remote model discovery."""
from __future__ import annotations
import json
from pathlib import Path
from .learned_embeddings import LocalContextEncoder,EncoderPolicy,LocalPairReranker,PairRerankerPolicy,_read_pinned
from .semantic_long_context import ContextualRanker,SemanticPolicy


def load_semantic_ranker(path,expected_sha256):
    path=Path(path)
    raw=_read_pinned(path,expected_sha256,65536)
    def unique(pairs):
        output={}
        for k,v in pairs:
            if k in output:raise ValueError("duplicate semantic configuration key")
            output[k]=v
        return output
    payload=json.loads(raw,object_pairs_hook=unique)
    expected={"schema","encoder_path","encoder_sha256","tokenizer_path","tokenizer_sha256","encoder_policy","retrieval_policy"}
    if not isinstance(payload,dict) or set(payload) not in (expected,expected|{"reranker"}) or payload["schema"]!="skeleton.local.semantic-config.v1":
        raise ValueError("unsupported pinned semantic configuration")
    def relative(value):
        if not isinstance(value,str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
            raise ValueError("semantic artifact must be relative to config directory")
        return path.parent/value
    encoder=LocalContextEncoder(relative(payload["encoder_path"]),payload["encoder_sha256"],
        relative(payload["tokenizer_path"]),payload["tokenizer_sha256"],EncoderPolicy(**payload["encoder_policy"]))
    reranker=None
    if "reranker" in payload:
        entry=payload["reranker"]
        if not isinstance(entry,dict) or set(entry)!={"model_path","model_sha256","tokenizer_path","tokenizer_sha256","policy"}:
            raise ValueError("invalid explicit local reranker config")
        reranker=LocalPairReranker(relative(entry["model_path"]),entry["model_sha256"],
            relative(entry["tokenizer_path"]),entry["tokenizer_sha256"],PairRerankerPolicy(**entry["policy"]))
    return ContextualRanker(encoder,SemanticPolicy(**payload["retrieval_policy"]),reranker=reranker)
