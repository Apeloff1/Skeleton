import pytest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.context_reconstruction import ReconstructionPolicy
from skeleton.ai.model_runtime.long_context_spool import LongContextSpool
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError


def test_exact_reconstruction_runs_native_inference(tmp_path):
    vocab={"alpha","beta","rare","needle","question","reference","tokens","answer","end","to"}
    rt=NativeLLMRuntime(TinyTransformer(vocab,dim=4,ctx=96,seed=3))
    root=tmp_path/"spool"
    spool=LongContextSpool(root)
    try:
        source=rt.tokenizer.encode_sequence(" ".join(["alpha"]*35+["rare","needle"]+["beta"]*35))
        checkpoint=spool.stage(source)
        result,proof=rt.generate_reconstructed_context(spool,checkpoint,"rare needle",
            GenerationConfig(max_new_tokens=1,temperature=0),
            ReconstructionPolicy(context_tokens=80,window_tokens=12,overlap_tokens=4))
        assert result.usage.generated_tokens==1
        assert proof["source_sequence_sha256"]==source.digest
        assert proof["covered_terms"]==2
        assert proof["semantic_verification"] is False
        assert any(row["start"]<=35<row["end"] for row in proof["spans"])
    finally:
        spool.close()
