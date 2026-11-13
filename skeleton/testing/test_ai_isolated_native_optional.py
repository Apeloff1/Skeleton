"""Real checkpoint acceptance test (SKIP is unqualified, never passed).

Run only with SKELETON_TEST_APPROVED_GGUF_ROOT set to a real, independently
approved manifest + shards. This test never downloads or fabricates weights.
"""
from __future__ import annotations
import os
from pathlib import Path
import unittest

from skeleton.ai.runtime.operational_ai.model.gguf.service import load_approved_manifest
from skeleton.ai.runtime.operational_ai.model.isolation.client import IsolatedGGUFBackend


class RealIsolatedNativeQualification(unittest.TestCase):
    def test_real_approved_model_in_isolated_worker(self):
        location=os.environ.get('SKELETON_TEST_APPROVED_GGUF_ROOT')
        if not location:
            self.skipTest('real approved GGUF not provided: full native acceptance unverified')
        root=Path(location)
        manifest=load_approved_manifest(root)
        with IsolatedGGUFBackend(root.absolute(),manifest,n_ctx=min(2048,manifest.context_ceiling),
                                 n_threads=2,inference_ms=120000) as model:
            status=model.probe()
            self.assertEqual(status['model_sha256'],manifest.model_sha256)
            output=model.generate([{'role':'user','content':
                'Describe your offline operation in one sentence.'}],
                max_output_tokens=64,seed=203,temperature=.5)
            self.assertEqual(output.model_digest,manifest.model_sha256)
            self.assertGreaterEqual(output.generated_tokens,0)
            self.assertTrue(output.text.strip())
        # This verifies the real checkpoint's basic operation, not quality,
        # representative workload, restart, or device performance qualification.


if __name__=='__main__':unittest.main()
