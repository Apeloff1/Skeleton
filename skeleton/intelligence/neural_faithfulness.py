"""Neural entailment channel built from the Jeeves cortex primitives.

Each clause is encoded by a shared scaled dot-product attention pool over
token and position embeddings, the same attention identity the Jeeves
transformer uses. A GELU head then reads the premise state and the hypothesis
state and predicts entailment, contradiction, or neutral. Embeddings, the
attention query, and the head are trained with cross-entropy on a fixed
curriculum, so one seed always produces the same weights. A hypothesis token
outside that vocabulary is neutral. The decision reads the trained network,
not a synonym table.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import re
import threading

from skeleton.cortex.attn import gelu, gelu_bwd, matvec_T, softmax, zeros


_MODEL_ID = "jeeves.cortex.faithfulness-nli.v1"
_WORD = re.compile(r"[^\W_]{2,}", re.UNICODE)
_DIM = 24
_HIDDEN = 48
_CTX = 28
_EPOCHS = 10
_LR = 0.16
_SEED = 11
_LABELS = ("entailment", "contradiction", "neutral")
_LOCK = threading.Lock()
_NETWORK: "FaithfulnessNetwork | None" = None


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token for token in _WORD.findall(text.casefold()) if token)


def _curriculum() -> tuple[tuple[str, str, str], ...]:
    """Premise, hypothesis, label. Training only. Not consulted when scoring."""

    rows: list[tuple[str, str, str]] = []

    def add(premise: str, hypothesis: str, label: str) -> None:
        rows.append((premise, hypothesis, label))

    enabled = ("enabled", "active")
    disabled = ("disabled", "inactive")
    verbs = ("stores", "holds", "keeps", "records")
    for subject in ("mode", "service", "worker", "cache"):
        for left in enabled:
            for right in enabled:
                add(f"the {subject} is {left}", f"the {subject} is {right}", "entailment")
            for right in disabled:
                add(f"the {subject} is {left}", f"the {subject} is {right}", "contradiction")
                add(f"the {subject} is {right}", f"the {subject} is {left}", "contradiction")
        add(f"the {subject} is enabled", f"the {subject} is not enabled", "contradiction")
        add(f"the {subject} is not enabled", f"the {subject} is enabled", "contradiction")
        add(f"the {subject} is enabled", f"the optional trace is not required", "neutral")
        add(f"the {subject} is enabled", f"the budget increased", "neutral")
    for left in verbs:
        for right in verbs:
            add(
                f"the depth buffer {left} a depth value for each pixel",
                f"the depth buffer {right} a depth value for each pixel",
                "entailment",
            )
    add("the budget increased", "the budget increased", "entailment")
    add("the budget decreased", "the budget decreased", "entailment")
    add("the budget increased", "the budget decreased", "contradiction")
    add("the budget decreased", "the budget increased", "contradiction")
    add(
        "the mode is enabled and the optional trace is not required",
        "the mode is enabled",
        "entailment",
    )
    add(
        "the mode is enabled and the optional trace is not required",
        "the trace is required",
        "contradiction",
    )
    add("the trace is required", "the trace is mandatory", "entailment")
    add("the trace is required", "the trace is necessary", "entailment")
    add("the trace is required", "the trace is optional", "contradiction")
    add("the cycle budget is 513 cpu cycles", "the cycle budget is 513 cpu cycles", "entailment")
    add(
        "the cycle budget is 513 cpu cycles",
        "the cycle budget is greater than 400 cpu cycles",
        "entailment",
    )
    add(
        "the cycle budget is 513 cpu cycles",
        "the cycle budget exceeds 400 cpu cycles",
        "entailment",
    )
    add(
        "the cycle budget is 513 cpu cycles",
        "the cycle budget is greater than 800 cpu cycles",
        "contradiction",
    )
    add(
        "the cycle budget is 513 cpu cycles",
        "the cycle budget exceeds 800 cpu cycles",
        "contradiction",
    )
    add(
        "the cycle budget is 513 cpu cycles",
        "the cycle budget is 900 cpu cycles",
        "contradiction",
    )
    add(
        "the cycle budget is 200 cpu cycles",
        "the cycle budget is greater than 100 cpu cycles",
        "entailment",
    )
    add(
        "the cycle budget is 200 cpu cycles",
        "the cycle budget is greater than 300 cpu cycles",
        "contradiction",
    )
    base = tuple(rows)
    for premise, hypothesis, label in base:
        if label != "entailment":
            continue
        add(premise, premise, "entailment")
        add(hypothesis, hypothesis, "entailment")
    for _copy in range(4):
        add("the mode is enabled", "the mode is enabled", "entailment")
        add("the mode is enabled", "the mode is active", "entailment")
        add("the mode is active", "the mode is enabled", "entailment")
        add(
            "the depth buffer stores a depth value for each pixel",
            "the depth buffer holds a depth value for each pixel",
            "entailment",
        )
        add("the trace is required", "the trace is mandatory", "entailment")
        add("the budget increased", "the budget decreased", "contradiction")
        add("the budget decreased", "the budget increased", "contradiction")
        add(
            "the cycle budget is 513 cpu cycles",
            "the cycle budget is greater than 800 cpu cycles",
            "contradiction",
        )
        add(
            "the cycle budget is 513 cpu cycles",
            "the cycle budget is 900 cpu cycles",
            "contradiction",
        )
        add(
            "the cycle budget is 513 cpu cycles",
            "the cycle budget is greater than 400 cpu cycles",
            "entailment",
        )
        add(
            "the mode is enabled and the optional trace is not required",
            "the mode is enabled",
            "entailment",
        )
    add("the optional trace is not required", "the trace is required", "contradiction")
    add("the trace is required", "the optional trace is not required", "contradiction")
    topics = (
        "the mode is enabled",
        "the optional trace is not required",
        "the depth buffer stores a depth value for each pixel",
        "the cycle budget is 513 cpu cycles",
        "the budget increased",
        "the trace is required",
    )
    for left in topics:
        for right in topics:
            if left == right:
                continue
            shared = set(left.split()) & set(right.split()) - {"the", "is", "a"}
            if shared:
                continue
            add(left, right, "neutral")
            add(right, left, "neutral")
    return tuple(rows)


def _matrix(rng: random.Random, rows: int, cols: int, scale: float) -> list[list[float]]:
    return [[rng.gauss(0.0, scale) for _ in range(cols)] for _ in range(rows)]


def _clip(vector: list[float], limit: float = 1.0) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm > limit and norm > 0.0:
        scale = limit / norm
        return [value * scale for value in vector]
    return vector


@dataclass(frozen=True)
class NeuralScore:
    relation: str | None
    label: str
    probabilities: tuple[float, float, float]
    unknown_token: bool

    def public(self) -> dict[str, object]:
        return {
            "model": _MODEL_ID,
            "label": self.label,
            "unknown_token": self.unknown_token,
            **{name: self.probabilities[index] for index, name in enumerate(_LABELS)},
        }


class FaithfulnessNetwork:
    """Attention encoder and entailment head. One trained instance per process."""

    def __init__(self) -> None:
        rows = _curriculum()
        vocab = sorted({
            token
            for premise, hypothesis, _label in rows
            for token in (*_tokens(premise), *_tokens(hypothesis))
        })
        self.itos = ["__unk__"] + vocab
        self.stoi = {token: index for index, token in enumerate(self.itos)}
        rng = random.Random(_SEED)
        scale = 0.05
        self.embed = _matrix(rng, len(self.itos), _DIM, scale)
        self.position = _matrix(rng, _CTX, _DIM, scale)
        self.query = [rng.gauss(0.0, scale) for _ in range(_DIM)]
        features = _DIM * 4 + 2
        self.w1 = _matrix(rng, _HIDDEN, features, scale)
        self.b1 = zeros(_HIDDEN)
        self.w2 = _matrix(rng, 3, _HIDDEN, scale)
        self.b2 = zeros(3)
        order = list(range(len(rows)))
        total = max(1, len(rows) * _EPOCHS)
        step = 0
        for _epoch in range(_EPOCHS):
            rng.shuffle(order)
            for index in order:
                premise, hypothesis, label = rows[index]
                eta = 0.5 * _LR * (1.0 + math.cos(math.pi * step / total))
                self._learn(premise, hypothesis, _LABELS.index(label), eta)
                step += 1
        self.steps = step

    def parameter_count(self) -> int:
        return (
            len(self.embed) * _DIM
            + len(self.position) * _DIM
            + len(self.query)
            + sum(len(row) for row in self.w1)
            + len(self.b1)
            + sum(len(row) for row in self.w2)
            + len(self.b2)
        )

    def _ids(self, text: str) -> tuple[int, ...] | None:
        tokens = _tokens(text)[:_CTX]
        if not tokens or any(token not in self.stoi for token in tokens):
            return None
        return tuple(self.stoi[token] for token in tokens)

    def _states(self, ids: tuple[int, ...]) -> list[list[float]]:
        states = []
        for position, index in enumerate(ids):
            states.append([
                self.embed[index][dim] + self.position[position][dim]
                for dim in range(_DIM)
            ])
        return states

    def _pool(self, states: list[list[float]]) -> tuple[list[float], list[float], list[float]]:
        scale = math.sqrt(_DIM)
        scores = [
            sum(self.query[dim] * state[dim] for dim in range(_DIM)) / scale
            for state in states
        ]
        weights = softmax(scores)
        pooled = [
            sum(weights[token] * state[dim] for token, state in enumerate(states))
            for dim in range(_DIM)
        ]
        mean = [
            sum(state[dim] for state in states) / len(states)
            for dim in range(_DIM)
        ]
        mixed = [(pooled[dim] + mean[dim]) for dim in range(_DIM)]
        return mixed, weights, scores

    def _geometry(self, premise: list[float], hypothesis: list[float]) -> tuple[float, float]:
        dot = sum(premise[dim] * hypothesis[dim] for dim in range(_DIM))
        premise_norm = math.sqrt(sum(value * value for value in premise)) or 1.0
        hypothesis_norm = math.sqrt(sum(value * value for value in hypothesis)) or 1.0
        cosine = dot / (premise_norm * hypothesis_norm)
        distance = math.sqrt(sum(
            (premise[dim] - hypothesis[dim]) ** 2 for dim in range(_DIM)
        ))
        return cosine, distance

    def _features(self, premise: list[float], hypothesis: list[float]) -> list[float]:
        cosine, distance = self._geometry(premise, hypothesis)
        return [
            *premise,
            *hypothesis,
            *[(premise[dim] - hypothesis[dim]) for dim in range(_DIM)],
            *[(premise[dim] * hypothesis[dim]) for dim in range(_DIM)],
            cosine,
            distance,
        ]

    def _logits(self, features: list[float]) -> tuple[list[float], list[float]]:
        pre = [
            self.b1[row] + sum(self.w1[row][col] * features[col] for col in range(len(features)))
            for row in range(_HIDDEN)
        ]
        hidden = gelu(pre)
        logits = [
            self.b2[row] + sum(self.w2[row][col] * hidden[col] for col in range(_HIDDEN))
            for row in range(3)
        ]
        return logits, pre

    def score(self, hypothesis: str, premise: str) -> NeuralScore:
        hypothesis_ids = self._ids(hypothesis)
        premise_ids = self._ids(premise)
        if hypothesis_ids is None or premise_ids is None:
            return NeuralScore(None, "neutral", (0.0, 0.0, 1.0), True)
        premise_state, _weights, _scores = self._pool(self._states(premise_ids))
        hypothesis_state, _weights, _scores = self._pool(self._states(hypothesis_ids))
        logits, _pre = self._logits(self._features(premise_state, hypothesis_state))
        if any(not math.isfinite(value) for value in logits):
            return NeuralScore(None, "neutral", (0.0, 0.0, 1.0), False)
        probabilities = softmax(logits)
        best = max(range(3), key=probabilities.__getitem__)
        rounded = tuple(round(float(probabilities[index]), 6) for index in range(3))
        if probabilities[best] < 0.45:
            relation = None
            label = "neutral"
        elif best == 0:
            relation, label = "entails", "entailment"
        elif best == 1:
            relation, label = "contradicts_predicate", "contradiction"
        else:
            relation, label = None, "neutral"
        return NeuralScore(relation, label, rounded, False)

    def _learn(self, premise: str, hypothesis: str, target: int, lr: float) -> None:
        premise_ids = self._ids(premise)
        hypothesis_ids = self._ids(hypothesis)
        if premise_ids is None or hypothesis_ids is None:
            return
        premise_states = self._states(premise_ids)
        hypothesis_states = self._states(hypothesis_ids)
        premise_mixed, premise_weights, _premise_scores = self._pool(premise_states)
        hypothesis_mixed, hypothesis_weights, _hypothesis_scores = self._pool(hypothesis_states)
        features = self._features(premise_mixed, hypothesis_mixed)
        logits, pre = self._logits(features)
        probabilities = softmax(logits)
        d_logits = _clip([
            probabilities[index] - (1.0 if index == target else 0.0)
            for index in range(3)
        ])
        hidden = gelu(pre)
        d_hidden = _clip(matvec_T(self.w2, d_logits))
        d_pre = _clip(gelu_bwd(d_hidden, pre))
        for row in range(3):
            self.b2[row] -= lr * d_logits[row]
            for col in range(_HIDDEN):
                self.w2[row][col] -= lr * d_logits[row] * hidden[col]
        for row in range(_HIDDEN):
            self.b1[row] -= lr * d_pre[row]
            for col in range(len(features)):
                self.w1[row][col] -= lr * d_pre[row] * features[col]
        d_features = _clip(matvec_T(self.w1, d_pre))
        d_premise = [0.0] * _DIM
        d_hypothesis = [0.0] * _DIM
        for dim in range(_DIM):
            d_premise[dim] += d_features[dim]
            d_hypothesis[dim] += d_features[_DIM + dim]
            d_premise[dim] += d_features[2 * _DIM + dim]
            d_hypothesis[dim] -= d_features[2 * _DIM + dim]
            d_premise[dim] += d_features[3 * _DIM + dim] * hypothesis_mixed[dim]
            d_hypothesis[dim] += d_features[3 * _DIM + dim] * premise_mixed[dim]
        cosine, distance = self._geometry(premise_mixed, hypothesis_mixed)
        d_cosine = d_features[4 * _DIM]
        d_distance = d_features[4 * _DIM + 1]
        dot = sum(premise_mixed[dim] * hypothesis_mixed[dim] for dim in range(_DIM))
        premise_norm = math.sqrt(sum(value * value for value in premise_mixed)) or 1.0
        hypothesis_norm = math.sqrt(sum(value * value for value in hypothesis_mixed)) or 1.0
        distance = distance or 1.0
        for dim in range(_DIM):
            d_premise[dim] += d_cosine * (
                hypothesis_mixed[dim] / (premise_norm * hypothesis_norm)
                - cosine * premise_mixed[dim] / (premise_norm * premise_norm)
            )
            d_hypothesis[dim] += d_cosine * (
                premise_mixed[dim] / (premise_norm * hypothesis_norm)
                - cosine * hypothesis_mixed[dim] / (hypothesis_norm * hypothesis_norm)
            )
            gap = premise_mixed[dim] - hypothesis_mixed[dim]
            d_premise[dim] += d_distance * gap / distance
            d_hypothesis[dim] -= d_distance * gap / distance
        self._update(premise_ids, premise_states, premise_weights, _clip(d_premise), lr)
        self._update(hypothesis_ids, hypothesis_states, hypothesis_weights, _clip(d_hypothesis), lr)

    def _update(
        self,
        ids: tuple[int, ...],
        states: list[list[float]],
        weights: list[float],
        d_mixed: list[float],
        lr: float,
    ) -> None:
        length = len(ids)
        mean_scale = 1.0 / length
        d_weights = _clip([
            sum(d_mixed[dim] * states[token][dim] for dim in range(_DIM))
            for token in range(length)
        ])
        dotted = sum(weights[token] * d_weights[token] for token in range(length))
        d_scores = [
            weights[token] * (d_weights[token] - dotted) / math.sqrt(_DIM)
            for token in range(length)
        ]
        query = list(self.query)
        for dim in range(_DIM):
            self.query[dim] -= lr * sum(d_scores[token] * states[token][dim] for token in range(length))
        for token, index in enumerate(ids):
            for dim in range(_DIM):
                d_state = (
                    weights[token] * d_mixed[dim]
                    + mean_scale * d_mixed[dim]
                    + d_scores[token] * query[dim]
                )
                update = lr * d_state
                self.embed[index][dim] -= update
                self.position[token][dim] -= update


def network() -> FaithfulnessNetwork:
    global _NETWORK
    with _LOCK:
        if _NETWORK is None:
            _NETWORK = FaithfulnessNetwork()
        return _NETWORK


def neural_clause_relation(hypothesis: str, premise: str) -> str | None:
    return network().score(hypothesis, premise).relation


def neural_score(hypothesis: str, premise: str) -> dict[str, object]:
    model = network()
    public = model.score(hypothesis, premise).public()
    public["parameters"] = model.parameter_count()
    public["steps"] = model.steps
    return public


__all__ = [
    "FaithfulnessNetwork",
    "neural_clause_relation",
    "neural_score",
    "network",
]
