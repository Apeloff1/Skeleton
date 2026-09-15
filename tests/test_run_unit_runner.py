from __future__ import annotations

import inspect
import unittest
from types import ModuleType

import tests.run_unit as runner
import tests.test_cortex as cortex_tests


class _Probe:
    def test_exact_legacy_failure(self) -> None:
        assert False, "legacy-terminal"

    def test_different_failure(self) -> None:
        assert False, "different"

    def test_nested_failure(self) -> None:
        _raise_nested()


class _DuplicateProbe:
    def test_duplicate_failure(self) -> None:
        assert False, "duplicated-terminal"
        assert False, "duplicated-terminal"


class _DescriptorProbe:
    def test_instance(self) -> str:
        return "instance"

    @staticmethod
    def test_static() -> str:
        return "static"

    @classmethod
    def test_class(cls) -> type:
        return cls


class _AsyncProbe:
    def __init__(self) -> None:
        self.ran = False

    async def test_async_success(self) -> None:
        self.ran = True

    async def test_async_failure(self) -> None:
        raise AssertionError("async-regression")


def _raise_nested() -> None:
    assert False, "legacy-terminal"


def _capture(bound_method) -> AssertionError:
    try:
        bound_method()
    except AssertionError as exc:
        return exc
    raise AssertionError("probe did not fail")


def _module_with_test_class(name: str, cls: type) -> ModuleType:
    mod = ModuleType(name)
    cls.__module__ = name
    setattr(mod, cls.__name__, cls)
    return mod


def _run_only(monkeypatch, mod: ModuleType) -> int:
    monkeypatch.setattr(runner, "TEST_MODULE_NAMES", (mod.__name__,))
    monkeypatch.setattr(runner, "SUPERSEDED_ASSERTIONS", {})
    monkeypatch.setattr(runner, "_load_test_module", lambda _: mod)
    return runner.main()


def test_superseded_match_requires_exact_terminal_source_line() -> None:
    probe = _Probe()
    exc = _capture(probe.test_exact_legacy_failure)
    assert runner._matches_superseded_assertion(
        probe.test_exact_legacy_failure,
        exc,
        'assert False, "legacy-terminal"',
    )
    assert not runner._matches_superseded_assertion(
        probe.test_exact_legacy_failure,
        exc,
        'assert False, "different"',
    )


def test_duplicate_obsolete_assertion_is_ambiguous_and_not_suppressible() -> None:
    try:
        runner._resolve_assertion_location(
            _DuplicateProbe.test_duplicate_failure,
            'assert False, "duplicated-terminal"',
        )
    except RuntimeError as exc:
        assert "exactly once" in str(exc)
        assert "found 2" in str(exc)
    else:
        raise AssertionError("ambiguous suppression location was accepted")


def test_nested_assertion_cannot_be_suppressed_by_method_name() -> None:
    probe = _Probe()
    exc = _capture(probe.test_nested_failure)
    assert not runner._matches_superseded_assertion(
        probe.test_nested_failure,
        exc,
        'assert False, "legacy-terminal"',
    )


def test_superseded_registry_is_immutable() -> None:
    try:
        runner.SUPERSEDED_ASSERTIONS[("TestInjected", "test_escape")] = {}  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("suppression registry was mutable")


def test_test_methods_get_fresh_instances() -> None:
    methods = list(runner._iter_test_methods(_Probe))
    owners = [getattr(meth, "__self__", None) for _, meth in methods]
    assert len(owners) == 3
    assert len({id(owner) for owner in owners}) == len(owners)


def test_static_and_class_methods_are_not_silently_dropped() -> None:
    methods = dict(runner._iter_test_methods(_DescriptorProbe))
    assert set(methods) == {"test_instance", "test_static", "test_class"}
    assert methods["test_instance"]() == "instance"
    assert methods["test_static"]() == "static"
    assert methods["test_class"]() is _DescriptorProbe


def test_module_level_functions_are_collected_but_imports_are_not() -> None:
    mod = ModuleType("runner_module_probe")

    def test_local() -> str:
        return "local"

    def test_imported() -> str:
        return "imported"

    test_local.__module__ = mod.__name__
    test_imported.__module__ = "some_other_module"
    mod.test_local = test_local
    mod.test_imported = test_imported

    functions = dict(runner._iter_module_test_functions(mod))
    assert set(functions) == {"test_local"}
    assert functions["test_local"]() == "local"


def test_awaitable_test_result_is_executed_to_completion() -> None:
    probe = _AsyncProbe()
    runner._invoke_test(probe.test_async_success)
    assert probe.ran is True


def test_async_assertion_is_not_counted_as_a_pass() -> None:
    probe = _AsyncProbe()
    try:
        runner._invoke_test(probe.test_async_failure)
    except AssertionError as exc:
        assert str(exc) == "async-regression"
    else:
        raise AssertionError("async assertion was not propagated")


def test_generator_style_test_is_rejected_instead_of_counted_as_pass() -> None:
    def test_generator():
        yield "body-never-ran"

    try:
        runner._invoke_test(test_generator)
    except RuntimeError as exc:
        assert "generator-style" in str(exc)
    else:
        raise AssertionError("generator test was counted as a pass")


def test_system_exit_zero_is_recorded_as_failure(monkeypatch, capsys) -> None:
    class TestExit:
        def test_exit_zero(self) -> None:
            raise SystemExit(0)

    probe = _module_with_test_class("runner_exit_probe", TestExit)
    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL TestExit test_exit_zero SystemExit 0" in out
    assert "RESULT 0 ok 1 fail 0 superseded" in out


def test_module_level_failure_changes_main_exit_status(monkeypatch, capsys) -> None:
    probe = ModuleType("runner_module_failure")

    def test_failure() -> None:
        raise AssertionError("module-regression")

    test_failure.__module__ = probe.__name__
    probe.test_failure = test_failure

    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL runner_module_failure test_failure AssertionError module-regression" in out
    assert "RESULT 0 ok 1 fail 0 superseded" in out


def test_import_system_exit_zero_is_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(runner, "TEST_MODULE_NAMES", ("runner_import_exit",))
    monkeypatch.setattr(runner, "SUPERSEDED_ASSERTIONS", {})

    def exit_during_import(_: str) -> ModuleType:
        raise SystemExit(0)

    monkeypatch.setattr(runner, "_load_test_module", exit_during_import)
    assert runner.main() == 1
    out = capsys.readouterr().out
    assert "FAIL IMPORT runner_import_exit SystemExit 0" in out
    assert "RESULT 0 ok 1 fail 0 superseded" in out


def test_empty_target_module_fails_collection(monkeypatch, capsys) -> None:
    empty = ModuleType("runner_empty_probe")
    assert _run_only(monkeypatch, empty) == 1
    out = capsys.readouterr().out
    assert "FAIL COLLECT runner_empty_probe no tests collected" in out
    assert "RESULT 0 ok 1 fail 0 superseded" in out


def test_constructor_system_exit_is_failure_at_test_execution(monkeypatch, capsys) -> None:
    class TestCtorExit:
        def __init__(self) -> None:
            raise SystemExit(0)

        def test_never_runs(self) -> None:
            raise AssertionError("unreachable")

    probe = _module_with_test_class("runner_ctor_exit", TestCtorExit)
    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL TestCtorExit test_never_runs SystemExit 0" in out
    assert "RESULT 0 ok 1 fail 0 superseded" in out


def test_class_construction_is_deferred_until_each_test_executes(monkeypatch) -> None:
    events: list[str] = []

    class TestTiming:
        def __init__(self) -> None:
            events.append("construct")

        def test_a(self) -> None:
            events.append("a")

        def test_b(self) -> None:
            events.append("b")

    probe = _module_with_test_class("runner_timing_probe", TestTiming)
    assert _run_only(monkeypatch, probe) == 0
    assert events == ["construct", "a", "construct", "b"]


def test_all_modules_are_loaded_before_first_test_body_executes(monkeypatch) -> None:
    events: list[str] = []
    first = ModuleType("runner_preload_first")
    second = ModuleType("runner_preload_second")

    def test_first() -> None:
        events.append("run:first")

    def test_second() -> None:
        events.append("run:second")

    test_first.__module__ = first.__name__
    test_second.__module__ = second.__name__
    first.test_first = test_first
    second.test_second = test_second
    modules = {first.__name__: first, second.__name__: second}

    def loader(name: str) -> ModuleType:
        events.append(f"load:{name}")
        return modules[name]

    monkeypatch.setattr(runner, "TEST_MODULE_NAMES", (first.__name__, second.__name__))
    monkeypatch.setattr(runner, "SUPERSEDED_ASSERTIONS", {})
    monkeypatch.setattr(runner, "_load_test_module", loader)

    assert runner.main() == 0
    assert events == [
        "load:runner_preload_first",
        "load:runner_preload_second",
        "run:first",
        "run:second",
    ]


def test_pytest_marked_function_fails_collection_instead_of_partial_execution(
    monkeypatch, capsys
) -> None:
    probe = ModuleType("runner_marked_probe")

    def test_marked(value: int = 1) -> None:
        assert value == 1

    test_marked.__module__ = probe.__name__
    test_marked.pytestmark = [object()]  # type: ignore[attr-defined]
    probe.test_marked = test_marked

    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL COLLECT runner_marked_probe RuntimeError unsupported pytest marks on test_marked" in out


def test_module_pytest_marks_fail_collection(monkeypatch, capsys) -> None:
    probe = ModuleType("runner_module_mark_probe")
    probe.pytestmark = [object()]

    def test_would_be_marker_controlled() -> None:
        pass

    test_would_be_marker_controlled.__module__ = probe.__name__
    probe.test_would_be_marker_controlled = test_would_be_marker_controlled

    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL COLLECT runner_module_mark_probe unsupported module pytest marks" in out


def test_unittest_testcase_is_rejected_instead_of_skipping_setup(monkeypatch, capsys) -> None:
    class TestUnit(unittest.TestCase):
        def setUp(self) -> None:
            raise AssertionError("setup-must-run")

        def test_would_look_green_without_setup(self) -> None:
            pass

    probe = _module_with_test_class("runner_unittest_probe", TestUnit)
    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL COLLECT TestUnit unsupported unittest.TestCase semantics" in out


def test_callable_test_object_is_rejected_instead_of_silently_dropped(monkeypatch, capsys) -> None:
    probe = ModuleType("runner_callable_probe")

    class CallableTest:
        def __call__(self) -> None:
            raise AssertionError("must-not-disappear")

    CallableTest.__module__ = probe.__name__
    probe.test_callable = CallableTest()

    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL COLLECT runner_callable_probe RuntimeError unsupported callable test shape test_callable" in out


def test_class_lifecycle_hooks_are_rejected_instead_of_ignored(monkeypatch, capsys) -> None:
    class TestLifecycle:
        def setup_method(self) -> None:
            raise AssertionError("setup-regression")

        def test_would_look_green_without_setup(self) -> None:
            pass

    probe = _module_with_test_class("runner_lifecycle_probe", TestLifecycle)
    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL COLLECT TestLifecycle unsupported lifecycle hook setup_method" in out
    assert "RESULT 0 ok 1 fail 0 superseded" in out


def test_module_lifecycle_hooks_are_rejected_instead_of_ignored(monkeypatch, capsys) -> None:
    probe = ModuleType("runner_module_lifecycle_probe")

    def setup_function() -> None:
        raise AssertionError("setup-regression")

    def test_would_look_green_without_setup() -> None:
        pass

    setup_function.__module__ = probe.__name__
    test_would_look_green_without_setup.__module__ = probe.__name__
    probe.setup_function = setup_function
    probe.test_would_look_green_without_setup = test_would_look_green_without_setup

    assert _run_only(monkeypatch, probe) == 1
    out = capsys.readouterr().out
    assert "FAIL COLLECT runner_module_lifecycle_probe unsupported lifecycle hook setup_function" in out
    assert "RESULT 0 ok 1 fail 0 superseded" in out


def test_stale_suppression_target_fails_configuration() -> None:
    probe = ModuleType("runner_suppression_probe")
    registry = {
        ("TestMissing", "test_missing"): {
            "module": probe.__name__,
            "successor": "TestReplacement.test_real",
            "assertion": "assert False",
        }
    }

    try:
        runner._resolve_suppressions([probe], registry=registry)
    except RuntimeError as exc:
        assert "target class is missing" in str(exc)
    else:
        raise AssertionError("stale suppression target did not fail closed")


def test_superseded_registry_has_no_stale_jeeves_escape_hatch() -> None:
    assert ("TestJeevesLM", "test_unfitted_does_not_speak") not in runner.SUPERSEDED_ASSERTIONS


def test_registered_legacy_assertion_still_exists_in_target_method() -> None:
    key = ("TestNeural", "test_train_fits_all_four_neurals")
    spec = runner.SUPERSEDED_ASSERTIONS[key]
    source = inspect.getsource(cortex_tests.TestNeural.test_train_fits_all_four_neurals)
    assert spec["module"] == "tests.test_cortex"
    assert spec["assertion"] in source
