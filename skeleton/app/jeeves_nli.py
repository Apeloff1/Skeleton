"""Pinned CPU-only three-way natural-language inference for local review.

A distinct classifier, never a second primary assistant. Explicit label
mapping is required; softmax scores are model scores, not calibrated truth.
No downloading, remote code, silent truncation or provider fallback.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import threading
import time

from skeleton.retrieval.learned_embeddings import _read_pinned, _validate_graph

SCHEMA = "skeleton.jeeves.local-nli.v1"
LABELS = ("contradiction", "neutral", "entailment")


def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def text_sha(text):
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NLIPolicy:
    label_order: tuple[str, ...]
    max_tokens: int = 512
    max_pair_bytes: int = 8192
    max_pairs: int = 24
    threads: int = 2
    output_name: str = "logits"
    confidence_floor_ppm: int = 850000
    margin_floor_ppm: int = 150000
    cache_entries: int = 128

    def __post_init__(self):
        if type(self.label_order) is not tuple or len(self.label_order) != 3 or set(self.label_order) != set(LABELS):
            raise ValueError("explicit three-class NLI label order required")
        for value, lo, hi in (
            (self.max_tokens, 8, 4096), (self.max_pair_bytes, 64, 65536),
            (self.max_pairs, 1, 64), (self.threads, 1, 16),
            (self.confidence_floor_ppm, 500001, 1000000),
            (self.margin_floor_ppm, 1, 1000000), (self.cache_entries, 0, 512),
        ):
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError("invalid NLI resource or decision envelope")
        if type(self.output_name) is not str or not 1 <= len(self.output_name) <= 128:
            raise ValueError("explicit NLI logits output required")


def classify_logits(logits, policy):
    if not isinstance(policy, NLIPolicy) or len(logits) != 3:
        raise ValueError("three logits required")
    values = tuple(float(x) for x in logits)
    if not all(math.isfinite(x) for x in values):
        raise ValueError("nonfinite local classifier output")
    peak = max(values)
    weights = [math.exp(x-peak) for x in values]
    total = sum(weights)
    probabilities = {label: round(weight/total*1000000)
                     for label, weight in zip(policy.label_order, weights)}
    ordered = sorted(probabilities, key=lambda label: (-probabilities[label], label))
    first, second = ordered[:2]
    margin = probabilities[first]-probabilities[second]
    decision = first if probabilities[first] >= policy.confidence_floor_ppm and margin >= policy.margin_floor_ppm else "uncertain"
    return {"decision": decision, "scores_ppm": probabilities, "margin_ppm": margin,
            "scores_calibrated": False}


class LocalNLIVerifier:
    def __init__(self, model_path, model_sha256, tokenizer_path, tokenizer_sha256,
                 policy, *, max_model_bytes=512*1024**2):
        if not isinstance(policy, NLIPolicy) or type(max_model_bytes) is not int or not 1 <= max_model_bytes <= 1024**3:
            raise ValueError("bounded local NLI model policy required")
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        raw = _read_pinned(model_path, model_sha256, max_model_bytes)
        tokenizer_raw = _read_pinned(tokenizer_path, tokenizer_sha256, 32*1024**2)
        _validate_graph(raw)
        tokenizer = Tokenizer.from_str(tokenizer_raw.decode("utf-8"))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = policy.threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern = False
        session = ort.InferenceSession(raw, sess_options=options, providers=["CPUExecutionProvider"])
        inputs = {item.name: item for item in session.get_inputs()}
        if ("input_ids" not in inputs or set(inputs)-{"input_ids","attention_mask","token_type_ids"}
                or any(x.type != "tensor(int64)" or len(x.shape) != 2 for x in inputs.values())):
            raise ValueError("invalid NLI inputs")
        output = {item.name: item for item in session.get_outputs()}.get(policy.output_name)
        if (output is None or len(output.shape) != 2 or output.type not in {"tensor(float)","tensor(float16)"}
                or (isinstance(output.shape[-1], int) and output.shape[-1] != 3)):
            raise ValueError("NLI must expose three classification logits")
        if session.get_providers() != ["CPUExecutionProvider"]:
            raise RuntimeError("local NLI provider drift")
        self._runtime, self._tokenizer, self._inputs = session, tokenizer, tuple(inputs)
        self.policy = policy
        self.model_sha256 = model_sha256
        self.tokenizer_sha256 = tokenizer_sha256
        self.identity = digest({"schema": SCHEMA, "model": model_sha256,
                                "tokenizer": tokenizer_sha256, "policy": asdict(policy),
                                "runtime": ort.__version__, "numpy": np.__version__,
                                "provider": "CPUExecutionProvider"})
        self._lock = threading.RLock()
        # Only digest-keyed classifier results; no source or candidate strings.
        self._cache = OrderedDict()

    def score_pairs(self, pairs, *, scope, deadline=None):
        import numpy as np
        if (type(scope) is not str or len(scope) != 64 or any(c not in "0123456789abcdef" for c in scope)
                or not isinstance(pairs, (list,tuple)) or not 1 <= len(pairs) <= self.policy.max_pairs):
            raise ValueError("bounded scoped NLI pairs required")
        if deadline is not None and (type(deadline) not in (float,int) or not math.isfinite(deadline)):
            raise ValueError("invalid classifier deadline")
        results = []
        with self._lock:
            for pair in pairs:
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("local classifier deadline exceeded")
                if (not isinstance(pair,(list,tuple)) or len(pair)!=2
                        or any(type(s) is not str or not s.strip() or "\x00" in s for s in pair)
                        or sum(len(s.encode("utf-8")) for s in pair)>self.policy.max_pair_bytes):
                    raise ValueError("invalid NLI pair")
                premise, hypothesis = pair
                key = (scope, text_sha(premise), text_sha(hypothesis))
                if key in self._cache:
                    row = self._cache.pop(key)
                    self._cache[key] = row
                    results.append(json.loads(row) | {"cache_hit": True})
                    continue
                encoded = self._tokenizer.encode(premise, pair=hypothesis, add_special_tokens=True)
                if not 1 <= len(encoded.ids) <= self.policy.max_tokens:
                    raise ValueError("NLI context exceeded; no truncation allowed")
                if 0 not in encoded.sequence_ids or 1 not in encoded.sequence_ids:
                    raise ValueError("NLI tokenizer dropped a sequence")
                payload = {"input_ids":encoded.ids,"attention_mask":encoded.attention_mask,
                           "token_type_ids":encoded.type_ids}
                output = self._runtime.run([self.policy.output_name], {
                    k:np.asarray([payload[k]],dtype=np.int64) for k in self._inputs})[0]
                if output.shape != (1,3) or not np.isfinite(output).all():
                    raise ValueError("invalid native NLI logits")
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("local classifier deadline exceeded")
                verdict = classify_logits(output[0], self.policy) | {
                    "premise_sha256":key[1],"hypothesis_sha256":key[2],
                    "token_count":len(encoded.ids),"verifier_identity":self.identity,
                }
                if self.policy.cache_entries:
                    self._cache[key] = json.dumps(verdict, sort_keys=True, allow_nan=False)
                    while len(self._cache)>self.policy.cache_entries:
                        self._cache.popitem(last=False)
                results.append(verdict | {"cache_hit":False})
        return results

    def clear_cache(self):
        with self._lock:
            self._cache.clear()


def load_nli_config(path, expected_sha256):
    path = Path(path)
    def unique(pairs):
        out = {}
        for key,value in pairs:
            if key in out:
                raise ValueError("duplicate NLI config field")
            out[key]=value
        return out
    cfg=json.loads(_read_pinned(path,expected_sha256,65536),object_pairs_hook=unique)
    if (type(cfg) is not dict or set(cfg)!={"schema","model_path","model_sha256",
            "tokenizer_path","tokenizer_sha256","policy"} or cfg["schema"]!="skeleton.local.nli-config.v1"):
        raise ValueError("invalid explicit NLI configuration")
    def relative(s):
        if type(s) is not str or not s or Path(s).is_absolute() or ".." in Path(s).parts:
            raise ValueError("local NLI artifact must be relative to config")
        return path.parent/s
    policy=cfg["policy"]
    if type(policy) is not dict or type(policy.get("label_order")) is not list:
        raise ValueError("explicit NLI label map required")
    return LocalNLIVerifier(relative(cfg["model_path"]),cfg["model_sha256"],
        relative(cfg["tokenizer_path"]),cfg["tokenizer_sha256"],
        NLIPolicy(**(policy|{"label_order":tuple(policy["label_order"])})))
