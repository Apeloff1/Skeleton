import pytest
from skeleton.repo_intelligence.repository_graph import DependencyEdge,FileNode,RepositoryGraph,RepositoryGraphError
from skeleton.repo_intelligence.change_planner import ChangePlan,plan_change
D="0"*64
def graph():
 nodes=(FileNode("src/a.py","python",D,"core",("tests/test_a.py",)),FileNode("src/b.ts","typescript",D,"ui",("tests/test_b.py",)),FileNode("tests/test_a.py","python",D,"qa"),FileNode("tests/test_b.py","python",D,"qa"))
 edges=(DependencyEdge("src/b.ts","src/a.py","import"),DependencyEdge("tests/test_a.py","src/a.py","test"),DependencyEdge("tests/test_b.py","src/b.ts","test"))
 return RepositoryGraph(nodes,edges)
def test_transitive_impact_drives_tests_and_owners():
 p=plan_change(graph(),("src/a.py",))
 assert p.impacted_paths==("src/a.py","src/b.ts","tests/test_a.py","tests/test_b.py")
 assert p.required_tests==("tests/test_a.py","tests/test_b.py") and set(p.owners)=={"core","qa","ui"}
def test_graph_identity_is_order_independent():
 g=graph(); h=RepositoryGraph(tuple(reversed(tuple(g.nodes.values()))),tuple(DependencyEdge(*e) for e in reversed(g.edges)))
 assert g.digest==h.digest
def test_dangling_and_self_edges_fail_closed():
 n=(FileNode("a.py","python",D),)
 with pytest.raises(RepositoryGraphError):RepositoryGraph(n,(DependencyEdge("a.py","missing.py","import"),))
 with pytest.raises(RepositoryGraphError):DependencyEdge("a.py","a.py","import")
def test_unknown_change_is_rejected():
 with pytest.raises(RepositoryGraphError):plan_change(graph(),("missing.py",))
def test_plan_cannot_escalate_authority():
 p=plan_change(graph(),("src/a.py",))
 with pytest.raises(RepositoryGraphError):ChangePlan(p.graph_digest,p.changed_paths,p.impacted_paths,p.required_tests,p.owners,"mutation")

def test_change_plan_evidence_cannot_be_forged_or_noncanonical():
 p=plan_change(graph(),("src/a.py",))
 with pytest.raises(RepositoryGraphError,match="invalid graph digest"):ChangePlan("forged",p.changed_paths,p.impacted_paths,p.required_tests,p.owners)
 with pytest.raises(RepositoryGraphError,match="changed paths must be impacted"):ChangePlan(p.graph_digest,("src/a.py",),("src/b.ts",),p.required_tests,p.owners)
 with pytest.raises(RepositoryGraphError,match="must be canonical"):ChangePlan(p.graph_digest,("src/a.py","src/a.py"),p.impacted_paths,p.required_tests,p.owners)

def test_graph_metadata_and_edge_paths_fail_closed():
 with pytest.raises(RepositoryGraphError,match="tests must be safe"):FileNode("a.py","python",D,tests=("../escape.py",))
 with pytest.raises(RepositoryGraphError,match="invalid edge path"):DependencyEdge("../a.py","b.py","import")
 with pytest.raises(RepositoryGraphError,match="nodes and edges must be tuples"):RepositoryGraph([],())
 with pytest.raises(RepositoryGraphError,match="typed nodes and edges required"):RepositoryGraph(("not-a-node",),())
