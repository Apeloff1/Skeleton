from skeleton.ai.contract_codegen import *
def test_clean_regeneration_is_stable():
 s=GenerationSpec("v1","python",("b","a"),(ExtensionPoint("manual_adapter"),));assert generate_code(s)==generate_code(s)
def test_generated_marker_and_extension_point_are_preserved():
 g=generate_code(GenerationSpec("v1","python",(),(ExtensionPoint("custom"),)));assert g.generated and "GENERATED" in g.content and "custom" in g.content

def test_generated_identifiers_reject_injection():
 import pytest
 with pytest.raises(ValueError):generate_code(GenerationSpec("v1","python-model",("x\npass",)))
def test_unknown_target_rejected():
 import pytest
 with pytest.raises(ValueError):generate_code(GenerationSpec("v1","shell",("x",)))
