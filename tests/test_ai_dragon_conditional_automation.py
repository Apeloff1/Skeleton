"""Dragon conditional research admission rejects unknown and vetoed facts."""
from dataclasses import replace
import pytest
from skeleton.ai.webcrawler.dragon_conditional_automation import (
    ConditionalRule, SHADOW_RULE, PROMOTION_RULE, VETOES,
    evaluate_trigger,
)


def good(rule):
    facts = {
        **{key: False for key in rule.but_none},
        **{key: True for key in rule.and_all},
    }
    facts[rule.if_any[0]] = True
    if rule.or_any:
        facts[rule.or_any[0]] = True
    return facts


def test_complete_shadow_admission_is_deterministic_and_no_veto():
    sample = good(SHADOW_RULE)
    decision = evaluate_trigger(SHADOW_RULE, sample)
    assert decision.admitted
    assert not decision.reasons
    assert len(decision.trace_digest) == 64
    assert decision == evaluate_trigger(SHADOW_RULE, dict(reversed(list(sample.items()))))
    assert not evaluate_trigger(PROMOTION_RULE, sample).admitted
    assert "and_missing:human_approved" in evaluate_trigger(PROMOTION_RULE, sample).reasons


def test_all_high_priority_vetoes_block_even_perfect_sources():
    sample = good(PROMOTION_RULE)
    assert evaluate_trigger(PROMOTION_RULE, sample).admitted
    for veto in PROMOTION_RULE.but_none:
        assert not evaluate_trigger(PROMOTION_RULE, {**sample, veto: True}).admitted
        unknown = evaluate_trigger(PROMOTION_RULE, {**sample, veto: None})
        assert not unknown.admitted
        assert "but_veto_or_unknown:" + veto in unknown.reasons
        assert unknown.trace_digest != evaluate_trigger(PROMOTION_RULE, sample).trace_digest


def test_missing_consent_or_independent_evidence_is_never_inferred():
    original = good(SHADOW_RULE)
    for required in ("consented", "owner_authorized", "independent_groups",
                     "reviewed", "rights_checked", "resource_admitted", "idle"):
        partial = dict(original)
        partial.pop(required)
        result = evaluate_trigger(SHADOW_RULE, partial)
        assert not result.admitted
        assert "and_missing:" + required in result.reasons


def test_rule_validation_rejects_crosslisted_vetoes_and_untyped_inputs():
    with pytest.raises(ValueError):
        ConditionalRule(("reviewed",), ("reviewed",), but_none=("reviewed",))
    with pytest.raises(ValueError):
        ConditionalRule(("unsupported_rule",), ("reviewed",))
    with pytest.raises(ValueError):
        ConditionalRule(("reviewed", "reviewed"), ("reviewed",))
    with pytest.raises(ValueError):
        ConditionalRule(("reviewed",), ())
    with pytest.raises(ValueError):
        evaluate_trigger(SHADOW_RULE, {"reviewed": 1})
    with pytest.raises(ValueError):
        evaluate_trigger(SHADOW_RULE, {"made_up": True})
    with pytest.raises(ValueError):
        evaluate_trigger(SHADOW_RULE, [])
