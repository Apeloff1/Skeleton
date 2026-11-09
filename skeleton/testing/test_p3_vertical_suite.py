from __future__ import annotations
import unittest


class P3VerticalSuiteInventoryTests(unittest.TestCase):
    def test_six_vertical_test_modules_are_importable(self):
        # Explicit literal imports keep the repository dynamic-import gate satisfied.
        from skeleton.testing import test_vs002_engineering_agent
        from skeleton.testing import test_vs003_scientific_researcher
        from skeleton.testing import test_vs004_multi_agent_engineering
        from skeleton.testing import test_vs005_self_improvement
        from skeleton.testing import test_vs006_distributed_execution
        from skeleton.testing import test_vs007_desktop_product

        modules = (
            test_vs002_engineering_agent,
            test_vs003_scientific_researcher,
            test_vs004_multi_agent_engineering,
            test_vs005_self_improvement,
            test_vs006_distributed_execution,
            test_vs007_desktop_product,
        )
        self.assertEqual(len(modules), 6)
        for module in modules:
            self.assertTrue(module.__name__.startswith("skeleton.testing.test_vs00"))


if __name__ == "__main__":
    unittest.main()
