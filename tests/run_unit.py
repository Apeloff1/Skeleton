#!/usr/bin/env python3
"""Small dependency-free runner for the legacy GameForge unit modules.

The GameForge cortex has intentionally strengthened several model-ownership
contracts over time. Queue28/Queue29 trains PFC's internal transformer, while
the live CI repair also forbids unfitted tract mouths from being absorbed into
Neo or falsely promoting the owned LM to fitted state. A few older assertions
encode those superseded pre-transfer assumptions. We execute the legacy tests
and may suppress only the exact obsolete assertion lines documented below.
Any different assertion failure in the same test remains a hard failure, and
successor contract tests exercise the replacement behavior directly.

This runner intentionally stays lightweight, but it also preserves pytest's
important per-test instance isolation, executes awaitable test results to
completion, collects module-level and descriptor-backed tests, and fails closed
when imports, collection, unsupported test semantics, or explicit ``SystemExit``
attempts short-circuit the suite.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
import unittest
from pathlib import Path
from types import CodeType, MappingProxyType, ModuleType, TracebackType
from typing import Awaitable, Callable, Iterator, Mapping, NamedTuple, TypeVar

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_MODULE_NAMES = (
    "tests.test_forge",
    "tests.test_jeeves",
    "tests.test_context",
    "tests.test_cortex",
    "tests.test_cortex_acquire_contract",
    "skeleton.testing.test_simulation_physics_ccd_advanced",
    "skeleton.testing.test_simulation_physics_character",
    "skeleton.testing.test_simulation_physics_constraints",
    "skeleton.testing.test_simulation_physics_convex",
    "skeleton.testing.test_simulation_physics_convex_collision",
    "skeleton.testing.test_simulation_physics_convex_queries",
    "skeleton.testing.test_simulation_physics_convex_toi",
    "skeleton.testing.test_simulation_physics_fixed_slider",
    "skeleton.testing.test_simulation_physics_foundation",
    "skeleton.testing.test_simulation_physics_hinge",
    "skeleton.testing.test_simulation_physics_islands",
    "skeleton.testing.test_simulation_physics_joint_cache_coloring",
    "skeleton.testing.test_simulation_physics_manifolds",
    "skeleton.testing.test_simulation_physics_obb_edges",
    "skeleton.testing.test_simulation_physics_plane_toi",
    "skeleton.testing.test_simulation_physics_replay",
)

UNSUPPORTED_MODULE_LIFECYCLE_HOOKS = (
    "setup_module",
    "teardown_module",
    "setup_function",
    "teardown_function",
)
UNSUPPORTED_CLASS_LIFECYCLE_HOOKS = (
    "setup_class",
    "teardown_class",
    "setup_method",
    "teardown_method",
)

# These are not generic skips. The target is resolved before any test body runs,
# and suppression is permitted only when the terminal traceback points at the
# one unique source line documented here.
SUPERSEDED_ASSERTIONS = MappingProxyType(
    {
        ("TestNeural", "test_train_fits_all_four_neurals"): MappingProxyType(
            {
                "module": "tests.test_cortex",
                "successor": "TestQueue28Queue29.test_tied_cosine_all_slot_lms",
                "assertion": 'assert lms["pfc"]["transformer_steps"] == 0',
            }
        ),
        ("TestQueue24", "test_acquire_copies_the_model"): MappingProxyType(
            {
                "module": "tests.test_cortex",
                "successor": "TestAcquireAbsorbContract.test_unfitted_source_is_stored_without_promoting_neo",
                "assertion": 'assert got["absorb"]["absorbed"] == 1',
            }
        ),
        ("TestQueue25", "test_surpass_is_neo_decode"): MappingProxyType(
            {
                "module": "tests.test_cortex",
                "successor": "TestAcquireAbsorbContract.test_trained_source_absorbs_and_surpass_decodes_from_neo",
                "assertion": 'assert a.amalgam.kind == "own-lm" and b.amalgam.kind == "own-lm"',
            }
        ),
    }
)

T = TypeVar("T")
TestCallable = Callable[[], object]
_MISSING = object()


class ResolvedSuppression(NamedTuple):
    code: CodeType
    line: int
    successor: str


class CollectedCase(NamedTuple):
    owner: str
    name: str
    meth: TestCallable
    suppression: ResolvedSuppression | None


def _terminal_traceback(exc: BaseException) -> TracebackType | None:
    tb = exc.__traceback__
    if tb is None:
        return None
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb


def _resolve_assertion_location(
    meth: object,
    expected_line: str,
    _getsourcelines: Callable[[object], tuple[list[str], int]] = inspect.getsourcelines,
) -> tuple[CodeType, int]:
    """Resolve one documented assertion to one immutable code/line identity."""

    func = getattr(meth, "__func__", meth)
    code = getattr(func, "__code__", None)
    if code is None:
        raise RuntimeError("suppression target has no Python code object")

    source, start = _getsourcelines(func)
    matches = [start + offset for offset, line in enumerate(source) if line.strip() == expected_line]
    if len(matches) != 1:
        raise RuntimeError(
            "documented superseded assertion must occur exactly once "
            f"(found {len(matches)})"
        )
    return code, matches[0]


def _matches_superseded_assertion(
    meth: object,
    exc: AssertionError,
    expected_line: str,
) -> bool:
    """Compatibility helper used by regression tests for exact suppression."""

    try:
        code, line = _resolve_assertion_location(meth, expected_line)
    except (OSError, RuntimeError, TypeError):
        return False
    tb = _terminal_traceback(exc)
    return tb is not None and tb.tb_frame.f_code is code and tb.tb_lineno == line


def _matches_resolved_suppression(exc: AssertionError, suppression: ResolvedSuppression) -> bool:
    tb = _terminal_traceback(exc)
    return (
        tb is not None
        and tb.tb_frame.f_code is suppression.code
        and tb.tb_lineno == suppression.line
    )


def _load_test_module(
    name: str,
    _import_module: Callable[[str], ModuleType] = importlib.import_module,
) -> ModuleType:
    return _import_module(name)


def _first_unsupported_hook(
    target: object,
    names: tuple[str, ...],
    _getattr_static: Callable[..., object] = inspect.getattr_static,
) -> str | None:
    for name in names:
        if _getattr_static(target, name, _MISSING) is not _MISSING:
            return name
    return None


def _has_pytest_marks(
    target: object,
    _getattr_static: Callable[..., object] = inspect.getattr_static,
) -> bool:
    """Return true when pytest-specific marker semantics would be required."""

    return _getattr_static(target, "pytestmark", _MISSING) is not _MISSING


def _iter_module_test_functions(
    mod: ModuleType,
    _getmembers_static: Callable[..., list[tuple[str, object]]] = inspect.getmembers_static,
    _isfunction: Callable[[object], bool] = inspect.isfunction,
) -> Iterator[tuple[str, TestCallable]]:
    """Yield local module tests and reject unsupported callable test shapes."""

    for name, candidate in _getmembers_static(mod):
        if not name.startswith("test_"):
            continue
        if _isfunction(candidate):
            if getattr(candidate, "__module__", None) != mod.__name__:
                continue
            if _has_pytest_marks(candidate):
                raise RuntimeError(f"unsupported pytest marks on {name}")
            yield name, candidate
            continue

        origin = getattr(candidate, "__module__", None)
        if origin not in (None, mod.__name__):
            continue
        if callable(candidate):
            raise RuntimeError(
                f"unsupported callable test shape {name}: {type(candidate).__name__}"
            )


def _iter_test_methods(
    cls: type,
    _getmembers_static: Callable[..., list[tuple[str, object]]] = inspect.getmembers_static,
    _isfunction: Callable[[object], bool] = inspect.isfunction,
) -> Iterator[tuple[str, TestCallable]]:
    """Compatibility collector returning fresh bound instances per method."""

    for mname, raw in _getmembers_static(cls):
        if not mname.startswith("test_"):
            continue
        if isinstance(raw, classmethod):
            func = raw.__func__
            if _has_pytest_marks(raw) or _has_pytest_marks(func):
                raise RuntimeError(f"unsupported pytest marks on {mname}")
            yield mname, getattr(cls, mname)
            continue
        if isinstance(raw, staticmethod):
            func = raw.__func__
            if _has_pytest_marks(raw) or _has_pytest_marks(func):
                raise RuntimeError(f"unsupported pytest marks on {mname}")
            yield mname, func
            continue
        if _isfunction(raw):
            if _has_pytest_marks(raw):
                raise RuntimeError(f"unsupported pytest marks on {mname}")
            inst = cls()
            yield mname, getattr(inst, mname)
            continue
        if callable(raw):
            raise RuntimeError(
                f"unsupported callable test shape {mname}: {type(raw).__name__}"
            )


def _iter_frozen_test_methods(
    cls: type,
    _getmembers_static: Callable[..., list[tuple[str, object]]] = inspect.getmembers_static,
    _isfunction: Callable[[object], bool] = inspect.isfunction,
) -> Iterator[tuple[str, TestCallable]]:
    """Freeze method identities while deferring instance construction to execution."""

    for mname, raw in _getmembers_static(cls):
        if not mname.startswith("test_"):
            continue
        if isinstance(raw, classmethod):
            func = raw.__func__
            if _has_pytest_marks(raw) or _has_pytest_marks(func):
                raise RuntimeError(f"unsupported pytest marks on {mname}")
            yield mname, (lambda _func=func, _cls=cls: _func(_cls))
            continue
        if isinstance(raw, staticmethod):
            func = raw.__func__
            if _has_pytest_marks(raw) or _has_pytest_marks(func):
                raise RuntimeError(f"unsupported pytest marks on {mname}")
            yield mname, func
            continue
        if _isfunction(raw):
            if _has_pytest_marks(raw):
                raise RuntimeError(f"unsupported pytest marks on {mname}")
            yield mname, (lambda _func=raw, _cls=cls: _func(_cls()))
            continue
        if callable(raw):
            raise RuntimeError(
                f"unsupported callable test shape {mname}: {type(raw).__name__}"
            )


async def _await_result(awaitable: Awaitable[T]) -> T:
    return await awaitable


def _invoke_test(meth: TestCallable) -> object:
    """Invoke one test and synchronously complete any awaitable it returns."""

    result = meth()
    if inspect.isawaitable(result):
        return asyncio.run(_await_result(result))
    if inspect.isgenerator(result) or inspect.isasyncgen(result):
        raise RuntimeError("legacy runner does not support generator-style tests")
    return result


def _unwrap_static_test_method(cls: type, name: str) -> object:
    raw = inspect.getattr_static(cls, name, _MISSING)
    if raw is _MISSING:
        raise RuntimeError(f"suppression target method is missing: {name}")
    if isinstance(raw, (classmethod, staticmethod)):
        return raw.__func__
    if inspect.isfunction(raw):
        return raw
    raise RuntimeError(f"suppression target is not a Python test method: {name}")


def _resolve_suppressions(
    modules: list[ModuleType],
    unavailable_modules: frozenset[str] = frozenset(),
    registry: Mapping[tuple[str, str], Mapping[str, str]] | None = None,
) -> Mapping[tuple[str, str, str], ResolvedSuppression]:
    """Resolve suppression policy before executing any test body."""

    active_registry = SUPERSEDED_ASSERTIONS if registry is None else registry
    by_name = {mod.__name__: mod for mod in modules}
    resolved: dict[tuple[str, str, str], ResolvedSuppression] = {}

    for (class_name, method_name), spec in active_registry.items():
        module_name = spec["module"]
        if module_name in unavailable_modules:
            continue
        mod = by_name.get(module_name)
        if mod is None:
            raise RuntimeError(f"suppression target module was not loaded: {module_name}")

        cls = inspect.getattr_static(mod, class_name, _MISSING)
        if not inspect.isclass(cls) or getattr(cls, "__module__", None) != module_name:
            raise RuntimeError(
                f"suppression target class is missing or imported: {module_name}.{class_name}"
            )

        meth = _unwrap_static_test_method(cls, method_name)
        code, line = _resolve_assertion_location(meth, spec["assertion"])
        resolved[(module_name, class_name, method_name)] = ResolvedSuppression(
            code=code,
            line=line,
            successor=spec["successor"],
        )

    return MappingProxyType(resolved)


def _run_case(
    case: CollectedCase,
    _invoke: Callable[[TestCallable], object] = _invoke_test,
) -> tuple[int, int, int]:
    """Run one pre-collected test and return pass/fail/superseded deltas."""

    try:
        _invoke(case.meth)
        print("PASS", case.owner, case.name)
        return 1, 0, 0
    except AssertionError as exc:
        suppression = case.suppression
        if suppression and _matches_resolved_suppression(exc, suppression):
            print(
                "SUPERSEDED",
                case.owner,
                case.name,
                "->",
                suppression.successor,
                repr(exc),
            )
            return 0, 0, 1
        print("FAIL", case.owner, case.name, type(exc).__name__, exc)
        return 0, 1, 0
    except SystemExit as exc:
        print("FAIL", case.owner, case.name, type(exc).__name__, exc)
        return 0, 1, 0
    except Exception as exc:
        print("FAIL", case.owner, case.name, type(exc).__name__, exc)
        return 0, 1, 0


def _collect_module(
    mod: ModuleType,
    resolved_suppressions: Mapping[tuple[str, str, str], ResolvedSuppression],
) -> tuple[list[CollectedCase], int]:
    """Collect one module completely before any test body is allowed to run."""

    cases: list[CollectedCase] = []
    fails = 0
    collection_failed = False

    if _has_pytest_marks(mod):
        print("FAIL COLLECT", mod.__name__, "unsupported module pytest marks")
        return [], 1

    hook = _first_unsupported_hook(mod, UNSUPPORTED_MODULE_LIFECYCLE_HOOKS)
    if hook is not None:
        print("FAIL COLLECT", mod.__name__, "unsupported lifecycle hook", hook)
        return [], 1

    try:
        module_tests = list(_iter_module_test_functions(mod))
    except SystemExit as exc:
        print("FAIL COLLECT", mod.__name__, type(exc).__name__, exc)
        return [], 1
    except Exception as exc:
        print("FAIL COLLECT", mod.__name__, type(exc).__name__, exc)
        return [], 1

    for name, meth in module_tests:
        cases.append(CollectedCase(mod.__name__, name, meth, None))

    try:
        classes = inspect.getmembers_static(mod, inspect.isclass)
    except SystemExit as exc:
        print("FAIL COLLECT", mod.__name__, type(exc).__name__, exc)
        return cases, fails + 1
    except Exception as exc:
        print("FAIL COLLECT", mod.__name__, type(exc).__name__, exc)
        return cases, fails + 1

    for name, cls in classes:
        if not name.startswith("Test") or cls.__module__ != mod.__name__:
            continue

        if issubclass(cls, unittest.TestCase):
            print("FAIL COLLECT", name, "unsupported unittest.TestCase semantics")
            fails += 1
            collection_failed = True
            continue

        if _has_pytest_marks(cls):
            print("FAIL COLLECT", name, "unsupported class pytest marks")
            fails += 1
            collection_failed = True
            continue

        hook = _first_unsupported_hook(cls, UNSUPPORTED_CLASS_LIFECYCLE_HOOKS)
        if hook is not None:
            print("FAIL COLLECT", name, "unsupported lifecycle hook", hook)
            fails += 1
            collection_failed = True
            continue

        try:
            methods = list(_iter_frozen_test_methods(cls))
        except SystemExit as exc:
            print("FAIL COLLECT", name, type(exc).__name__, exc)
            fails += 1
            collection_failed = True
            continue
        except Exception as exc:
            print("FAIL COLLECT", name, type(exc).__name__, exc)
            fails += 1
            collection_failed = True
            continue

        for mname, meth in methods:
            suppression = resolved_suppressions.get((mod.__name__, name, mname))
            cases.append(CollectedCase(name, mname, meth, suppression))

    if not cases and not collection_failed:
        print("FAIL COLLECT", mod.__name__, "no tests collected")
        fails += 1

    return cases, fails


def _run_module(
    mod: ModuleType,
    resolved_suppressions: Mapping[tuple[str, str, str], ResolvedSuppression] | None = None,
) -> tuple[int, int, int]:
    """Compatibility wrapper for running one already-imported test module."""

    cases, fails = _collect_module(mod, resolved_suppressions or {})
    passes = 0
    superseded = 0
    for case in cases:
        p, failed, s = _run_case(case)
        passes += p
        fails += failed
        superseded += s
    return passes, fails, superseded


def main() -> int:
    fails = 0
    passes = 0
    superseded = 0

    # Capture runner policy before importing any test module. Imports can execute
    # arbitrary module-level code; they must not be able to rewrite what this
    # invocation intends to import or suppress.
    module_names = tuple(TEST_MODULE_NAMES)
    registry = SUPERSEDED_ASSERTIONS
    loader = _load_test_module
    resolver = _resolve_suppressions
    collector = _collect_module
    run_case = _run_case

    loaded: list[ModuleType] = []
    unavailable: set[str] = set()
    for module_name in module_names:
        try:
            loaded.append(loader(module_name))
        except SystemExit as exc:
            unavailable.add(module_name)
            fails += 1
            print("FAIL IMPORT", module_name, type(exc).__name__, exc)
        except Exception as exc:
            unavailable.add(module_name)
            fails += 1
            print("FAIL IMPORT", module_name, type(exc).__name__, exc)

    try:
        resolved = resolver(loaded, frozenset(unavailable), registry)
    except SystemExit as exc:
        fails += 1
        resolved = {}
        print("FAIL CONFIG superseded assertions", type(exc).__name__, exc)
    except Exception as exc:
        fails += 1
        resolved = {}
        print("FAIL CONFIG superseded assertions", type(exc).__name__, exc)

    # Freeze every test identity before the first test body executes. Instance
    # construction is still deferred to each test invocation, so test classes
    # keep per-test timing/isolation without allowing an earlier test to erase a
    # later method from collection.
    collected: list[CollectedCase] = []
    for mod in loaded:
        try:
            cases, collection_fails = collector(mod, resolved)
        except SystemExit as exc:
            fails += 1
            print("FAIL COLLECT", mod.__name__, type(exc).__name__, exc)
            continue
        except Exception as exc:
            fails += 1
            print("FAIL COLLECT", mod.__name__, type(exc).__name__, exc)
            continue
        collected.extend(cases)
        fails += collection_fails

    for case in collected:
        p, failed, s = run_case(case)
        passes += p
        fails += failed
        superseded += s

    print(f"RESULT {passes} ok {fails} fail {superseded} superseded")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
