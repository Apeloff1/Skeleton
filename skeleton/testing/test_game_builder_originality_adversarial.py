"""Adversarial bounded originality screening: correctness, repeated tokens, Unicode.

Synthetic content only. Similarity is an investigation signal, never a claim
that a machine can decide whether independently authored ideas infringe law.
"""
from __future__ import annotations

import random

import pytest

from skeleton.ai.game_builder.plagiarism_guard import (
    ExpressionSample, OriginalityError,
    _longest_overlap, _tokens, find_expression_overlap,
)


def _oracle(left, right):
    best = 0
    for i in range(len(left)):
        for j in range(len(right)):
            run = 0
            while i+run < len(left) and j+run < len(right) and left[i+run] == right[j+run]:
                run += 1
            best = max(best,run)
    return best


@pytest.mark.parametrize("seed",range(50))
def test_suffix_automaton_matches_exact_quadratic_oracle_under_word_collisions(seed):
    random_state=random.Random(seed)
    alphabet=("rose","rose","thirteen","moth","astronaut","lighthouse","copper")
    for _ in range(18):
        left=tuple(random_state.choice(alphabet) for _ in range(random_state.randrange(19)))
        right=tuple(random_state.choice(alphabet) for _ in range(random_state.randrange(19)))
        assert _longest_overlap(left,right)==_oracle(left,right)


@pytest.mark.parametrize("size", [64,256,1024,4096,12000,16000])
def test_adversarial_repeated_word_runs_are_detected_without_quadratic_work(size):
    repeated=("violet",)*size
    assert _longest_overlap(repeated,repeated)==size
    assert _longest_overlap(repeated,("different",)*size)==0
    assert _longest_overlap(("different",)+repeated,("other",)+repeated)==size


@pytest.mark.parametrize("prefix", [1,2,8,32,64,100])
def test_distinctive_common_run_after_many_repeated_shingles_is_never_skipped(prefix):
    # Previous implementation deliberately ignored offsets beyond 32.
    # Every repeated phrase and actual last unique run must now be compared.
    left=("a",)*prefix + tuple("unique"+str(i) for i in range(40))
    right=("a",)*(prefix+32) + tuple("unique"+str(i) for i in range(40))
    assert _longest_overlap(left,right)==len(left)


def test_copying_exactly_six_narrative_tokens_is_flagged_for_human_review():
    phrase="amber moth catalogues violet clocks carefully"
    sample=ExpressionSample("own","story_dialogue",phrase)
    reference=ExpressionSample("prior","story_dialogue",phrase)
    finding=find_expression_overlap(sample,reference)
    assert finding is not None
    assert finding.triage_signal=="SHORT_IDENTICAL_NARRATIVE_FOR_REVIEW"
    assert finding.legal_infringement_determined is False


def test_generic_six_token_programming_convention_is_not_automatically_illegal():
    code="for index in objects render index"
    item=ExpressionSample("own","source_code",code)
    ref=ExpressionSample("ref","source_code",code)
    assert find_expression_overlap(item,ref) is None


@pytest.mark.parametrize("render",[
    "A B C D E F G H",
    "ａ ｂ ｃ ｄ ｅ ｆ ｇ ｈ",
    "a b c d e f g h",
])
def test_unicode_width_case_and_normalization_are_stable_in_text_triage(render):
    left=ExpressionSample("mine","story_dialogue",render)
    reference=ExpressionSample("prior","story_dialogue","a b c d e f g h")
    assert find_expression_overlap(left,reference) is not None


def test_source_text_above_token_limit_is_rejected_not_silently_truncated():
    excessive=" ".join("word"+str(i) for i in range(16001))
    with pytest.raises(OriginalityError):
        _tokens(excessive)


def test_short_unrelated_references_never_invent_infringement():
    assert _longest_overlap((),("rose",))==0
    assert _longest_overlap(("rose",),())==0
    assert _longest_overlap((),())==0


def test_longest_overlap_stays_within_actual_input_lengths():
    a=tuple("v"+str(i%7) for i in range(100))
    b=tuple("v"+str(i%7) for i in range(150))
    result=_longest_overlap(a,b)
    assert 0<=result<=min(len(a),len(b))
