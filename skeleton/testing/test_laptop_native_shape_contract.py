"""Finite native request admission before any private I/O or GGUF process.

The simulated tests cannot prove a real installed model, device, Windows,
WSL2, source-rights approval or release readiness.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.preflight import validate_native_shape
from skeleton.ai.runtime.operational_ai.laptop_runtime.cli import main as laptop_main
from skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli import main as client_main
from skeleton.ai.runtime.operational_ai.laptop_runtime.cli_doctor import main as doctor_main

class TestCanonicalNativeShape(unittest.TestCase):
    def test_cpu_first_laptop_defaults_are_structural_only(self):
        self.assertIsNone(validate_native_shape(
            n_ctx=4096,max_new_tokens=1024,n_threads=4,gpu_layers=0,
            capacity_budget_bytes=8000000000,
        ))
        self.assertIsNone(validate_native_shape(
            n_ctx=128,max_new_tokens=1,n_threads=1,gpu_layers=0,
            capacity_budget_bytes=1,capacity_slots=1,inference_ms=100,
        ))

    def test_upper_shape_boundaries_are_typed(self):
        self.assertIsNone(validate_native_shape(
            n_ctx=131072,max_new_tokens=8192,n_threads=64,gpu_layers=128,
            capacity_budget_bytes=20000000000,
            capacity_slots=64,inference_ms=600000,
        ))

    def test_invalid_context_and_output_never_pass(self):
        for key,bad in (
            ("n_ctx",(None,True,0,1,127,131073,"4096",1.5)),
            ("max_new_tokens",(None,True,0,-1,8193,"128",2.5)),
        ):
            for value in bad:
                with self.subTest(key=key,value=value):
                    values=dict(n_ctx=4096,max_new_tokens=1024,
                                n_threads=4,gpu_layers=0,capacity_budget_bytes=8000000000)
                    values[key]=value
                    with self.assertRaises(ContractViolation):
                        validate_native_shape(**values)

    def test_output_must_not_equal_or_exceed_context(self):
        for context,output in ((128,128),(2048,2048),(4096,8192)):
            with self.subTest(context=context,output=output):
                with self.assertRaises(ContractViolation):
                    validate_native_shape(
                        n_ctx=context,max_new_tokens=output,
                        n_threads=4,gpu_layers=0,capacity_budget_bytes=1024,
                    )

    def test_invalid_threads_gpu_slots_time_and_capacity_held(self):
        for name,bad in (
            ("n_threads",(None,True,0,-1,65,"4")),
            ("gpu_layers",(None,True,-1,129,"0")),
            ("capacity_slots",(None,True,0,-1,65,"1")),
            ("inference_ms",(None,True,0,-1,1,99,600001,"90")),
            ("capacity_budget_bytes",(None,True,0,-1,20000000001,"8000000000")),
        ):
            for value in bad:
                with self.subTest(name=name,value=value):
                    args=dict(n_ctx=4096,max_new_tokens=1024,
                        n_threads=4,gpu_layers=0,capacity_budget_bytes=8000000000)
                    args[name]=value
                    with self.assertRaises(ContractViolation):
                        validate_native_shape(**args)

if __name__=="__main__":
    unittest.main()
