from __future__ import annotations
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/check_masterplan_overlay_semantics.py"

def _module():
    spec=importlib.util.spec_from_file_location("overlay_semantics",SCRIPT)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_current_overlay_semantics_are_exact():
    assert _module().validate()==[]

def test_semantic_length_mismatch_is_rejected():
    m=_module()
    errors=m._semantic_errors("x",{"levels":[1]},[{"path":"levels","kind":"length","expected":2}])
    assert errors and "length 1 != 2" in errors[0]

def test_semantic_value_mismatch_is_rejected():
    m=_module()
    errors=m._semantic_errors("x",{"topology":{"total_levels":4}},[{"path":"topology.total_levels","kind":"equals","expected":5}])
    assert errors and "!= 5" in errors[0]

def test_missing_semantic_path_is_rejected():
    m=_module()
    errors=m._semantic_errors("x",{},[{"path":"levels","kind":"length","expected":1}])
    assert errors and "missing semantic path" in errors[0]
