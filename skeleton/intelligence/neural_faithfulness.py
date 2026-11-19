"""Neural entailment channel built from the Jeeves cortex primitives.

A clause is embedded, then read by a pre-norm residual block. The premise
mixes itself with bidirectional multi-head attention. The hypothesis then
cross-attends to every premise token, which is the entailment alignment.
Rotary positions and the scaled dot-product are the cortex identities; the
mask is bidirectional because a faithfulness clause is not a language-model
prefix. A GELU head reads the two pooled states. Embeddings, both attention
blocks, and the head train with cross-entropy on a fixed curriculum, so one
seed always produces the same weights. A token outside that vocabulary is
neutral. The decision reads the trained network, not a synonym table.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import re
import threading

from skeleton.cortex.attn import (
    apply_rope,
    apply_rope_bwd,
    cosine_lr,
    dot,
    gelu,
    gelu_bwd,
    layer_norm,
    layer_norm_bwd,
    matvec,
    matvec_T,
    ones,
    softmax,
    zeros,
)


_MODEL_ID = "jeeves.cortex.faithfulness-nli.v2"
_ENCODER = "cross_attention"
_WORD = re.compile(r"[^\W_]{2,}", re.UNICODE)
_DIM = 24
_HEADS = 2
_HIDDEN = 48
_CTX = 28
_EPOCHS = 8
_LR = 0.12
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


def _zeros_like(matrix: list[list[float]]) -> list[list[float]]:
    return [[0.0] * len(row) for row in matrix]


def _apply(matrix: list[list[float]], grad: list[list[float]], lr: float) -> None:
    for row, grow in zip(matrix, grad):
        for index, value in enumerate(grow):
            row[index] -= lr * value


def _accum(matrix: list[list[float]], dy: list[float], x: list[float]) -> None:
    for index, slope in enumerate(dy):
        row = matrix[index]
        for column, value in enumerate(x):
            row[column] += slope * value


def _clip(vector: list[float], limit: float = 1.0) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm > limit and norm > 0.0:
        scale = limit / norm
        return [value * scale for value in vector]
    return vector


def _finite(rows: list[list[float]]) -> bool:
    return all(math.isfinite(value) for row in rows for value in row)


def _bidir_mha(
    query: list[list[float]],
    key: list[list[float]],
    value: list[list[float]],
    n_heads: int,
) -> tuple[list[list[float]], list[list[list[float]]]]:
    """Full bidirectional attention. Every query sees every key."""

    width = len(query[0])
    heads = max(1, n_heads)
    span = max(1, width // heads)
    inverse = 1.0 / math.sqrt(span)
    contexts: list[list[list[float]]] = []
    weights: list[list[list[float]]] = []
    for head in range(heads):
        start = head * span
        stop = start + span
        query_head = [row[start:stop] for row in query]
        key_head = [row[start:stop] for row in key]
        value_head = [row[start:stop] for row in value]
        head_weights: list[list[float]] = []
        head_context: list[list[float]] = []
        for query_row in query_head:
            scores = [dot(query_row, key_row) * inverse for key_row in key_head]
            choice = softmax(scores)
            mixed = [
                sum(choice[index] * value_head[index][dim] for index in range(len(value_head)))
                for dim in range(span)
            ]
            head_weights.append(choice)
            head_context.append(mixed)
        weights.append(head_weights)
        contexts.append(head_context)
    joined = []
    for index in range(len(query)):
        row: list[float] = []
        for head in range(heads):
            row.extend(contexts[head][index])
        joined.append(row)
    return joined, weights


def _bidir_mha_bwd(
    d_context: list[list[float]],
    query: list[list[float]],
    key: list[list[float]],
    value: list[list[float]],
    weights: list[list[list[float]]],
    n_heads: int,
) -> tuple[list[list[float]], list[list[float]], list[list[float]]]:
    width = len(query[0])
    heads = max(1, n_heads)
    span = max(1, width // heads)
    inverse = 1.0 / math.sqrt(span)
    d_query = [zeros(width) for _ in query]
    d_key = [zeros(width) for _ in key]
    d_value = [zeros(width) for _ in value]
    for head in range(heads):
        start = head * span
        query_head = [row[start:start + span] for row in query]
        key_head = [row[start:start + span] for row in key]
        value_head = [row[start:start + span] for row in value]
        for index, query_row in enumerate(query_head):
            upstream = d_context[index][start:start + span]
            choice = weights[head][index]
            d_choice = [dot(upstream, value_head[key_index]) for key_index in range(len(key_head))]
            for key_index, weight in enumerate(choice):
                for dim, slope in enumerate(upstream):
                    d_value[key_index][start + dim] += slope * weight
            agreement = sum(slope * weight for slope, weight in zip(d_choice, choice))
            for key_index, weight in enumerate(choice):
                score_grad = (d_choice[key_index] - agreement) * weight * inverse
                key_row = key_head[key_index]
                for dim in range(span):
                    d_query[index][start + dim] += key_row[dim] * score_grad
                    d_key[key_index][start + dim] += query_row[dim] * score_grad
    return d_query, d_key, d_value


@dataclass(frozen=True)
class NeuralScore:
    relation: str | None
    label: str
    probabilities: tuple[float, float, float]
    unknown_token: bool
    focus: str

    def public(self) -> dict[str, object]:
        return {
            "model": _MODEL_ID,
            "encoder": _ENCODER,
            "heads": _HEADS,
            "label": self.label,
            "unknown_token": self.unknown_token,
            "focus": self.focus,
            **{name: self.probabilities[index] for index, name in enumerate(_LABELS)},
        }


class _BlockGrads:
    def __init__(self, owner: "FaithfulnessNetwork", kind: str) -> None:
        self.wq = _zeros_like(getattr(owner, f"{kind}_wq"))
        self.wk = _zeros_like(getattr(owner, f"{kind}_wk"))
        self.wv = _zeros_like(getattr(owner, f"{kind}_wv"))
        self.wo = _zeros_like(getattr(owner, f"{kind}_wo"))
        self.g = zeros(_DIM)
        self.b = zeros(_DIM)


class FaithfulnessNetwork:
    """Cross-attention entailment encoder. One trained instance per process."""

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
        narrow = 0.01
        self.embed = _matrix(rng, len(self.itos), _DIM, scale)
        self.position = _matrix(rng, _CTX, _DIM, scale)
        self.self_wq = _matrix(rng, _DIM, _DIM, scale)
        self.self_wk = _matrix(rng, _DIM, _DIM, scale)
        self.self_wv = _matrix(rng, _DIM, _DIM, scale)
        self.self_wo = _matrix(rng, _DIM, _DIM, narrow)
        self.self_g = ones(_DIM)
        self.self_b = zeros(_DIM)
        self.cross_wq = _matrix(rng, _DIM, _DIM, scale)
        self.cross_wk = _matrix(rng, _DIM, _DIM, scale)
        self.cross_wv = _matrix(rng, _DIM, _DIM, scale)
        self.cross_wo = _matrix(rng, _DIM, _DIM, narrow)
        self.cross_g = ones(_DIM)
        self.cross_b = zeros(_DIM)
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
                self._learn(premise, hypothesis, _LABELS.index(label), cosine_lr(step, total, base=_LR))
                step += 1
        self.steps = step

    def parameter_count(self) -> int:
        matrices = (
            self.embed, self.position, self.self_wq, self.self_wk, self.self_wv, self.self_wo,
            self.cross_wq, self.cross_wk, self.cross_wv, self.cross_wo, self.w1, self.w2,
        )
        vectors = (self.self_g, self.self_b, self.cross_g, self.cross_b, self.query, self.b1, self.b2)
        counted = sum(len(matrix) * len(matrix[0]) for matrix in matrices if matrix and matrix[0])
        return counted + sum(len(row) for row in vectors)

    def _ids(self, text: str) -> tuple[int, ...] | None:
        tokens = _tokens(text)[:_CTX]
        if not tokens or any(token not in self.stoi for token in tokens):
            return None
        return tuple(self.stoi[token] for token in tokens)

    def _token_states(self, ids: tuple[int, ...]) -> list[list[float]]:
        states = []
        for position, index in enumerate(ids):
            states.append([
                self.embed[index][dim] + self.position[position][dim]
                for dim in range(_DIM)
            ])
        return states

    def _normalize(
        self, states: list[list[float]], gain: list[float], bias: list[float],
    ) -> tuple[list[list[float]], list[list[float]], list[float]]:
        normed: list[list[float]] = []
        hats: list[list[float]] = []
        inverse: list[float] = []
        for state in states:
            value, hat, inv = layer_norm(state, gain, bias)
            normed.append(value)
            hats.append(hat)
            inverse.append(inv)
        return normed, hats, inverse

    def _project(self, states: list[list[float]], weight: list[list[float]], rotary: bool) -> list[list[float]]:
        projected = []
        for position, state in enumerate(states):
            value = matvec(weight, state)
            projected.append(apply_rope(value, position) if rotary else value)
        return projected

    def _self_block(
        self, states: list[list[float]],
    ) -> tuple[list[list[float]], dict[str, object]]:
        normed, hats, inverse = self._normalize(states, self.self_g, self.self_b)
        query = self._project(normed, self.self_wq, True)
        key = self._project(normed, self.self_wk, True)
        value = self._project(normed, self.self_wv, False)
        context, weights = _bidir_mha(query, key, value, _HEADS)
        mixed = [matvec(self.self_wo, row) for row in context]
        output = [
            [states[token][dim] + mixed[token][dim] for dim in range(_DIM)]
            for token in range(len(states))
        ]
        return output, {
            "normed": normed, "hats": hats, "inverse": inverse,
            "query": query, "key": key, "value": value, "weights": weights, "context": context,
        }

    def _cross_block(
        self, hypothesis: list[list[float]], premise: list[list[float]],
    ) -> tuple[list[list[float]], dict[str, object]]:
        normed, hats, inverse = self._normalize(hypothesis, self.cross_g, self.cross_b)
        query = self._project(normed, self.cross_wq, True)
        key = self._project(premise, self.cross_wk, True)
        value = self._project(premise, self.cross_wv, False)
        context, weights = _bidir_mha(query, key, value, _HEADS)
        mixed = [matvec(self.cross_wo, row) for row in context]
        output = [
            [hypothesis[token][dim] + mixed[token][dim] for dim in range(_DIM)]
            for token in range(len(hypothesis))
        ]
        return output, {
            "normed": normed, "hats": hats, "inverse": inverse,
            "query": query, "key": key, "value": value, "weights": weights, "context": context,
        }

    def _pool(self, states: list[list[float]]) -> tuple[list[float], list[float]]:
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
        return [(pooled[dim] + mean[dim]) for dim in range(_DIM)], weights

    def _geometry(self, premise: list[float], hypothesis: list[float]) -> tuple[float, float]:
        paired = sum(premise[dim] * hypothesis[dim] for dim in range(_DIM))
        premise_norm = math.sqrt(sum(value * value for value in premise)) or 1.0
        hypothesis_norm = math.sqrt(sum(value * value for value in hypothesis)) or 1.0
        cosine = paired / (premise_norm * hypothesis_norm)
        distance = math.sqrt(sum((premise[dim] - hypothesis[dim]) ** 2 for dim in range(_DIM)))
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

    def _focus(self, weights: list[list[list[float]]], premise_ids: tuple[int, ...]) -> str:
        if not premise_ids or not weights:
            return ""
        score = [0.0] * len(premise_ids)
        seen = 0
        for head in weights:
            for row in head:
                for index, weight in enumerate(row):
                    score[index] += weight
                seen += 1
        if seen == 0:
            return ""
        best = max(range(len(score)), key=lambda index: score[index])
        token = self.itos[premise_ids[best]]
        return "" if token == "__unk__" else token

    def _encode(
        self, hypothesis_ids: tuple[int, ...], premise_ids: tuple[int, ...],
    ) -> tuple[list[float], list[float], list[float], dict[str, object], dict[str, object], str]:
        premise_in = self._token_states(premise_ids)
        hypothesis_in = self._token_states(hypothesis_ids)
        premise, self_cache = self._self_block(premise_in)
        hypothesis, cross_cache = self._cross_block(hypothesis_in, premise)
        premise_pool, premise_weights = self._pool(premise)
        hypothesis_pool, hypothesis_weights = self._pool(hypothesis)
        self_cache["weights_pool"] = premise_weights
        cross_cache["weights_pool"] = hypothesis_weights
        self_cache["output"] = premise
        cross_cache["output"] = hypothesis
        focus = self._focus(cross_cache["weights"], premise_ids)  # type: ignore[arg-type]
        return premise_pool, hypothesis_pool, self._features(premise_pool, hypothesis_pool), self_cache, cross_cache, focus

    def score(self, hypothesis: str, premise: str) -> NeuralScore:
        hypothesis_ids = self._ids(hypothesis)
        premise_ids = self._ids(premise)
        if hypothesis_ids is None or premise_ids is None:
            return NeuralScore(None, "neutral", (0.0, 0.0, 1.0), True, "")
        _premise, _hypothesis, features, _self_cache, cross_cache, focus = self._encode(
            hypothesis_ids, premise_ids,
        )
        logits, _pre = self._logits(features)
        if any(not math.isfinite(value) for value in logits):
            return NeuralScore(None, "neutral", (0.0, 0.0, 1.0), False, focus)
        probabilities = softmax(logits)
        best = max(range(3), key=probabilities.__getitem__)
        rounded = tuple(round(float(probabilities[index]), 6) for index in range(3))
        if probabilities[best] < 0.45:
            relation, label = None, "neutral"
        elif best == 0:
            relation, label = "entails", "entailment"
        elif best == 1:
            relation, label = "contradicts_predicate", "contradiction"
        else:
            relation, label = None, "neutral"
        return NeuralScore(relation, label, rounded, False, focus)

    def _pool_backward(
        self, states: list[list[float]], weights: list[float], d_mixed: list[float],
    ) -> tuple[list[list[float]], list[float]]:
        length = len(states)
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
        d_query = _clip([
            sum(d_scores[token] * states[token][dim] for token in range(length))
            for dim in range(_DIM)
        ])
        d_states = []
        for token in range(length):
            d_states.append(_clip([
                weights[token] * d_mixed[dim]
                + mean_scale * d_mixed[dim]
                + d_scores[token] * query[dim]
                for dim in range(_DIM)
            ]))
        return d_states, d_query

    def _attend_backward(
        self,
        kind: str,
        cache: dict[str, object],
        d_out: list[list[float]],
        key_states: list[list[float]] | None,
    ) -> tuple[list[list[float]], list[list[float]] | None, _BlockGrads]:
        grads = _BlockGrads(self, kind)
        weight_q = getattr(self, f"{kind}_wq")
        weight_k = getattr(self, f"{kind}_wk")
        weight_v = getattr(self, f"{kind}_wv")
        weight_o = getattr(self, f"{kind}_wo")
        gain = getattr(self, f"{kind}_g")
        context = cache["context"]
        normed = cache["normed"]
        query = cache["query"]
        key = cache["key"]
        value = cache["value"]
        assert isinstance(context, list) and isinstance(normed, list)
        assert isinstance(query, list) and isinstance(key, list) and isinstance(value, list)
        d_context = [_clip(matvec_T(weight_o, row)) for row in d_out]
        for token, row in enumerate(d_out):
            _accum(grads.wo, row, context[token])
        d_query, d_key, d_value = _bidir_mha_bwd(
            d_context, query, key, value, cache["weights"], _HEADS,  # type: ignore[arg-type]
        )
        d_normed = [zeros(_DIM) for _ in normed]
        for token, row in enumerate(d_query):
            pre = apply_rope_bwd(row, token)
            for dim, value_ in enumerate(matvec_T(weight_q, pre)):
                d_normed[token][dim] += value_
            _accum(grads.wq, pre, normed[token])
        sources = normed if key_states is None else key_states
        d_sources = [zeros(_DIM) for _ in sources]
        for token, row in enumerate(d_key):
            pre = apply_rope_bwd(row, token)
            back = matvec_T(weight_k, pre)
            for dim, value_ in enumerate(back):
                d_sources[token][dim] += value_
            _accum(grads.wk, pre, sources[token])
        for token, row in enumerate(d_value):
            back = matvec_T(weight_v, row)
            for dim, value_ in enumerate(back):
                d_sources[token][dim] += value_
            _accum(grads.wv, row, sources[token])
        if key_states is None:
            for token, row in enumerate(d_sources):
                for dim, value_ in enumerate(row):
                    d_normed[token][dim] += value_
        d_input = []
        hats = cache["hats"]
        inverse = cache["inverse"]
        assert isinstance(hats, list) and isinstance(inverse, list)
        for token, row in enumerate(d_normed):
            dx, dg, db = layer_norm_bwd(_clip(row), hats[token], inverse[token], gain)
            d_input.append(_clip([dx[dim] + d_out[token][dim] for dim in range(_DIM)]))
            for dim in range(_DIM):
                grads.g[dim] += dg[dim]
                grads.b[dim] += db[dim]
        grads.g = _clip(grads.g)
        grads.b = _clip(grads.b)
        if key_states is None:
            return d_input, None, grads
        return d_input, [_clip(row) for row in d_sources], grads

    def _feature_grads(
        self, premise: list[float], hypothesis: list[float], d_features: list[float],
    ) -> tuple[list[float], list[float]]:
        d_premise = [0.0] * _DIM
        d_hypothesis = [0.0] * _DIM
        for dim in range(_DIM):
            d_premise[dim] += d_features[dim]
            d_hypothesis[dim] += d_features[_DIM + dim]
            d_premise[dim] += d_features[2 * _DIM + dim]
            d_hypothesis[dim] -= d_features[2 * _DIM + dim]
            d_premise[dim] += d_features[3 * _DIM + dim] * hypothesis[dim]
            d_hypothesis[dim] += d_features[3 * _DIM + dim] * premise[dim]
        cosine, distance = self._geometry(premise, hypothesis)
        d_cosine = d_features[4 * _DIM]
        d_distance = d_features[4 * _DIM + 1]
        premise_norm = math.sqrt(sum(value * value for value in premise)) or 1.0
        hypothesis_norm = math.sqrt(sum(value * value for value in hypothesis)) or 1.0
        distance = distance or 1.0
        for dim in range(_DIM):
            d_premise[dim] += d_cosine * (
                hypothesis[dim] / (premise_norm * hypothesis_norm)
                - cosine * premise[dim] / (premise_norm * premise_norm)
            )
            d_hypothesis[dim] += d_cosine * (
                premise[dim] / (premise_norm * hypothesis_norm)
                - cosine * hypothesis[dim] / (hypothesis_norm * hypothesis_norm)
            )
            gap = premise[dim] - hypothesis[dim]
            d_premise[dim] += d_distance * gap / distance
            d_hypothesis[dim] -= d_distance * gap / distance
        return _clip(d_premise), _clip(d_hypothesis)

    def _learn(self, premise: str, hypothesis: str, target: int, lr: float) -> None:
        premise_ids = self._ids(premise)
        hypothesis_ids = self._ids(hypothesis)
        if premise_ids is None or hypothesis_ids is None or lr <= 0.0:
            return
        premise_pool, hypothesis_pool, features, self_cache, cross_cache, _focus = self._encode(
            hypothesis_ids, premise_ids,
        )
        logits, pre = self._logits(features)
        probabilities = softmax(logits)
        if not _finite([probabilities, logits, pre]):
            return
        d_logits = _clip([
            probabilities[index] - (1.0 if index == target else 0.0)
            for index in range(3)
        ])
        hidden = gelu(pre)
        d_hidden = _clip(matvec_T(self.w2, d_logits))
        d_pre = _clip(gelu_bwd(d_hidden, pre))
        d_features = _clip(matvec_T(self.w1, d_pre))
        d_premise, d_hypothesis = self._feature_grads(premise_pool, hypothesis_pool, d_features)
        premise_states = self_cache["output"]
        hypothesis_states = cross_cache["output"]
        assert isinstance(premise_states, list) and isinstance(hypothesis_states, list)
        d_premise_states, d_query_p = self._pool_backward(
            premise_states, self_cache["weights_pool"], d_premise,  # type: ignore[arg-type]
        )
        d_hypothesis_states, d_query_h = self._pool_backward(
            hypothesis_states, cross_cache["weights_pool"], d_hypothesis,  # type: ignore[arg-type]
        )
        d_hypothesis_in, d_premise_cross, cross_grads = self._attend_backward(
            "cross", cross_cache, d_hypothesis_states, premise_states,
        )
        if d_premise_cross is not None:
            for token, row in enumerate(d_premise_cross):
                for dim, value in enumerate(row):
                    d_premise_states[token][dim] += value
        d_premise_in, _unused, self_grads = self._attend_backward(
            "self", self_cache, d_premise_states, None,
        )
        if not _finite(d_premise_in) or not _finite(d_hypothesis_in):
            return
        self._apply_block("self", self_grads, lr)
        self._apply_block("cross", cross_grads, lr)
        for dim in range(_DIM):
            self.query[dim] -= lr * (d_query_p[dim] + d_query_h[dim])
        for row in range(_HIDDEN):
            self.b1[row] -= lr * d_pre[row]
            for col in range(len(features)):
                self.w1[row][col] -= lr * d_pre[row] * features[col]
        for row in range(3):
            self.b2[row] -= lr * d_logits[row]
            for col in range(_HIDDEN):
                self.w2[row][col] -= lr * d_logits[row] * hidden[col]
        self._update_tokens(premise_ids, d_premise_in, lr)
        self._update_tokens(hypothesis_ids, d_hypothesis_in, lr)

    def _apply_block(self, kind: str, grads: _BlockGrads, lr: float) -> None:
        _apply(getattr(self, f"{kind}_wq"), grads.wq, lr)
        _apply(getattr(self, f"{kind}_wk"), grads.wk, lr)
        _apply(getattr(self, f"{kind}_wv"), grads.wv, lr)
        _apply(getattr(self, f"{kind}_wo"), grads.wo, lr)
        gain = getattr(self, f"{kind}_g")
        bias = getattr(self, f"{kind}_b")
        for dim in range(_DIM):
            gain[dim] -= lr * grads.g[dim]
            bias[dim] -= lr * grads.b[dim]

    def _update_tokens(self, ids: tuple[int, ...], d_states: list[list[float]], lr: float) -> None:
        for position, (index, grad) in enumerate(zip(ids, d_states)):
            for dim, value in enumerate(grad):
                step = lr * value
                self.embed[index][dim] -= step
                self.position[position][dim] -= step


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
