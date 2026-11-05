"""Multi-draft publication must match the authoritative verifier token by token."""

import math

import pytest

from skeleton.cortex.speculative import (
    GrammarBudgetLogitProcessor,
    SpeculativeDecoder,
    lookahead_jacobi_decode,
)


class _Model:
    V = 4
    ctx = 32
    itos = ("a", "b", "c", "d")

    def __init__(self, selector):
        self.selector = selector

    def _logits(self, context):
        selected = self.selector(tuple(context))
        return [1.0 if i == selected else 0.0 for i in range(self.V)]


def _verifier_only(model, prefix, n, processor=None):
    context = list(prefix)
    result = []
    for step in range(n):
        logits = list(model._logits(context[-model.ctx:]))
        if processor is not None:
            logits = processor.process(logits, result, steps_remaining=n - step)
        token = max(range(len(logits)), key=lambda i: (logits[i], -i))
        result.append(token)
        context.append(token)
    return tuple(result)


def test_fallback_uses_the_longest_accepted_branch_context():
    # The first draft rejects at prefix (0,), but the second draft accepts 1
    # before rejecting. Its fallback must be chosen at (0, 1), not at (0,).
    verifier = _Model(lambda context: (context[-1] + 1) % 4)
    first = _Model(lambda context: 3)
    second = _Model(lambda context: 1 if context[-1] == 0 else 0)
    result = lookahead_jacobi_decode(verifier, [first, second], [0], 2,
                                     lookahead_window=2, max_jacobi_iters=1)
    assert result["token_ids"] == (1, 2)
    assert result["token_ids"] == _verifier_only(verifier, [0], 2)
    assert result["accepted"] == 1


class _PositionProcessor:
    def process(self, logits, generated_ids, *, steps_remaining):
        result = [-100.0] * len(logits)
        result[len(generated_ids) % len(logits)] = 100.0
        return result


@pytest.mark.parametrize("window", [1, 2, 4])
def test_processor_sees_generated_prefix_once(window):
    verifier = _Model(lambda context: 0)
    drafts = [_Model(lambda context: 3), _Model(lambda context: 2)]
    processor = _PositionProcessor()
    expected = _verifier_only(verifier, [1, 2], 9, processor)
    result = lookahead_jacobi_decode(verifier, drafts, [1, 2], 9,
                                     lookahead_window=window, max_jacobi_iters=2,
                                     logit_processor=processor)
    assert result["token_ids"] == expected


@pytest.mark.parametrize("seed", range(6))
def test_multidraft_grammar_output_matches_verifier_only(seed):
    def selector(offset):
        def choose(context):
            value = seed + offset + 17
            for token in context:
                value = (value * 131 + token * 17 + 19) % 65521
            return value % 4
        return choose

    verifier = _Model(selector(0))
    drafts = [_Model(selector(7)), _Model(selector(31))]
    processor = GrammarBudgetLogitProcessor(verifier.itos, required_tokens=["c"], no_repeat_ngram_size=2)
    expected = _verifier_only(verifier, [0, 1], 9, processor)
    result = lookahead_jacobi_decode(verifier, drafts, [0, 1], 9,
                                     lookahead_window=3, max_jacobi_iters=3,
                                     logit_processor=processor)
    assert result["token_ids"] == expected


@pytest.mark.parametrize("with_constraints", [False, True])
def test_real_tiny_transformer_multidraft_matches_verifier(with_constraints):
    from skeleton.cortex.transformer import TinyTransformer
    def model(seed):
        return TinyTransformer(vocab=("alpha", "beta", "gamma"), dim=8, ctx=6,
                               n_heads=2, n_layers=1, d_ff=16, seed=seed)
    verifier, first, second = model(11), model(13), model(17)
    prefix = list(verifier._ids("alpha beta"))
    processor = (GrammarBudgetLogitProcessor(verifier.itos, required_tokens=["beta"], no_repeat_ngram_size=2)
                 if with_constraints else None)
    expected = _verifier_only(verifier, prefix, 8, processor)
    result = lookahead_jacobi_decode(verifier, [first, second], prefix, 8,
                                     lookahead_window=3, max_jacobi_iters=2,
                                     logit_processor=processor)
    assert result["token_ids"] == expected


@pytest.mark.parametrize("n", [-1, 2049, True, 2.5])
def test_lookahead_rejects_invalid_or_unbounded_output_budget(n):
    model = _Model(lambda context: 0)
    with pytest.raises(ValueError):
        lookahead_jacobi_decode(model, [model], [0], n)


def test_lookahead_rejects_excess_drafts_and_invalid_context():
    model = _Model(lambda context: 0)
    with pytest.raises(ValueError, match="draft models"):
        lookahead_jacobi_decode(model, [model] * 9, [0], 1)
    for prefix in ([], [True], [-1], [4], [0] * 16_385):
        with pytest.raises(ValueError, match="context"):
            lookahead_jacobi_decode(model, [model], prefix, 1)


def test_proposal_iterable_is_consumed_only_to_its_budget():
    consumed = []
    def draft(prefix, requested):
        assert requested == 3
        for item in range(10):
            consumed.append(item)
            if len(consumed) > 3:
                raise AssertionError("unbounded proposal iteration")
            yield item

    result = SpeculativeDecoder(max_proposals=3).decode(draft, lambda context, token: True, [0])
    assert result.accepted == (0, 1, 2)
    assert consumed == [0, 1, 2]


def test_zero_steps_do_not_call_the_draft():
    def unexpected(*args):
        raise AssertionError("zero proposals must not invoke the draft")
    result = SpeculativeDecoder().decode(unexpected, lambda context, token: True, [0], steps=0)
    assert result.proposed == 0


@pytest.mark.parametrize("value", [0, -1, 257, True, 1.5])
def test_proposal_budget_is_strict_and_bounded(value):
    with pytest.raises(ValueError):
        SpeculativeDecoder(max_proposals=value)


@pytest.mark.parametrize("configuration", [
    {"allowed_tokens": []},
    {"banned_tokens": ["a", "b"]},
    {"required_tokens": ["b"], "banned_tokens": ["b"]},
    {"required_tokens": ["b"], "allowed_tokens": ["a"]},
])
def test_impossible_grammar_never_restores_unmasked_logits(configuration):
    processor = GrammarBudgetLogitProcessor(("a", "b"), **configuration)
    with pytest.raises(ValueError, match="grammar"):
        processor.process([10.0, 20.0], [], steps_remaining=1)


def test_hard_masks_are_stronger_than_arbitrarily_negative_model_logits():
    processor = GrammarBudgetLogitProcessor(("a", "b"), banned_tokens=["b"])
    logits = processor.process([-1e100, 1.0], [], steps_remaining=1)
    assert logits[1] == -math.inf
    assert max(range(2), key=lambda token: logits[token]) == 0


def test_required_tokens_are_deduplicated_and_respect_the_remaining_budget():
    processor = GrammarBudgetLogitProcessor(("a", "b"), required_tokens=["a", "a"])
    logits = processor.process([0.0, 10.0], [], steps_remaining=1)
    assert max(range(2), key=lambda token: logits[token]) == 0
    impossible = GrammarBudgetLogitProcessor(("a", "b"), required_tokens=["a", "b"])
    with pytest.raises(ValueError, match="remaining budget"):
        impossible.process([0.0, 10.0], [], steps_remaining=1)


@pytest.mark.parametrize("logits", [[math.nan, 0.0], [math.inf, 0.0], [-math.inf, -math.inf], [0.0]])
def test_invalid_model_logits_cannot_be_published(logits):
    verifier = _Model(lambda context: 0)
    verifier._logits = lambda context: logits
    with pytest.raises(ValueError, match="logits|vocabulary|masks"):
        lookahead_jacobi_decode(verifier, [verifier], [0], 1)


@pytest.mark.parametrize("options", [
    {"lookahead_window": True}, {"lookahead_window": 9}, {"lookahead_window": 0},
    {"max_jacobi_iters": 1.5}, {"max_jacobi_iters": 7}, {"max_jacobi_iters": 0},
])
def test_lookahead_iteration_budgets_are_strict(options):
    verifier = _Model(lambda context: 0)
    with pytest.raises(ValueError):
        lookahead_jacobi_decode(verifier, [verifier], [0], 1, **options)


def test_real_transformer_constrained_sampling_preserves_hard_masks():
    from skeleton.cortex.transformer import TinyTransformer
    model = TinyTransformer(vocab=("alpha", "beta", "gamma"), dim=8, ctx=6,
                            n_heads=2, n_layers=1, d_ff=16, seed=19)
    result = model.constrained_generate(
        "beta gamma", 6, allowed_tokens=["alpha"], banned_tokens=["beta"],
        required_tokens=["alpha"], temperature=0.7,
    )
    assert result["tokens"] == ("alpha",) * 6
    assert result["all_required_satisfied"] is True
