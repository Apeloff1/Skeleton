"""Semantic selection must feed original token spans, not generated summaries."""
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy
from skeleton.ai.model_runtime.long_context_spool import LongContextSpool
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.context_reconstruction import ReconstructionPolicy
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.cortex.transformer import TinyTransformer


def test_semantic_spool_executes_without_token_overlap(tmp_path):
    ranker=ContextualRanker(build_encoder(tmp_path),SemanticPolicy(context_chars=128,min_cosine=.25,segments=2))
    rt=NativeLLMRuntime(TinyTransformer({"cat","feline","motor","other"},dim=4,ctx=128,seed=3))
    spool=LongContextSpool(tmp_path/"spool")
    try:
        seq=rt.tokenizer.encode_sequence(" ".join(["motor"]*16+["cat"]*16+["other"]*16))
        checkpoint=spool.stage(seq)
        result,proof=rt.generate_reconstructed_context(spool,checkpoint,"feline",
          GenerationConfig(max_new_tokens=1,temperature=0),
          ReconstructionPolicy(context_tokens=80,window_tokens=8,overlap_tokens=0,max_spans=1,edge_order=True),
          semantic_ranker=ranker)
        assert result.usage.generated_tokens==1
        assert proof["learned_semantic_retrieval"] is True and proof["covered_terms"]==0
        assert 16<=proof["spans"][0]["start"]<32
        assert proof["semantic_verification"] is False
    finally:
        spool.close()
