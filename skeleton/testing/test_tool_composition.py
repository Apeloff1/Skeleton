from skeleton.ai.tool_composition import *
def b(n,p,i="x",o="x",t="verified"):return ToolBinding(n,frozenset(p),i,o,t)
def test_composition_cannot_aggregate_new_authority():assert not validate(ToolComposition((b("a",("read",)),b("b",("write",))),frozenset(("read",)))).valid
def test_schema_and_trust_boundary_checked():assert not validate(ToolComposition((b("a",(),"x","y"),b("b",(),"x","x")),frozenset())).valid
