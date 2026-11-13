import json

from skeleton.perf_profiler.cli import main
from skeleton.perf_profiler.clock import DeterministicClock
from skeleton.perf_profiler.load_timers import LoadTimer

_KEEP = []


def allocate_two_mb():
    _KEEP.append(bytearray(2 * 1024 * 1024))


def test_frames_pass_and_fail(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps([10, 12, 14]))
    assert main(["frames", str(good), "--budget-ms", "16"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pass"] is True and out["percentiles"]["samples"] == 3

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([10, 40]))
    assert main(["frames", str(bad), "--budget-ms", "16"]) == 1
    assert main(["frames", str(bad), "--budget-ms", "16", "--max-hitch-ratio", "0.5"]) == 0


def test_frames_empty_fails_closed_and_bad_input_is_usage_error(tmp_path):
    empty = tmp_path / "e.json"
    empty.write_text("[]")
    assert main(["frames", str(empty)]) == 1
    obj = tmp_path / "o.json"
    obj.write_text("{}")
    assert main(["frames", str(obj)]) == 2
    neg = tmp_path / "n.json"
    neg.write_text("[-1]")
    assert main(["frames", str(neg)]) == 2
    assert main(["frames", str(tmp_path / "missing.json")]) == 2


def test_alloc_limits(capsys, monkeypatch):
    target = f"{__name__}:allocate_two_mb"
    # No symbol import or invocation without both trusted-local gates.
    assert main(["alloc", target]) == 2
    assert _KEEP == []
    monkeypatch.setenv("SKELETON_PERF_TRUSTED_EXECUTION", "1")
    assert main(["alloc", target]) == 2
    assert _KEEP == []
    monkeypatch.delenv("SKELETON_PERF_TRUSTED_EXECUTION")
    assert main(["alloc", target, "--allow-local-callable"]) == 2
    assert _KEEP == []
    monkeypatch.setenv("SKELETON_PERF_TRUSTED_EXECUTION", "1")
    assert main(["alloc", target, "--allow-local-callable"]) == 2
    assert _KEEP == []
    monkeypatch.setenv("SKELETON_PERF_ALLOWED_TARGETS", target)
    assert main(["alloc", target, "--allow-local-callable"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["alloc_bytes"] >= 2 * 1024 * 1024
    assert main(["alloc", target, "--allow-local-callable", "--max-alloc-bytes", "1024"]) == 1
    assert main(["alloc", "no_colon", "--allow-local-callable"]) == 2
    assert main(["alloc", "json:does_not_exist", "--allow-local-callable"]) == 2
    _KEEP.clear()


def test_alloc_rejects_unpinned_target_before_import(monkeypatch):
    import skeleton.perf_profiler.cli as cli

    monkeypatch.setenv("SKELETON_PERF_TRUSTED_EXECUTION", "1")
    monkeypatch.setenv("SKELETON_PERF_ALLOWED_TARGETS", "json:loads")

    def forbidden_import(_module):
        raise AssertionError("untrusted module was imported")

    import importlib
    monkeypatch.setattr(importlib, "import_module", forbidden_import)
    assert main(["alloc", "untrusted.module:run", "--allow-local-callable"]) == 2



def test_alloc_allowlisted_but_unloaded_module_is_not_imported(monkeypatch, capsys):
    import importlib
    from skeleton.perf_profiler import cli

    target = "never_loaded_perf_target.worker:run"
    monkeypatch.setenv("SKELETON_PERF_TRUSTED_EXECUTION", "1")
    monkeypatch.setenv("SKELETON_PERF_ALLOWED_TARGETS", target)

    def forbidden_import(*_args, **_kwargs):
        raise AssertionError("allowlisted CLI input must not trigger an import")

    monkeypatch.setattr(importlib, "import_module", forbidden_import)
    assert cli.main(["alloc", target, "--allow-local-callable"]) == 2
    assert "preloaded" in capsys.readouterr().err


def test_alloc_does_not_evaluate_module_getattr(monkeypatch, capsys):
    import sys
    from types import ModuleType
    from skeleton.perf_profiler import cli

    name = "perf_profiler_preloaded_module_without_callable"
    module = ModuleType(name)

    def forbidden_getattr(_attr):
        raise AssertionError("module __getattr__ must not execute")

    module.__getattr__ = forbidden_getattr
    monkeypatch.setitem(sys.modules, name, module)
    target = f"{name}:run"
    monkeypatch.setenv("SKELETON_PERF_TRUSTED_EXECUTION", "1")
    monkeypatch.setenv("SKELETON_PERF_ALLOWED_TARGETS", target)
    assert cli.main(["alloc", target, "--allow-local-callable"]) == 2
    assert "preloaded callable" in capsys.readouterr().err


def test_alloc_rejects_fake_preloaded_module(monkeypatch, capsys):
    import sys
    from skeleton.perf_profiler import cli

    name = "perf_profiler_fake_module"
    monkeypatch.setitem(sys.modules, name, object())
    target = f"{name}:run"
    monkeypatch.setenv("SKELETON_PERF_TRUSTED_EXECUTION", "1")
    monkeypatch.setenv("SKELETON_PERF_ALLOWED_TARGETS", target)
    assert cli.main(["alloc", target, "--allow-local-callable"]) == 2
    assert "preloaded" in capsys.readouterr().err

def test_verify(tmp_path):
    t = LoadTimer(clock=DeterministicClock(script=[5]))
    with t.phase("boot"):
        pass
    path = tmp_path / "r.json"
    path.write_text(t.report().to_json())
    assert main(["verify", str(path)]) == 0
    data = json.loads(path.read_text())
    data["payload"]["total_ms"] = 0
    path.write_text(json.dumps(data))
    assert main(["verify", str(path)]) == 1


def test_usage_errors():
    assert main([]) == 2
    assert main(["bogus"]) == 2


def test_cli_rejects_oversized_input_and_frame_counts(tmp_path, monkeypatch):
    from skeleton.perf_profiler import cli

    monkeypatch.setattr(cli, "MAX_INPUT_BYTES", 16)
    too_big = tmp_path / "huge.json"
    too_big.write_text("[1, 2, 3, 4, 5, 6, 7]")
    assert cli.main(["frames", str(too_big)]) == 2
    monkeypatch.setattr(cli, "MAX_INPUT_BYTES", 1024)
    monkeypatch.setattr(cli, "MAX_FRAMES", 2)
    assert cli.main(["frames", str(too_big)]) == 2


def test_cli_rejects_nonfinite_ratio_and_invalid_allocation_limits(tmp_path, monkeypatch):
    from skeleton.perf_profiler import cli

    path = tmp_path / "frames.json"
    path.write_text("[16, 17]")
    for ratio in ("nan", "inf", "-0.1", "1.1"):
        assert cli.main(["frames", str(path), "--max-hitch-ratio", ratio]) == 2
    assert cli.main(["frames", str(path), "--budget-ms", "nan"]) == 2
    monkeypatch.setenv("SKELETON_PERF_TRUSTED_EXECUTION", "1")
    monkeypatch.setenv("SKELETON_PERF_ALLOWED_TARGETS", "json:dumps")
    assert cli.main(["alloc", "json:dumps", "--allow-local-callable", "--top", "101"]) == 2
    assert cli.main(["alloc", "json:dumps", "--allow-local-callable", "--max-peak-bytes", "-1"]) == 2


def test_cli_rejects_overflowing_frame_threshold_without_traceback(tmp_path, capsys):
    path = tmp_path / "frames.json"
    path.write_text("[10, 20]")
    assert main(["frames", str(path), "--budget-ms", "1e308", "--hitch-factor", "2"]) == 2
    captured = capsys.readouterr()
    assert "hitch threshold must be finite" in captured.err
    assert "Traceback" not in captured.err
