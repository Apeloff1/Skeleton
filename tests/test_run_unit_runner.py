from __future__ import annotations

import inspect
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


def test_nested_assertion_cannot_be_suppressed_by_method_name() -> None:
    probe = _Probe()
    exc = _capture(probe.test_nested_failure)
    assert not runner._matches_superseded_assertion(
        probe.test_nested_failure,
        exc,
        'assert False, "legacy-terminal"',
    )


def test_test_methods_get_fresh_instances() -> None:
    methods = list(runner._iter_test_methods(_Probe))
    owners = [getattr(meth, "__self__", None) for _, meth in methods]
    assert len(owners) == 3
    assert len({id(owner) for owner in owners}) == len(owners)


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


def test_system_exit_zero_is_recorded_as_failure(monkeypatch, capsys) -> None:
    class TestExit:
        def test_exit_zero(self) -> None:
            raise SystemExit(0)

    probe = _module_with_test_class("runner_exit_probe", TestExit)
    empty = ModuleType("runner_empty_probe")
    monkeypatch.setattr(runner, "f", probe)
    monkeypatch.setattr(runner, "j", empty)
    monkeypatch.setattr(runner, "c", empty)
    monkeypatch.setattr(runner, "x", empty)

    assert runner.main() == 1
    out = capsys.readouterr().out
    assert "FAIL TestExit test_exit_zero SystemExit 0" in out
    assert "RESULT 0 ok 1 fail 0 superseded" in out


def test_superseded_registry_has_no_stale_jeeves_escape_hatch() -> None:
    assert ("TestJeevesLM", "test_unfitted_does_not_speak") not in runner.SUPERSEDED_ASSERTIONS


def test_registered_legacy_assertion_still_exists_in_target_method() -> None:
    key = ("TestNeural", "test_train_fits_all_four_neurals")
    spec = runner.SUPERSEDED_ASSERTIONS[key]
    source = inspect.getsource(cortex_tests.TestNeural.test_train_fits_all_four_neurals)
    assert spec["assertion"] in source
