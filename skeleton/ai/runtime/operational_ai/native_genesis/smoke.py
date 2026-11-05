"""Real native graph smoke test; never treats random output as correct reasoning."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from .canonical import digest, required_sha
from .errors import refuse


@dataclass(frozen=True, slots=True)
class SmokeResult:
    model_sha256: str
    tokenizer_sha256: str
    input_sha256: str
    generated_sha256: str
    prompt_tokens: int
    generated_tokens: int
    graph_executed: bool

    def report(self) -> dict:
        return {
            **{key: getattr(self, key) for key in self.__dataclass_fields__},
            "actual_inference": self.graph_executed,
            "answer_quality_verified": False,
            "model_trained": False,
            "serving_admitted": False,
        }


def run_graph_smoke(runtime: NativeLLMRuntime, *,
                    exact_model_sha256: str, seed: int = 0) -> SmokeResult:
    required_sha(exact_model_sha256, "model")
    if type(runtime) is not NativeLLMRuntime:
        refuse("smoke-native-runtime")
    runtime.assert_model_unchanged()
    if runtime.model_digest != exact_model_sha256:
        refuse("smoke-model-changed")
    prompt = "Instruction: add two numbers Response:"
    tokenized = runtime.encode(prompt)
    if not tokenized.token_ids:
        refuse("smoke-tokenizer-empty")
    config = GenerationConfig(max_new_tokens=2, seed=seed, temperature=1.0)
    result = runtime.generate_sequence(tokenized, config)
    runtime.assert_model_unchanged()
    if result.replay_receipt.model_digest != exact_model_sha256:
        refuse("smoke-receipt-model")
    if len(result.generated_ids) != 2:
        refuse("smoke-native-not-executed")
    return SmokeResult(
        runtime.model_digest, runtime.tokenizer.digest,
        digest({"prompt": prompt}), result.output_digest,
        len(tokenized.token_ids), len(result.generated_ids), True,
    )
