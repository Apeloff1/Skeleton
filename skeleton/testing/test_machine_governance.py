import pytest
from skeleton.ai.runtime.deferred.machine_governance import *
D="a"*64; B="b"*64
def test_codeowners_generation_is_deterministic():
 a=CodeownersManifest((CodeownersRule("z/*",(ReviewOwner("@z"),)),CodeownersRule("a/*",(ReviewOwner("@b"),ReviewOwner("@a")))),())
 b=CodeownersManifest(tuple(reversed(a.rules)),())
 assert a.render()==b.render() and a.digest==b.digest
def test_codeowners_rule_cannot_be_ownerless():
 with pytest.raises(ValueError): CodeownersRule("src/*",())
def test_normative_docs_require_authority_source():
 with pytest.raises(ValueError,match="authority"): DocumentationRule(True,None)
def test_doc_reference_detects_missing_and_drifted_target():
 r=DocReference("doc.md","machine/x.json",D)
 assert not DocCheck(r,False,None).valid
 assert not DocCheck(r,True,B).valid
 assert DocCheck(r,True,D).valid
def test_diagram_cannot_silently_override_machine_topology():
 s=DiagramSpec("d",DiagramSource("architecture","v1",D),"mermaid")
 assert not DiagramArtifact(s,B,B).current
 assert DiagramArtifact(s,B,D).current
def test_snapshot_digest_binds_manifest_graph_and_release():
 a=ArchitectureSnapshot("s",D,D,"r1"); b=ArchitectureSnapshot("s",D,B,"r1")
 assert a.digest!=b.digest and diff_architecture(a,b).dependency_graph_changed
def test_snapshot_diff_separates_manifest_and_dependency_changes():
 a=ArchitectureSnapshot("a",D,D,"r1"); b=ArchitectureSnapshot("b",B,D,"r2")
 x=diff_architecture(a,b); assert x.manifest_changed and not x.dependency_graph_changed
def test_reproducible_build_requires_identical_source_env_toolchain_artifact():
 a=ReproBuild("a",D,D,D,D); b=ReproBuild("b",D,D,D,D)
 assert compare_builds(a,b).reproducible
def test_build_variance_names_unexplained_input_or_output_difference():
 a=ReproBuild("a",D,D,D,D); b=ReproBuild("b",D,B,D,B)
 c=compare_builds(a,b)
 assert not c.reproducible and {v.field for v in c.variances}=={"environment_digest","artifact_digest"}
