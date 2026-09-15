from __future__ import annotations

import inspect

import tests.run_unit as runner
import tests.test_cortex as cortex_tests


class _Probe:
    def test_exact_legacy_failure(self) -> None:
        assert False, "legacy-terminal"

    def test_different_failure(self) -> None:
        assert False, "different"

    def test_nested_failure(self) -> None:
        _raise_nested()


def _raise_nested() -> None:
    assert False, "legacy-terminal"


def _capture(bound_method) -> AssertionError:
    try:
        bound_method()
    except AssertionError as exc:
        return exc
    raise AssertionError("probe did not fail")


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


def test_superseded_registry_has_no_stale_jeeves_escape_hatch() -> None:
    assert ("TestJeevesLM", "test_unfitted_does_not_speak") not in runner.SUPERSEDED_ASSERTIONS


def test_registered_legacy_assertion_still_exists_in_target_method() -> None:
    key = ("TestNeural", "test_train_fits_all_four_neurals")
    spec = runner.SUPERSEDED_ASSERTIONS[key]
    source = inspect.getsource(cortex_tests.TestNeural.test_train_fits_all_four_neurals)
    assert spec["assertion"] in source
