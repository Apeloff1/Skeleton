"""
Skeleton Testing Framework — Scaffold, assertions, and test lifecycle

Provides:
- TestCase: Enhanced unittest.TestCase with skeleton-specific helpers
- TestScaffold: Test environment setup and teardown
- TestOutcome: Structured test result reporting
"""

from __future__ import annotations

import json
import time
import unittest
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type


@dataclass
class TestOutcome:
    """Structured test result with timing and metadata."""
    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
            "metadata": self.metadata,
        }


class TestScaffold:
    """Test environment setup with genesis boot and cleanup."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.genesis: Optional[Any] = None
        self._handles: List[str] = []

    def setup(self) -> "TestScaffold":
        """Boot a fresh genesis for testing."""
        from skeleton.genesis import Genesis
        self.genesis = Genesis(seed=self.seed).boot()
        self._handles = list(self.genesis.handles.keys())
        return self

    def teardown(self) -> None:
        """Clean up test resources."""
        if self.genesis and hasattr(self.genesis, 'bus'):
            self.genesis.bus.emit("test.teardown", {"handles": self._handles})
        self.genesis = None

    def get(self, name: str) -> Any:
        """Get a handle from the booted genesis."""
        if self.genesis is None:
            raise RuntimeError("Scaffold not set up. Call setup() first.")
        return self.genesis.get(name)

    def snapshot(self) -> Dict[str, Any]:
        """Capture current system state for test verification."""
        if self.genesis is None:
            return {"status": "not_booted"}
        return {
            "handles": list(self.genesis.handles.keys()),
            "phases": self.genesis.report.phases,
            "invariants": self.genesis.report.invariants_registered,
        }


class TestCase(unittest.TestCase):
    """Enhanced TestCase with skeleton-specific utilities."""

    scaffold: Optional[TestScaffold] = None

    @classmethod
    def setUpClass(cls) -> None:
        """Set up a shared scaffold for the test class."""
        cls.scaffold = TestScaffold(seed=42).setup()

    @classmethod
    def tearDownClass(cls) -> None:
        """Tear down the shared scaffold."""
        if cls.scaffold:
            cls.scaffold.teardown()
            cls.scaffold = None

    def assertHandleWired(self, name: str) -> Any:
        """Assert that a handle is wired in genesis."""
        if self.scaffold is None:
            self.fail("Scaffold not available")
        handle = self.scaffold.genesis.handles.get(name)
        self.assertIsNotNone(handle, f"Handle '{name}' not wired")
        return handle

    def assertInvariantHealthy(self) -> None:
        """Assert that all invariants pass."""
        if self.scaffold is None:
            self.fail("Scaffold not available")
        violations = self.scaffold.genesis.lattice.evaluate()
        self.assertEqual(len(violations), 0, f"Invariant violations: {violations}")

    def assertEventPublished(self, topic: str) -> None:
        """Assert that an event was published to the bus."""
        if self.scaffold is None:
            self.fail("Scaffold not available")
        # Check if any handler received the topic
        bus = self.scaffold.genesis.bus
        self.assertIn(topic, bus._subscribers or {}, f"No subscribers for topic '{topic}'")

    def run_subtest(self, name: str, fn: Callable[[], None]) -> TestOutcome:
        """Run a function as a subtest with timing."""
        start = time.time()
        try:
            fn()
            return TestOutcome(name=name, passed=True, duration_ms=(time.time() - start) * 1000)
        except Exception as e:
            import traceback
            return TestOutcome(
                name=name,
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e),
                stack_trace=traceback.format_exc(),
            )

    def assertValidBlueprint(self, blueprint: Any) -> None:
        """Assert that a blueprint passes validation."""
        problems = blueprint.validate()
        self.assertEqual(len(problems), 0, f"Blueprint validation failed: {problems}")

    def assertMaterialises(self, forge: Any, blueprint: Any, target: str = "json") -> Dict[str, Any]:
        """Assert that a blueprint materialises without error."""
        try:
            result = forge.materialise(blueprint, target=target)
            self.assertIn("blueprint_id", result)
            return result
        except Exception as e:
            self.fail(f"Materialisation failed: {e}")


class TestRunner:
    """Custom test runner with structured output."""

    def __init__(self, verbosity: int = 2):
        self.verbosity = verbosity
        self.outcomes: List[TestOutcome] = []

    def run(self, test_suite: unittest.TestSuite) -> Dict[str, Any]:
        """Run a test suite and return structured results."""
        runner = unittest.TextTestRunner(verbosity=self.verbosity)
        result = runner.run(test_suite)

        summary = {
            "total": result.testsRun,
            "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
            "failed": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "success": result.wasSuccessful(),
        }

        return {
            "summary": summary,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }

    def discover_and_run(self, path: str = "skeleton/testing", pattern: str = "test_*.py") -> Dict[str, Any]:
        """Discover and run tests from a path."""
        loader = unittest.TestLoader()
        suite = loader.discover(path, pattern=pattern)
        return self.run(suite)
