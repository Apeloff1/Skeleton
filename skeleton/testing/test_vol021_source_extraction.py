import hashlib,pytest
from skeleton.repo_intelligence.source_extraction import MAX_SOURCE_BYTES,SourceFile,build_repository_graph
from skeleton.repo_intelligence.repository_graph import RepositoryGraphError
def s(path,content):return SourceFile(path,content,hashlib.sha256(content.encode()).hexdigest())
def test_python_and_typescript_relative_edges():
 g=build_repository_graph((s("pkg/a.py","import pkg.b"),s("pkg/b.py",""),s("web/a.ts","import x from './b'"),s("web/b.ts","")))
 assert ("pkg/a.py","pkg/b.py","import") in g.edges and ("web/a.ts","web/b.ts","import") in g.edges
def test_java_rust_go_extractors_are_conservative():
 g=build_repository_graph((s("com/x/A.java","import com.x.B;"),s("com/x/B.java",""),s("crate/main.rs","use crate::util;"),s("crate/util.rs",""),s("app/main.go",'import "lib/util"'),s("lib/util.go","")))
 assert ("com/x/A.java","com/x/B.java","import") in g.edges
 assert ("lib/util.go" in g.nodes)
def test_external_and_ambiguous_imports_are_not_guessed():
 g=build_repository_graph((s("a.py","import requests"),s("b.py","")))
 assert g.edges==()
def test_invalid_python_fails_closed():
 with pytest.raises(RepositoryGraphError):build_repository_graph((s("a.py","def broken("),))
def test_source_budget_is_hard():
 with pytest.raises(RepositoryGraphError):build_repository_graph((s("a.py","x"*(MAX_SOURCE_BYTES+1)),))
def test_graph_is_deterministic_under_source_order():
 xs=(s("a.py","import b"),s("b.py",""))
 assert build_repository_graph(xs).digest==build_repository_graph(tuple(reversed(xs))).digest

def test_source_identity_is_bound_to_content_and_safe_path():
 with pytest.raises(RepositoryGraphError,match="digest mismatch"):SourceFile("a.py","x","0"*64)
 with pytest.raises(RepositoryGraphError,match="invalid source path"):s("../a.py","x")
 with pytest.raises(RepositoryGraphError,match="invalid source path"):s("/a.py","x")
def test_source_metadata_is_bounded_and_deterministic():
 x=SourceFile("a.py","",hashlib.sha256(b"").hexdigest(),"core",("z.py","a.py","z.py"))
 assert x.tests==("a.py","z.py")
 with pytest.raises(RepositoryGraphError,match="source tests"):SourceFile("a.py","",hashlib.sha256(b"").hexdigest(),tests=("",))

def test_relative_resolution_normalizes_module_paths():
 g=build_repository_graph((s("pkg/sub/a.py","from .. import b"),s("pkg/b.py",""),s("web/sub/a.ts","import x from '../b'"),s("web/b.ts","")))
 assert ("pkg/sub/a.py","pkg/b.py","import") in g.edges
 assert ("web/sub/a.ts","web/b.ts","import") in g.edges
