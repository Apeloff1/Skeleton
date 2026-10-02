from __future__ import annotations
import unittest

class P3VerticalSuiteInventoryTests(unittest.TestCase):
    def test_six_vertical_test_modules_are_importable(self):
        modules=(
            "skeleton.testing.test_vs002_engineering_agent",
            "skeleton.testing.test_vs003_scientific_researcher",
            "skeleton.testing.test_vs004_multi_agent_engineering",
            "skeleton.testing.test_vs005_self_improvement",
            "skeleton.testing.test_vs006_distributed_execution",
            "skeleton.testing.test_vs007_desktop_product",
        )
        for name in modules:
            __import__(name)

if __name__=="__main__": unittest.main()
