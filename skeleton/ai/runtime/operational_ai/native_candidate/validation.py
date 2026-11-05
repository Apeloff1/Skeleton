"""Actual native-model validation and holdout generation, never simulated scores.

Only source-fixed validation or holdout items may be evaluated. No training
examples can enter this evaluator. Testing does not mutate model weights.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic_ns

from skeleton.ai.model_runtime.chat_engine import NativeChatEngine
from skeleton.ai.model_runtime.chat_protocol import ChatTranscript
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from .records import TrainingExample
from .splits import Partition
from .strict import bytes_sha, number, sha
from .errors import deny


@dataclass(frozen=True, slots=True)
class ValidationCase:
    item_id: str
    output_sha256: str
    expected_sha256: str
    passed: bool
    latency_ms: int
    tokens_generated: int
    model_sha256: str

    def record(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ValidationReport:
    partition_name: str
    candidate_model_sha256: str
    source_partition_sha256: str
    cases: tuple[ValidationCase, ...]

    def record(self) -> dict:
        return {
            "schema": "skeleton.native-candidate.validation.v1",
            "partition": self.partition_name,
            "candidate_model_sha256": self.candidate_model_sha256,
            "source_partition_sha256": self.source_partition_sha256,
            "cases_total": len(self.cases),
            "cases_passed": sum(case.passed for case in self.cases),
            "cases": [case.record() for case in self.cases],
            "actual_native_inference": True,
            "independent_review_complete": False,
            "production_authorized": False,
        }


def evaluate_model(
    checkpoint_bytes: bytes, *,
    expected_model_sha256: str,
    partitions: Partition,
    partition_name: str,
    max_new_tokens: int = 64,
) -> ValidationReport:
    sha(expected_model_sha256, "evaluation-model")
    if type(checkpoint_bytes) is not bytes or len(checkpoint_bytes) > 256000000:
        deny("validation-checkpoint-budget")
    if type(partitions) is not Partition:
        deny("validation-partition")
    if partition_name not in ("validation", "holdout"):
        deny("training-data-evaluation-refused")
    number(max_new_tokens, "evaluation-output", 1, 512)
    from .split_proof import verify
    verify(partitions)
    cases = getattr(partitions, partition_name)
    native = NativeLLMRuntime.restore_json(checkpoint_bytes.decode("utf-8"))
    if native.model_digest != expected_model_sha256:
        deny("validation-model-identity")
    engine = NativeChatEngine(native)
    outputs = []
    for item in cases:
        if type(item) is not TrainingExample:
            deny("validation-source")
        start = monotonic_ns()
        transcript = ChatTranscript.parse([{"role": "user", "content": item.prompt}])
        config = GenerationConfig(seed=0, temperature=0.7,
                                  max_new_tokens=max_new_tokens)
        produced = engine.generate(transcript, config).generation
        if native.model_digest != expected_model_sha256:
            deny("validation-model-mutated")
        raw = produced.text.encode("utf-8")
        correct = produced.text.strip() == item.completion.strip()
        outputs.append(ValidationCase(
            item.item_id, bytes_sha(raw),
            bytes_sha(item.completion.encode("utf-8")),
            correct, (monotonic_ns() - start) // 1000000,
            len(produced.generated_ids), native.model_digest,
        ))
    return ValidationReport(partition_name, native.model_digest,
                            partitions.digest, tuple(outputs))
