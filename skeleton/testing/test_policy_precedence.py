from skeleton.security.policy_precedence import PolicyConflictError, PolicyRule, resolve_policy, verify_replay

def r(rule_id, layer, effect, action="tool.write"):
    return PolicyRule(rule_id=rule_id, layer=layer, effect=effect, action=action)

def test_higher_authority_wins_independent_of_input_order():
    rules=(r("tenant-allow","tenant","allow"),r("system-deny","system","deny"))
    assert resolve_policy("tool.write",rules).effect=="deny"
    assert resolve_policy("tool.write",tuple(reversed(rules)))==resolve_policy("tool.write",rules)

def test_invariant_is_unoverrideable():
    d=resolve_policy("tool.write",(r("system-allow","system","allow"),r("inv-deny","invariant","deny")))
    assert (d.effect,d.authority_layer)==("deny","invariant")

def test_equal_authority_conflict_fails_closed():
    try:
        resolve_policy("tool.write",(r("a","system","allow"),r("b","system","deny")))
    except PolicyConflictError:
        return
    raise AssertionError("conflict did not fail closed")

def test_missing_authority_fails_closed():
    try:
        resolve_policy("tool.write",())
    except PolicyConflictError:
        return
    raise AssertionError("missing authority did not fail closed")

def test_replay_is_bound_to_policy_content():
    rules=(r("a","system","allow"),)
    d=resolve_policy("tool.write",rules)
    assert verify_replay(d,rules)
    assert not verify_replay(d,(r("a","system","allow"),r("tenant","tenant","deny")))
