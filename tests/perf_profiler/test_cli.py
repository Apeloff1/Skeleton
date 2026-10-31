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


def test_alloc_limits(capsys):
    target = f"{__name__}:allocate_two_mb"
    assert main(["alloc", target]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["alloc_bytes"] >= 2 * 1024 * 1024
    assert main(["alloc", target, "--max-alloc-bytes", "1024"]) == 1
    assert main(["alloc", "no_colon"]) == 2
    assert main(["alloc", "json:does_not_exist"]) == 2
    _KEEP.clear()


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
