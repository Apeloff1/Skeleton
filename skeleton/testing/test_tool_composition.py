from skeleton.ai.tool_composition import *
def b(n,p,i="x",o="x",t="verified"):return ToolBinding(n,frozenset(p),i,o,t)
def test_composition_cannot_aggregate_new_authority():assert not validate(ToolComposition((b("a",("read",)),b("b",("write",))),frozenset(("read",)))).valid
def test_schema_and_trust_boundary_checked():assert not validate(ToolComposition((b("a",(),"x","y"),b("b",(),"x","x")),frozenset())).valid

def test_union_of_tool_permissions_cannot_amplify_composition():
 a=ToolBinding("a",frozenset({"read"}),"x","y","t");b=ToolBinding("b",frozenset({"write"}),"y","z","t")
 assert not validate(ToolComposition((a,b),frozenset({"read","write"}))).valid

def test_duplicate_tool_binding_rejected():
 b=ToolBinding("t",frozenset({"r"}),"x","x","trusted")
 assert not validate(ToolComposition((b,b),frozenset({"r"}))).valid
