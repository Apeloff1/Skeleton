"""Behavioral regressions for exact measured-backend runtime fingerprints."""

from __future__ import annotations

import math
import random
import types

import pytest

from skeleton.ai.runtime.inference import ReferenceNGramModel
from skeleton.ai.runtime.training.verifier import (
    MeasuredVerifierError,
    _runtime_identity,
)


def _first():
    return 1


def _second():
    return 999


_CHOICE = _first


class _Weights:
    def to_dict(self):
        return {"weights": [1]}


def test_existing_class_helper_override_changes_actual_infer_identity():
    class Model(_Weights):
        def infer(self):
            return "original"

        def alternate(self):
            return "alternate"

    model = Model()
    before = _runtime_identity(model)
    model.infer = types.MethodType(Model.alternate, model)
    assert model.infer() == "alternate"
    assert _runtime_identity(model) != before


def test_referenced_native_module_function_mutation_changes_identity(monkeypatch):
    class Model(_Weights):
        def infer(self):
            return math.floor(1.9)

    model = Model()
    before = _runtime_identity(model)
    with monkeypatch.context() as changes:
        changes.setattr(math, "floor", lambda _value: 999)
        after = _runtime_identity(model)
        output = model.infer()
    assert output == 999
    assert after != before


def test_property_getter_remains_bound_when_a_setter_also_exists():
    class Model(_Weights):
        @property
        def factor(self):
            return 1

        @factor.setter
        def factor(self, _value):
            pass

        def infer(self):
            return self.factor

    model = Model()
    before = _runtime_identity(model)
    original = Model.factor
    Model.factor = property(lambda _self: 999, original.fset)
    assert model.infer() == 999
    assert _runtime_identity(model) != before


def test_referenced_global_alias_is_bound_even_when_both_helpers_are_identified(monkeypatch):
    class Model(_Weights):
        def unused(self):
            return _first() + _second()

        def infer(self):
            return _CHOICE()

    model = Model()
    before = _runtime_identity(model)
    monkeypatch.setitem(globals(), "_CHOICE", _second)
    assert model.infer() == 999
    assert _runtime_identity(model) != before


def test_raw_python_code_bytes_are_bounded_before_digesting_them():
    class Model(_Weights):
        def infer(self):
            return 1

    code = Model.infer.__code__.replace(co_consts=(None, "x" * (300 * 1024)), co_name="oversized")
    Model.oversized = types.FunctionType(code, {})
    with pytest.raises(MeasuredVerifierError, match="code exceeds byte bound"):
        _runtime_identity(Model())


def test_reference_sampler_runtime_class_helper_is_bound(monkeypatch):
    model = ReferenceNGramModel.train(
        ("alpha beta", "alpha gamma", "alpha delta"), order=2, model_id="runtime-class-helper"
    )
    before = _runtime_identity(model)
    original_choice = model._choose(("alpha",), random.Random(1))
    with monkeypatch.context() as changes:
        changes.setattr(random.Random, "randrange", lambda _self, *_args: 2)
        changed_choice = model._choose(("alpha",), random.Random(1))
        after = _runtime_identity(model)
    assert original_choice != changed_choice
    assert after != before
