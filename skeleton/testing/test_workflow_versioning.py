import pytest
from skeleton.ai.workflow_versioning import *
V=lambda a,b=0,c=0:WorkflowVersion(a,b,c)
def test_inflight_operation_remains_pinned_by_default():
 b=WorkflowBinding("op","wf",V(1));assert b.resolve(V(1,1)).pinned_version==V(1)
def test_compatible_update_requires_explicit_approval():
 b=WorkflowBinding("op","wf",V(1));assert b.resolve(V(1,1),True).pinned_version==V(1,1)
def test_major_change_cannot_use_implicit_approval():
 b=WorkflowBinding("op","wf",V(1))
 with pytest.raises(ValueError):b.resolve(V(2),True)
def test_major_migration_requires_bound_evidence():
 b=WorkflowBinding("op","wf",V(1));m=WorkflowMigration("op",V(1),V(2),"evidence:1")
 assert m.apply(b).pinned_version==V(2)
 with pytest.raises(ValueError):WorkflowMigration("op",V(1),V(2),"").apply(b)
def test_invalid_versions_fail_closed():
 with pytest.raises(ValueError):V(-1)
 with pytest.raises(ValueError):WorkflowVersion(True,0,0)
