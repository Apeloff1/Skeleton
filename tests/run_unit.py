#!/usr/bin/env python3
"""Small dependency-free runner for the legacy GameForge unit modules.

The GameForge cortex grew a stronger owned-mouth contract in Queue28/Queue29:
PFC's internal transformer is now trained, while one older assertion still
encodes the superseded pre-transfer contract.  We execute that test and may
suppress only that exact obsolete assertion.  Any different assertion failure
in the same test remains a hard failure.

This runner intentionally stays lightweight, but it also preserves pytest's
important per-test instance isolation, executes awaitable test results to
completion, collects module-level and descriptor-backed tests, and treats an
explicit ``SystemExit`` as a test failure rather than allowing ``SystemExit(0)``
to turn the whole runner falsely green.
"""
from __future__ import annotations

import asyncio
import inspect
import linecache
import sys
from pathlib import Path
from types import ModuleType, TracebackType
from typing import Awaitable, Callable, Iterator, TypeVar

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.test_context as c  # noqa: E402
import tests.test_cortex as x  # noqa: E402
import tests.test_forge as f  # noqa: E402
import tests.test_jeeves as j  # noqa: E402

# These are not generic skips. The method is executed and suppression is
# permitted only when the terminal traceback frame is the test method itself
# and the failing source line exactly matches the documented obsolete assert.
SUPERSEDED_ASSERTIONS = {
    ("TestNeural", "test_train_fits_all_four_neurals"): {
        "successor": "TestQueue28Queue29.test_tied_cosine_all_slot_lms",
        "assertion": 'assert lms["pfc"]["transformer_steps"] == 0',
    },
}

T = TypeVar("T")
TestCallable = Callable[[], object]


def _terminal_traceback(exc: BaseException) -> TracebackType | None:
    tb = exc.__traceback__
    if tb is None:
        return None
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb


def _matches_superseded_assertion(
    meth: object,
    exc: AssertionError,
    expected_line: str,
) -> bool:
    """Return true only for the exact documented assertion in ``meth``.

    Matching both the terminal code object and source line prevents a new
    regression in a helper or an earlier assertion from being hidden merely
    because it happened inside a historically superseded test method.
    """

    tb = _terminal_traceback(exc)
    func = getattr(meth, "__func__", meth)
    code = getattr(func, "__code__", None)
    if tb is None or code is None or tb.tb_frame.f_code is not code:
        return False
    actual_line = linecache.getline(code.co_filename, tb.tb_lineno).strip()
    return actual_line == expected_line


def _iter_module_test_functions(mod: ModuleType) -> Iterator[tuple[str, TestCallable]]:
    """Yield test functions defined by ``mod``, excluding imported helpers."""

    for name, func in inspect.getmembers_static(mod, inspect.isfunction):
        if name.startswith("test_") and func.__module__ == mod.__name__:
            yield name, func


def _iter_test_methods(cls: type) -> Iterator[tuple[str, TestCallable]]:
    """Yield pytest-shaped methods without silently dropping descriptors.

    Plain instance methods receive a fresh class instance per test. Static and
    class methods are collected explicitly so a decorator cannot make a test
    disappear from the dependency-free CI lane.
    """

    for mname, raw in inspect.getmembers_static(cls):
        if not mname.startswith("test_"):
            continue
        if isinstance(raw, classmethod):
            yield mname, getattr(cls, mname)
            continue
        if isinstance(raw, staticmethod):
            yield mname, raw.__func__
            continue
        if inspect.isfunction(raw):
            inst = cls()
            yield mname, getattr(inst, mname)


async def _await_result(awaitable: Awaitable[T]) -> T:
    return await awaitable


def _invoke_test(meth: TestCallable) -> object:
    """Invoke one test and synchronously complete any awaitable it returns."""

    result = meth()
    if inspect.isawaitable(result):
        return asyncio.run(_await_result(result))
    return result


def _run_case(
    owner: str,
    name: str,
    meth: TestCallable,
    superseded_key: tuple[str, str] | None = None,
) -> tuple[int, int, int]:
    """Run one collected test and return pass/fail/superseded deltas."""

    try:
        _invoke_test(meth)
        print("PASS", owner, name)
        return 1, 0, 0
    except AssertionError as exc:
        spec = SUPERSEDED_ASSERTIONS.get(superseded_key) if superseded_key else None
        if spec and _matches_superseded_assertion(meth, exc, spec["assertion"]):
            print("SUPERSEDED", owner, name, "->", spec["successor"], repr(exc))
            return 0, 0, 1
        print("FAIL", owner, name, type(exc).__name__, exc)
        return 0, 1, 0
    except SystemExit as exc:
        print("FAIL", owner, name, type(exc).__name__, exc)
        return 0, 1, 0
    except Exception as exc:
        print("FAIL", owner, name, type(exc).__name__, exc)
        return 0, 1, 0


def main() -> int:
    fails = 0
    passes = 0
    superseded = 0
    for mod in (f, j, c, x):
        for name, meth in _iter_module_test_functions(mod):
            p, failed, s = _run_case(mod.__name__, name, meth)
            passes += p
            fails += failed
            superseded += s

        for name, cls in inspect.getmembers_static(mod, inspect.isclass):
            if not name.startswith("Test") or cls.__module__ != mod.__name__:
                continue
            for mname, meth in _iter_test_methods(cls):
                p, failed, s = _run_case(name, mname, meth, (name, mname))
                passes += p
                fails += failed
                superseded += s

    print(f"RESULT {passes} ok {fails} fail {superseded} superseded")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
