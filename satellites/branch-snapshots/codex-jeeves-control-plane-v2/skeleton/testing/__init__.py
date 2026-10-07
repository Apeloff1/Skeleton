"""
Skeleton Testing Package

Exports:
- TestCase: Enhanced unittest with skeleton helpers
- TestScaffold: Genesis boot for tests
- TestOutcome: Structured test results
- TestRunner: Custom runner with JSON output
"""

from skeleton.testing.scaffold import TestCase, TestOutcome, TestRunner, TestScaffold

__all__ = [
    "TestCase",
    "TestScaffold",
    "TestOutcome",
    "TestRunner",
]
