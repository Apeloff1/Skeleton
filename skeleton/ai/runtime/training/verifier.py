"""Measured, reusable local verifier inference with candidate-only authority."""

from __future__ import annotations

import hashlib
import json
import marshal
import math
import re
import time
import types
import weakref
from collections.abc import Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from typing import Any

from skeleton.ai.runtime.inference.local import (
    LocalInferenceEngine,
    LocalInferenceRequest,
)
from skeleton.learning.model_program import (
    ModelDevelopmentRegistry,
    TrainingReceipt,
    corpus_digest,
)

from .evaluation import (
    EvaluationCase,
    EvaluationLedger,
    EvaluationSuite,
    evaluation_case_passes,
)

MAX_RECORD_BYTES = 16 * 1024 * 1024
MAX_CASES = 256
MAX_CASE_BYTES = 256 * 1024
MAX_RUN_EVIDENCE_BYTES = MAX_RECORD_BYTES
_SOURCE_TOKEN = object()


class _WriterCapability:
    pass


_WRITER_CAPABILITIES = weakref.WeakSet()


def _issue_writer_capability():
    capability = _WriterCapability()
    _WRITER_CAPABILITIES.add(capability)
    return capability


def _issued_writer_capability(capability):
    return type(capability) is _WriterCapability and capability in _WRITER_CAPABILITIES


class MeasuredVerifierError(RuntimeError):
    """Measured verifier evidence is invalid, stale, contaminated, or unissued."""


def canonical(value: object) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise MeasuredVerifierError("evidence must be finite canonical JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_RECORD_BYTES:
        raise MeasuredVerifierError("evidence exceeds durable record byte bound")
    return encoded


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text(value: object, name: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise MeasuredVerifierError(f"{name} must be bounded nonempty text")
    return value


def sha(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise MeasuredVerifierError(f"{name} must be lowercase sha256")
    return value


def integer(value: object, name: str, minimum: int = 0, maximum: int = (1 << 63) - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise MeasuredVerifierError(f"{name} must be a bounded integer")
    return value


def rate(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise MeasuredVerifierError(f"{name} must be a finite rate")
    return float(value)


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise MeasuredVerifierError("duplicate JSON key")
        result[key] = value
    return result


def decode(raw: str, *, maximum: int = MAX_RECORD_BYTES, require_canonical: bool = True) -> Any:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > maximum:
        raise MeasuredVerifierError("JSON evidence exceeds byte bound")
    try:
        result = json.loads(
            raw, object_pairs_hook=_pairs, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError())
        )
    except (ValueError, TypeError, RecursionError) as exc:
        raise MeasuredVerifierError("invalid bounded JSON evidence") from exc
    if require_canonical and canonical(result) != raw:
        raise MeasuredVerifierError("evidence JSON is not canonical")
    return result


def _fingerprint(document: str) -> str:
    return hashlib.sha256(" ".join(document.casefold().split()).encode("utf-8")).hexdigest()


def _documents(corpora: Sequence[Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    if not isinstance(corpora, Sequence) or isinstance(corpora, (str, bytes)) or not 1 <= len(corpora) <= 128:
        raise MeasuredVerifierError("training corpus groups must be a bounded sequence")
    result = []
    count = size = 0
    for corpus in corpora:
        if not isinstance(corpus, Sequence) or isinstance(corpus, (str, bytes)) or not corpus:
            raise MeasuredVerifierError("training documents must be a nonempty sequence")
        count += len(corpus)
        if count > 8192:
            raise MeasuredVerifierError("training document count exceeds bound")
        group = []
        for index in range(len(corpus)):
            document = text(corpus[index], "training document", 1024 * 1024)
            size += len(document.encode("utf-8"))
            if size > 64 * 1024 * 1024:
                raise MeasuredVerifierError("training corpus bytes exceed bound")
            group.append(document)
        result.append(tuple(group))
    return tuple(result)


def _runtime_identity(model) -> str:
    payload = getattr(model, "to_dict", None)
    if not callable(payload):
        raise MeasuredVerifierError("measured model must expose serializable local weights")
    implementations = {}
    seen = set()
    code_bytes = 0
    seen_classes = set()
    seen_modules = set()

    def descriptor(value):
        return {
            "module": getattr(value, "__module__", type(value).__module__),
            "name": getattr(value, "__qualname__", getattr(value, "__name__", None)),
            "type": type(value).__module__ + "." + type(value).__qualname__,
        }

    def class_helpers(cls, name, depth):
        implementations[name] = descriptor(cls)
        if id(cls) in seen_classes:
            return
        seen_classes.add(id(cls))
        for base in cls.__mro__:
            for symbol, member in sorted(vars(base).items()):
                functions = (
                    (("get", member.fget), ("set", member.fset), ("delete", member.fdel))
                    if isinstance(member, property)
                    else (("call", member),)
                )
                for accessor, function in functions:
                    if isinstance(function, (staticmethod, classmethod)):
                        function = function.__func__
                    if isinstance(function, types.FunctionType):
                        identify(
                            function,
                            "dependency-class:"
                            + base.__module__
                            + "."
                            + base.__qualname__
                            + "."
                            + symbol
                            + ":"
                            + accessor,
                            depth + 1,
                        )

    def module_binding(module, symbols, depth):
        implementations["module:" + module.__name__] = getattr(module, "__version__", None)
        marker = (id(module), tuple(sorted(set(symbols))))
        if marker in seen_modules:
            return
        if depth > 8:
            raise MeasuredVerifierError("backend module dependency exceeds depth bound")
        seen_modules.add(marker)
        for symbol in sorted(set(symbols)):
            if symbol not in vars(module):
                continue
            value = vars(module)[symbol]
            name = "module-dispatch:" + module.__name__ + "." + symbol
            if isinstance(value, types.FunctionType):
                identify(value, name, depth + 1)
            elif isinstance(value, types.ModuleType):
                implementations[name] = {
                    "module": value.__name__,
                    "version": getattr(value, "__version__", None),
                }
                module_binding(value, symbols, depth + 1)
            elif isinstance(value, type):
                class_helpers(value, name, depth)
            elif callable(value):
                implementations[name] = {
                    "module": getattr(value, "__module__", type(value).__module__),
                    "name": getattr(value, "__qualname__", getattr(value, "__name__", None)),
                    "type": type(value).__module__ + "." + type(value).__qualname__,
                }
            elif isinstance(value, (str, int, float, bool, tuple, list, dict)) or value is None:
                implementations[name] = value

    def identify(function, name, depth=0):
        nonlocal code_bytes
        function = getattr(function, "__func__", function)
        code = getattr(function, "__code__", None)
        if code is None:
            raise MeasuredVerifierError("backend helpers must expose identified Python code")
        if depth > 8 or (id(function) not in seen and len(seen) >= 256):
            raise MeasuredVerifierError("backend implementation exceeds fingerprint bounds")
        encoded_code = marshal.dumps(code)
        if id(function) not in seen:
            code_bytes += len(encoded_code)
            if code_bytes > 256 * 1024:
                raise MeasuredVerifierError("backend implementation code exceeds byte bound")
        captured = [
            descriptor(cell.cell_contents) if isinstance(cell.cell_contents, type) else cell.cell_contents
            for cell in (function.__closure__ or ())
        ]
        implementations[name] = {
            "code": hashlib.sha256(encoded_code).hexdigest(),
            "defaults": function.__defaults__,
            "kwdefaults": function.__kwdefaults__,
            "captures": captured,
        }
        if id(function) in seen:
            return
        seen.add(id(function))
        for symbol in code.co_names:
            value = function.__globals__.get(symbol)
            if isinstance(value, types.FunctionType):
                identify(value, "global-binding:" + function.__module__ + "." + symbol, depth + 1)
            elif isinstance(value, types.ModuleType):
                implementations["global-binding:" + function.__module__ + "." + symbol] = {
                    "module": value.__name__
                }
                module_binding(value, code.co_names, depth)
            elif callable(value):
                implementations["global-binding:" + function.__module__ + "." + symbol] = descriptor(value)
            elif isinstance(value, re.Pattern):
                implementations["global:" + function.__module__ + "." + symbol] = {
                    "pattern": value.pattern,
                    "flags": value.flags,
                }
            elif value is not None and isinstance(value, (str, int, float, bool, tuple, list, dict)):
                implementations["global:" + function.__module__ + "." + symbol] = value

    for cls in type(model).__mro__:
        if cls is object:
            continue
        for name, member in sorted(vars(cls).items()):
            functions = (
                tuple(
                    (name + ":" + accessor, function)
                    for accessor, function in (
                        ("get", member.fget),
                        ("set", member.fset),
                        ("delete", member.fdel),
                    )
                )
                if isinstance(member, property)
                else ((name, member),)
            )
            for dispatch_name, function in functions:
                if isinstance(function, (staticmethod, classmethod)):
                    function = function.__func__
                if isinstance(function, types.FunctionType):
                    identify(function, cls.__module__ + "." + cls.__qualname__ + "." + dispatch_name)
    for name, value in sorted(getattr(model, "__dict__", {}).items()):
        if callable(value):
            identify(value, "instance:" + name)
    identify(model.infer, "actual:infer")
    if len(canonical(implementations).encode("utf-8")) > 256 * 1024:
        raise MeasuredVerifierError("backend implementation exceeds fingerprint byte bound")
    return digest(
        {
            "weights": payload(),
            "implementation_code": implementations,
            "implementation": type(model).__module__ + "." + type(model).__qualname__,
        }
    )


class EvaluationModelSource:
    """An issued training artifact and its exact observed training documents."""

    def __init__(self, model, identity, corpora, checker, *, registry=None, authority=None, _token=None):
        if _token is not _SOURCE_TOKEN:
            raise MeasuredVerifierError("use an existing training authority to bind an evaluation model")
        documents = _documents(corpora)
        self.model = model
        self._checker = checker
        self._registry = registry
        self._authority = authority
        document_digest = corpus_digest
        if identity["kind"] == "durable_training":
            from .trainer import corpus_digest as native_corpus_digest

            document_digest = native_corpus_digest
        self._payload = canonical(
            {
                "model_id": text(model.model_id, "model_id"),
                "model_digest": sha(model.model_digest, "model_digest"),
                "runtime_digest": _runtime_identity(model),
                "training_identity": identity,
                "training_identity_digest": digest(identity),
                "document_fingerprints": sorted({_fingerprint(doc) for group in documents for doc in group}),
                "corpus_digests": [document_digest(group) for group in documents],
                "document_count": sum(map(len, documents)),
            }
        )
        self.assert_current()

    @classmethod
    def from_model_program(
        cls, registry: ModelDevelopmentRegistry, receipt: TrainingReceipt, *, model, corpora
    ):
        if not isinstance(registry, ModelDevelopmentRegistry) or not isinstance(receipt, TrainingReceipt):
            raise TypeError("model-program training authority and receipt are required")
        documents = _documents(corpora)
        if tuple(corpus_digest(group) for group in documents) != receipt.dataset_digests:
            raise MeasuredVerifierError("training document sequence does not match issued receipt")
        receipt_payload = canonical(receipt.as_dict())

        def check():
            if (
                registry._receipts.get(receipt.run_id) is not receipt
                or canonical(receipt.as_dict()) != receipt_payload
            ):
                raise MeasuredVerifierError("training receipt is not current and registry-issued")
            artifact = registry.artifact(receipt.model_digest)
            if (
                artifact.artifact_digest != receipt.artifact_digest
                or artifact.training_run_id != receipt.run_id
            ):
                raise MeasuredVerifierError("training artifact and receipt identity mismatch")
            if model.model_digest != receipt.model_digest or model.model_id != receipt.model_id:
                raise MeasuredVerifierError("actual model does not match issued training receipt")
            if canonical(model.to_dict()) != canonical(artifact.payload):
                raise MeasuredVerifierError("actual local weights do not match the issued training artifact")

        return cls(
            model,
            {"kind": "model_program", "receipt": receipt.as_dict()},
            documents,
            check,
            _token=_SOURCE_TOKEN,
        )

    @classmethod
    def from_training(cls, trainer, run_id: str):
        from .neural_trainer import NeuralLocalTrainer
        from .trainer import ReferenceLocalTrainer

        if not isinstance(trainer, (ReferenceLocalTrainer, NeuralLocalTrainer)):
            raise TypeError("canonical completed local trainer is required")
        model, artifact = trainer.load_artifact(run_id)
        manifest = trainer.runs.manifest(run_id)
        binding = trainer.runs.execution_binding(run_id)
        epoch = binding["dataset_authority_epoch"]
        trainer.datasets.assert_dataset_authority(manifest.dataset_digest, epoch)
        documents = trainer.datasets.training_corpus(
            manifest.dataset_digest, split_name=binding.get("split_name", "train")
        )
        trainer.datasets.validate_training_corpus(
            manifest.dataset_digest, documents, split_name=binding.get("split_name", "train")
        )
        artifact_payload = asdict(artifact)
        identity = {
            "kind": "durable_training",
            "artifact": artifact_payload,
            "manifest_digest": manifest.digest,
            "binding_digest": digest(binding),
            "dataset_authority_epoch": epoch,
        }

        def check():
            trainer.datasets.assert_dataset_authority(manifest.dataset_digest, epoch)
            if (
                trainer.runs.state(run_id) != "completed"
                or trainer.runs.manifest(run_id).digest != manifest.digest
            ):
                raise MeasuredVerifierError("completed training identity changed")
            current = trainer.runs.execution_binding(run_id)
            checkpoint = trainer.runs.latest_checkpoint(run_id)
            if (
                digest(current) != identity["binding_digest"]
                or checkpoint.digest != artifact.checkpoint_digest
            ):
                raise MeasuredVerifierError("completed training artifact changed")

        return cls(
            model,
            identity,
            (documents,),
            check,
            registry=trainer.datasets,
            authority=(manifest.dataset_digest, epoch),
            _token=_SOURCE_TOKEN,
        )

    @property
    def payload(self):
        return decode(self._payload)

    def assert_current(self):
        self._checker()
        pinned = self.payload
        if (
            self.model.model_digest != pinned["model_digest"]
            or self.model.model_id != pinned["model_id"]
            or _runtime_identity(self.model) != pinned["runtime_digest"]
        ):
            raise MeasuredVerifierError("local model or inference implementation identity changed")


@contextmanager
def source_authority(sources):
    """Fence observed case publication against current source revocation."""
    groups = {}
    for source in sources:
        if source._registry is not None:
            with source._registry._lock:
                path = source._registry._db.execute("PRAGMA database_list").fetchone()[2]
            groups.setdefault(path or id(source._registry), []).append(source)
    with ExitStack() as stack:
        for _key, grouped in sorted(groups.items(), key=lambda item: str(item[0])):
            first = grouped[0]
            stack.enter_context(first._registry.training_authority(*first._authority))
        for source in sources:
            source.assert_current()
        yield
        for source in sources:
            source.assert_current()


@dataclass(frozen=True, slots=True)
class VerifierGatePolicy:
    min_candidate_accuracy: float = 1.0
    max_accuracy_regression: float = 0.0
    max_calibration_error: float = 0.1
    max_false_accept_rate: float = 0.0
    max_false_reject_rate: float = 0.0
    max_correlated_false_accept_rate: float = 0.0
    min_positive_samples: int = 1
    min_negative_samples: int = 1
    require_disjoint_verifier_training: bool = True

    def __post_init__(self):
        for name in (
            "min_candidate_accuracy",
            "max_accuracy_regression",
            "max_calibration_error",
            "max_false_accept_rate",
            "max_false_reject_rate",
            "max_correlated_false_accept_rate",
        ):
            object.__setattr__(self, name, rate(getattr(self, name), name))
        for name in ("min_positive_samples", "min_negative_samples"):
            integer(getattr(self, name), name, 1, MAX_CASES * 2)
        if not isinstance(self.require_disjoint_verifier_training, bool):
            raise MeasuredVerifierError("training independence policy must be boolean")


def parse_verifier_output(raw: str) -> dict[str, object]:
    payload = decode(raw, maximum=4096, require_canonical=False)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"decision", "confidence"}
        or not isinstance(payload["decision"], str)
        or payload["decision"] not in {"accept", "reject"}
    ):
        raise MeasuredVerifierError("verifier must return exactly decision and confidence")
    confidence = rate(payload["confidence"], "confidence")
    if confidence < 0.5:
        raise MeasuredVerifierError("verifier decision confidence must be at least 0.5")
    return {"decision": payload["decision"], "confidence": confidence}


async def _generate(source, prompt, max_tokens, seed):
    source.assert_current()
    started = time.perf_counter_ns()
    response = await LocalInferenceEngine(source.model, cache_size=0).generate(
        LocalInferenceRequest(prompt=prompt, max_output_tokens=max_tokens, seed=seed)
    )
    elapsed = time.perf_counter_ns() - started
    source.assert_current()
    output = response.text or ""
    if (
        not isinstance(output, str)
        or len(output.encode("utf-8")) > 65536
        or response.tool_calls
        or response.structured_output is not None
    ):
        raise MeasuredVerifierError("measured local output violates text-only bounds")
    if response.model_id != source.model.model_id or response.model_digest != source.model.model_digest:
        raise MeasuredVerifierError("actual inference result model identity mismatch")
    return {
        "input_digest": digest({"prompt": prompt, "max_output_tokens": max_tokens, "seed": seed}),
        "output": output,
        "input_tokens": integer(response.input_tokens, "actual input tokens", maximum=1_000_000),
        "output_tokens": integer(response.output_tokens, "actual output tokens", maximum=max_tokens),
        "elapsed_ns": integer(elapsed, "measured elapsed nanoseconds"),
        "model_digest": source.model.model_digest,
    }


class LocalVerifier:
    """Reusable local judgment proposals; qualification grants no finalization authority."""

    def __init__(self, source: EvaluationModelSource):
        if not isinstance(source, EvaluationModelSource):
            raise TypeError("issued evaluation model source is required")
        self.source = source

    @staticmethod
    def prompt(task: str, answer: str) -> str:
        text(task, "verification task", 65536)
        if not isinstance(answer, str) or len(answer.encode("utf-8")) > 65536:
            raise MeasuredVerifierError("verification answer exceeds byte bound")
        return canonical(
            {
                "instruction": "Judge whether the answer correctly completes the task. Return only JSON with decision accept or reject and confidence in [0.5,1].",
                "task": task,
                "answer": answer,
            }
        )

    async def judge(self, task: str, answer: str, *, seed: int = 0):
        integer(seed, "seed")
        measured = await _generate(self.source, self.prompt(task, answer), 256, seed)
        return {**measured, **parse_verifier_output(measured["output"])}


def validate_suite(suite):
    if (
        not isinstance(suite, EvaluationSuite)
        or not 1 <= len(suite.cases) <= MAX_CASES
        or suite.population not in {"heldout", "holdout", "test"}
    ):
        raise MeasuredVerifierError("a bounded held-out EvaluationSuite is required")
    text(suite.suite_id, "suite_id")
    text(suite.version, "suite_version")
    for case in suite.cases:
        if not isinstance(case, EvaluationCase):
            raise MeasuredVerifierError("suite cases must be EvaluationCase values")
        text(case.case_id, "case_id")
        text(case.prompt, "prompt", 65536)
        text(case.expected_substring, "expected answer", 4096)
        integer(case.max_output_tokens, "max_output_tokens", 1, 8192)
    canonical(suite.as_dict())


def derive_metrics(cases):
    samples = [row[role] for row in cases for role in ("candidate", "baseline")]
    positive = sum(item["gold"] for item in samples)
    negative = len(samples) - positive
    false_accepts = sum(not item["gold"] and item["judgment"]["decision"] == "accept" for item in samples)
    false_rejects = sum(item["gold"] and item["judgment"]["decision"] == "reject" for item in samples)
    probabilities = [
        (
            (
                item["judgment"]["confidence"]
                if item["judgment"]["decision"] == "accept"
                else 1 - item["judgment"]["confidence"]
            ),
            int(item["gold"]),
        )
        for item in samples
    ]
    calibration = 0.0
    for bucket in range(10):
        observations = [
            (probability, gold)
            for probability, gold in probabilities
            if min(int(probability * 10), 9) == bucket
        ]
        if observations:
            calibration += abs(sum(p for p, _ in observations) - sum(g for _, g in observations)) / len(
                samples
            )
    jointly_wrong = [row for row in cases if not row["candidate"]["gold"] and not row["baseline"]["gold"]]
    correlated = sum(
        row["candidate"]["judgment"]["decision"] == "accept"
        and row["baseline"]["judgment"]["decision"] == "accept"
        for row in jointly_wrong
    )
    return {
        "sample_count": len(samples),
        "positive_samples": positive,
        "negative_samples": negative,
        "false_accepts": false_accepts,
        "false_rejects": false_rejects,
        "false_accept_rate": false_accepts / negative if negative else 0.0,
        "false_reject_rate": false_rejects / positive if positive else 0.0,
        "calibration_error": calibration,
        "brier_score": sum((p - g) ** 2 for p, g in probabilities) / len(samples),
        "candidate_accuracy": sum(row["candidate"]["gold"] for row in cases) / len(cases),
        "baseline_accuracy": sum(row["baseline"]["gold"] for row in cases) / len(cases),
        "jointly_wrong_cases": len(jointly_wrong),
        "correlated_false_accepts": correlated,
        "correlated_false_accept_rate": correlated / len(jointly_wrong) if jointly_wrong else 0.0,
    }


def qualification_reasons(metrics, policy, binding):
    reasons = []
    if metrics["candidate_accuracy"] < policy.min_candidate_accuracy:
        reasons.append("candidate_accuracy_below_threshold")
    if metrics["baseline_accuracy"] - metrics["candidate_accuracy"] > policy.max_accuracy_regression:
        reasons.append("candidate_regressed_from_baseline")
    for metric, threshold in (
        ("calibration_error", policy.max_calibration_error),
        ("false_accept_rate", policy.max_false_accept_rate),
        ("false_reject_rate", policy.max_false_reject_rate),
        ("correlated_false_accept_rate", policy.max_correlated_false_accept_rate),
    ):
        if metrics[metric] > threshold:
            reasons.append(metric + "_exceeded")
    if (
        metrics["positive_samples"] < policy.min_positive_samples
        or metrics["negative_samples"] < policy.min_negative_samples
    ):
        reasons.append("insufficient_labeled_class_coverage")
    if policy.require_disjoint_verifier_training and binding["shared_training_fingerprints"]:
        reasons.append("verifier_training_overlaps_generator_training")
    return tuple(reasons)


@dataclass(frozen=True, slots=True)
class MeasuredVerifierReceipt:
    run_id: str
    binding_digest: str
    cases_digest: str
    metrics_json: str

    def __post_init__(self):
        text(self.run_id, "run_id", 256)
        sha(self.binding_digest, "binding_digest")
        sha(self.cases_digest, "cases_digest")
        if not isinstance(decode(self.metrics_json), dict):
            raise MeasuredVerifierError("measured metrics must be an object")

    @property
    def metrics(self):
        return decode(self.metrics_json)

    @property
    def digest(self):
        return digest(asdict(self))


@dataclass(frozen=True, slots=True)
class MeasuredVerifierQualification:
    receipt_digest: str
    binding_digest: str
    verifier_model_digest: str
    status: str
    reasons: tuple[str, ...]

    def __post_init__(self):
        for name in ("receipt_digest", "binding_digest", "verifier_model_digest"):
            sha(getattr(self, name), name)
        if self.status not in {"qualified_verifier_candidate", "rejected"}:
            raise MeasuredVerifierError("unsupported measured qualification status")
        if not isinstance(self.reasons, tuple) or len(set(self.reasons)) != len(self.reasons):
            raise MeasuredVerifierError("qualification reasons must be a unique tuple")
        for reason in self.reasons:
            text(reason, "qualification reason")
        if (self.status == "rejected") != bool(self.reasons):
            raise MeasuredVerifierError("qualification status and reasons disagree")

    @property
    def production_promotion_authorized(self):
        return False

    @property
    def digest(self):
        return digest(asdict(self))


class MeasuredVerifierRunner:
    """Execute and resume measured verifier cases on the existing ledger owner."""

    def __init__(self, ledger: EvaluationLedger):
        from .evaluation_store import MeasuredEvaluationStore

        self._writer_token = _issue_writer_capability()
        self.store = MeasuredEvaluationStore(ledger, _writer_token=self._writer_token)

    async def evaluate(
        self,
        run_id: str,
        *,
        candidate: EvaluationModelSource,
        baseline: EvaluationModelSource,
        verifier: EvaluationModelSource,
        suite: EvaluationSuite,
        policy: VerifierGatePolicy | None = None,
        seed: int = 0,
        worker_id: str = "local-verifier-worker",
        lease_seconds: int = 30,
    ):
        validate_suite(suite)
        integer(seed, "seed", maximum=(1 << 63) - 1 - MAX_CASES * 4)
        policy = policy or VerifierGatePolicy()
        if not isinstance(policy, VerifierGatePolicy) or any(
            not isinstance(source, EvaluationModelSource) for source in (candidate, baseline, verifier)
        ):
            raise TypeError("issued model sources and verifier policy are required")
        sources = (candidate, baseline, verifier)
        for source in sources:
            source.assert_current()
        if len({source.payload["model_digest"] for source in sources}) != 3:
            raise MeasuredVerifierError("candidate, baseline and verifier require distinct local models")
        heldout = {_fingerprint(case.prompt) for case in suite.cases} | {
            _fingerprint(case.prompt + "\n" + case.expected_substring) for case in suite.cases
        }
        if any(heldout.intersection(source.payload["document_fingerprints"]) for source in sources):
            raise MeasuredVerifierError("held-out sample is present in observed training documents")
        shared = set(verifier.payload["document_fingerprints"]) & (
            set(candidate.payload["document_fingerprints"]) | set(baseline.payload["document_fingerprints"])
        )
        binding = {
            "schema_version": 1,
            "candidate": candidate.payload,
            "baseline": baseline.payload,
            "verifier": verifier.payload,
            "suite": suite.as_dict(),
            "seed": seed,
            "policy": asdict(policy),
            "shared_training_fingerprints": sorted(shared),
        }
        epoch = self.store.start(run_id, binding, worker_id, lease_seconds)
        if epoch is None:
            return self.store.receipt(run_id)
        judge = LocalVerifier(verifier)
        try:
            for index, case in enumerate(suite.cases):
                if self.store.case(run_id, index) is not None:
                    continue
                self.store.renew(run_id, worker_id, epoch, lease_seconds)
                row = {"case_id": case.case_id, "index": index}
                for offset, (role, source) in enumerate((("candidate", candidate), ("baseline", baseline))):
                    answer = await _generate(
                        source, case.prompt, case.max_output_tokens, seed + index * 4 + offset
                    )
                    judgment = await judge.judge(
                        case.prompt, answer["output"], seed=seed + index * 4 + offset + 2
                    )
                    row[role] = {
                        "answer": answer,
                        "judgment": judgment,
                        "gold": evaluation_case_passes(case, answer["output"]),
                    }
                with source_authority(sources):
                    self.store.record_case(run_id, index, row, worker_id, epoch, _token=self._writer_token)
            with source_authority(sources):
                return self.store.complete(run_id, worker_id, epoch, _token=self._writer_token)
        except BaseException:
            self.store.release(run_id, worker_id, epoch)
            raise

    def receipt(self, run_id: str):
        return self.store.receipt(run_id)

    def qualify(
        self,
        receipt: MeasuredVerifierReceipt,
        *,
        candidate: EvaluationModelSource,
        baseline: EvaluationModelSource,
        verifier: EvaluationModelSource,
    ):
        sources = (candidate, baseline, verifier)
        if any(not isinstance(source, EvaluationModelSource) for source in sources):
            raise TypeError("qualification requires current issued evaluation model sources")
        with source_authority(sources):
            return self.store.qualify(receipt, sources=sources, _token=self._writer_token)

    def qualified_verifier(self, qualification: MeasuredVerifierQualification, source: EvaluationModelSource):
        binding = self.store.require_qualification(qualification)
        if source.payload != binding["verifier"]:
            raise MeasuredVerifierError("qualified verifier source identity mismatch")
        source.assert_current()
        return LocalVerifier(source)
