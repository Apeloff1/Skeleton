import pytest
from skeleton.retrieval.vector_index_migration import *
def idx(v,space="e1"):return VectorIndexVersion("docs",v,space)
def test_shadow_does_not_route_before_atomic_promotion():
 m=IndexMigration(idx("v1"),idx("v2"),IndexValidation(.99,.99,True));assert m.route().version=="v1" and m.promote(.9,.9).route().version=="v2"
def test_quality_and_embedding_space_gate_promotion():
 with pytest.raises(PermissionError):IndexMigration(idx("v1"),idx("v2"),IndexValidation(.1,1,True)).promote(.9,.9)
 with pytest.raises(ValueError):IndexMigration(idx("v1"),idx("v2","e2"),IndexValidation(1,1,True)).promote(.9,.9)
def test_rollback_restores_active_route():
 m=IndexMigration(idx("v1"),idx("v2"),IndexValidation(1,1,True)).promote(.9,.9);assert m.rollback().route().version=="v1"
