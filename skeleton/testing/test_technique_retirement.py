import pytest
from skeleton.ai.technique_retirement import *
def test_consumer_blocks_retirement_until_migrated():
 with pytest.raises(PermissionError):retire(Technique("t","v1",("c",)),RetirementEvidence("old","new","archive",frozenset()))
def test_history_archive_is_preserved():assert retire(Technique("t","v1",()),RetirementEvidence("old","new","archive",frozenset())).evidence.archive=="archive"

def test_self_replacement_rejected():
 import pytest
 with pytest.raises(ValueError):retire(Technique("t","1",()),RetirementEvidence("r","t","a",frozenset()))
