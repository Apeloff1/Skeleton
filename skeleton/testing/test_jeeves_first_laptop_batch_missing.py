"""Missing stage/domain and extra stage/domain source claims must fail closed."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.batch.catalog import manifest
from skeleton.jeeves.native_fabric.laptop_ops.batch.fixtures import (
    successful_bundle, negative_bundle, encode_bundle,
)
from skeleton.jeeves.native_fabric.laptop_ops.batch.runner import (
    evaluate_bundle, evaluate_json,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import list_domains

import importlib

class TestIncompleteBundleSafety(unittest.TestCase):
    def test_one_of_twenty_missing_domains_is_rejected(self):
        for domain in list_domains():
            with self.subTest(domain=domain):
                evidence = successful_bundle()
                del evidence[domain]
                with self.assertRaises(LaptopGateHold):
                    evaluate_bundle(evidence)

    def test_one_of_160_missing_stage_names_is_rejected(self):
        total = 0
        for domain in list_domains():
            module = importlib.import_module(
                "skeleton.jeeves.native_fabric.laptop_ops.domains."
                + domain + ".registry"
            )
            for stage in module.STAGES:
                with self.subTest(domain=domain, stage=stage):
                    sample = successful_bundle()
                    del sample[domain][stage]
                    with self.assertRaises(LaptopGateHold):
                        evaluate_bundle(sample)
                    total += 1
        self.assertEqual(total, 160)

    def test_extra_domain_and_extra_nested_stage_are_rejected(self):
        original = successful_bundle()
        with self.assertRaises(LaptopGateHold):
            evaluate_bundle({**original, "extra_native_authority": {}})
        for domain in list_domains():
            with self.subTest(domain=domain):
                sample = successful_bundle()
                sample[domain]["user_override"] = {"verified": True}
                with self.assertRaises(LaptopGateHold):
                    evaluate_bundle(sample)

    def test_bool_and_list_cannot_be_domain_mappings(self):
        for candidate in (None, True, 0, [], (), ""):
            with self.assertRaises(LaptopGateHold):
                evaluate_bundle(candidate)
        for domain in list_domains():
            with self.subTest(domain=domain):
                sample = successful_bundle()
                sample[domain] = True
                with self.assertRaises(LaptopGateHold):
                    evaluate_bundle(sample)
