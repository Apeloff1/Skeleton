"""The offline product compatibility API must be one canonical dispatcher."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.production_fabric.product.api import LocalAPI as CompatibilityAPI
from skeleton.ai.runtime.production_fabric.product.dispatcher import LocalAPI as CanonicalAPI
from skeleton.ai.runtime.production_fabric.product.cli import LocalAPI as CLIAPI


class SingleOfflineDispatcherTests(unittest.TestCase):
    def test_identity_is_shared_not_a_second_implementation(self):
        self.assertIs(CompatibilityAPI, CanonicalAPI)
        self.assertIs(CLIAPI, CanonicalAPI)

    def test_dispatch_authority_is_owned_by_local_product_dispatcher(self):
        self.assertEqual(CanonicalAPI.__module__,
                         "skeleton.ai.runtime.production_fabric.product.dispatcher")


if __name__ == "__main__":
    unittest.main()
