"""GF-D QA certification: fixtures, fake-engine import/export flow, lint, CLI and case catalogue."""
from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import pytest

from skeleton.godot_export import cases, certify, cli, gdscript_lint, references, report
from skeleton.godot_export.cases import Severity
from skeleton.godot_export.project import GodotProject, path_to_res, res_to_path
from skeleton.godot_export.runner import GodotRunner, RunResult, subprocess_exec
from skeleton.godot_export import pck

FIXTURES = Path(__file__).parent / "fixtures" / "godot_export"

# case id -> defect planted in fixtures/godot_export/broken
EXPECTED_FAILURES = {
    "GFD-05": "dangling main scene / autoload / ext_resource / sub_resource",
    "GFP-01": "physics ticks 144",
    "GFP-02": "main scene missing",
    "GFP-03": "autoload target missing",
    "GFP-04": "no 4.x feature tag",
    "GFS-01": "RigidBody3D mass 0",
    "GFS-02": "SoftBody3D without pinned points",
    "GFL-01": "mixed tab/space indent",
    "GFL-02": "var before extends",
    "GFL-03": "preload target missing",
    "GFL-04": "duplicate class_name",
    "GFX-02": "unknown platform Dreamcast",
    "GFX-03": "absolute export path",
    "GFX-04": "bad arch / package / min_sdk",
    "GFX-08": "duplicate preset name",
    "GFX-09": "keystore password committed",
}


def _ids(rep: report.CertificationReport, passed: bool | None = None) -> set[str]:
    return {r.case_id for r in rep.results if passed is None or r.passed is passed}


@pytest.fixture()
def good(tmp_path: Path) -> Path:
    dst = tmp_path / "good"
    shutil.copytree(FIXTURES / "good", dst)
    return dst


# --- catalogue ---------------------------------------------------------------

def test_case_catalogue_is_consistent():
    assert len(cases.CASES) == len({c.id for c in cases._RAW})
    for c in cases.CASES.values():
        assert c.id[:3] in {"GFD", "GFX", "GFL", "GFP", "GFS", "GFB"}
        assert c.title and isinstance(c.severity, Severity)
    assert Severity.SEV1.blocking and Severity.SEV2.blocking and not Severity.SEV3.blocking
    assert {"GF-P0-38", "GF-P0-74", "GF-P0-96", "GF-P0-134"} <= set(cases.todo_ids())
    assert "GFS-02" in {c.id for c in cases.by_todo("GF-P0-96")}
    with pytest.raises(KeyError):
        cases.get("GFZ-99")


def test_report_rendering_and_verdict():
    rep = report.CertificationReport("demo")
    rep.add("GFD-00", True)
    rep.add("GFL-02", False, "ordering")  # Sev3: non-blocking
    assert rep.ship and rep.exit_code() == 0
    rep.add("GFX-05", False, {"exit": 1}, "Linux")
    assert not rep.ship and rep.exit_code() == 1
    s = rep.summary()
    assert (s["total"], s["passed"], s["failed"], s["sev1_failed"], s["sev3_failed"]) == (3, 1, 2, 1, 1)
    d = json.loads(rep.to_json())
    assert d["ship"] is False and d["results"][2]["title"].startswith("headless --export-release")
    md = rep.to_markdown()
    assert "NO-SHIP" in md and "| GFX-05 | 1 | FAIL | Linux |" in md
    with pytest.raises(KeyError):
        rep.add("NOPE-1", True)
    merged = report.merge("all", [rep])
    assert merged.results[0].subject == "demo" and len(merged.results) == 3


# --- static certification over fixtures --------------------------------------

def test_good_fixture_ships_statically():
    rep = certify.certify(FIXTURES / "good", certify.Options())
    assert rep.ship, rep.to_markdown()
    assert not rep.failures, rep.to_markdown()
    assert {"GFD-00", "GFD-05", "GFD-06", "GFP-01", "GFS-01", "GFS-02", "GFS-03", "GFX-01"} <= _ids(rep, True)


def test_broken_fixture_fails_every_planted_defect():
    rep = certify.certify(FIXTURES / "broken", certify.Options())
    assert not rep.ship
    assert _ids(rep, False) == set(EXPECTED_FAILURES), rep.to_markdown()
    gfd05 = next(r for r in rep.results if r.case_id == "GFD-05")
    kinds = {d["kind"] for d in gfd05.detail}
    assert {"main_scene", "autoload:Ghost", "ext_resource", "sub_id"} <= kinds


def test_missing_and_unparseable_project(tmp_path):
    rep = certify.certify(tmp_path, certify.Options())
    assert [(r.case_id, r.passed) for r in rep.results] == [("GFD-00", False)]
    (tmp_path / "project.godot").write_text("[application]\nconfig/name=bare\n")
    rep = certify.certify(tmp_path, certify.Options())
    assert rep.results[0].case_id == "GFD-00" and not rep.results[0].passed and not rep.ship


def test_ticks_option_is_honoured():
    rep = certify.certify(FIXTURES / "good", certify.Options(ticks=(120,)))
    assert "GFP-01" in _ids(rep, False)


def test_project_model(good):
    p = GodotProject.load(good)
    assert p.config_version == 5 and p.name == "GF-D Export Fixture"
    assert p.main_scene == "res://main.tscn" and p.engine_version == "4.7"
    assert p.autoloads == {"Game": "res://scripts/game.gd"}
    assert p.physics_ticks == 60
    (good / ".godot").mkdir()
    (good / ".godot" / "cached.gd").write_text("extends Node\n")
    assert [path_to_res(good, s) for s in p.scripts()] == ["res://scripts/game.gd", "res://scripts/player.gd"]
    assert res_to_path(good, "res://a/b.gd") == good / "a" / "b.gd"
    with pytest.raises(ValueError):
        res_to_path(good, "res://../escape.gd")
    with pytest.raises(ValueError):
        res_to_path(good, "user://save.dat")
    assert not p.exists("res://../escape.gd")


def test_references_on_good_fixture_are_clean():
    assert references.all_problems(GodotProject.load(FIXTURES / "good")) == []


def test_unparseable_scene_is_reported_as_dangling(good):
    (good / "bad.tscn").write_text("[gd_scene format=3]\n???\n")
    probs = references.all_problems(GodotProject.load(good))
    assert [d.kind for d in probs] == ["parse"]
    rep = certify.certify(good, certify.Options())
    assert "GFD-05" in _ids(rep, False)


# --- GDScript lint ------------------------------------------------------------

def test_lint_clean_source_with_annotations_and_docstrings():
    src = '@tool\nextends Node\nclass_name Ok\n"""\nextends Nope\n"""\nvar a := "# not a comment"\n\nfunc f():\n\tpass\n'
    assert gdscript_lint.lint_source(src) == []


def test_lint_detects_indent_and_ordering():
    issues = gdscript_lint.lint_source("extends Node\nfunc a():\n\tpass\nfunc b():\n    pass\nextends Other\n")
    assert [(i.case_id, i.line) for i in issues] == [("GFL-01", 5), ("GFL-02", 6)]
    mixed = gdscript_lint.lint_source("extends Node\nfunc a():\n\t  pass\n")
    assert mixed[0].case_id == "GFL-01" and "mixed" in mixed[0].message


def test_lint_helpers():
    text = 'extends Node\nclass_name Foo\nconst A = preload("res://a.gd") # preload("res://commented.gd")\n'
    assert gdscript_lint.class_name_of(text) == "Foo"
    assert gdscript_lint.preload_targets(text) == [(3, "res://a.gd")]
    assert gdscript_lint.class_name_of("extends Node\n") is None


# --- fake-engine runs ---------------------------------------------------------

class FakeEngine:
    """Records argv and answers like Godot 4.7.2 would; writes export artifacts."""

    def __init__(self, version: str = "4.7.2.stable.official.e5b2a1f", import_out: str = "", fail_export: bool = False,
                 bad_script: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.version = version
        self.import_out = import_out
        self.fail_export = fail_export
        self.bad_script = bad_script

    def __call__(self, argv, cwd: Path, timeout: int) -> RunResult:
        argv = list(argv)
        self.calls.append(argv)
        if "--version" in argv:
            return RunResult(0, self.version + "\n", tuple(argv))
        if "--import" in argv:
            (cwd / ".godot").mkdir(exist_ok=True)
            return RunResult(0, "Godot Engine v4.7.2\n" + self.import_out, tuple(argv))
        if "--check-only" in argv:
            res = argv[argv.index("--script") + 1]
            if res == self.bad_script:
                return RunResult(1, f"SCRIPT ERROR: Parse Error: bad token\n   at: {res}\n", tuple(argv))
            return RunResult(0, "", tuple(argv))
        if "--export-release" in argv:
            if self.fail_export:
                return RunResult(1, "ERROR: No export template found", tuple(argv))
            preset, out = argv[argv.index("--export-release") + 1:][:2]
            out_p = Path(out)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            if preset == "Linux":
                out_p.write_bytes(b"\x7fELF\x02\x01\x01" + b"\0" * 11 + struct.pack("<H", 0x3E) + b"\0" * 40)
                out_p.with_suffix(".pck").write_bytes(pck.build_header((4, 7, 2), 7))
            elif preset == "Web":
                out_p.write_text("<html><body>game</body></html>")
                out_p.with_suffix(".js").write_text("//")
                out_p.with_suffix(".wasm").write_bytes(b"\0asm\1\0\0\0")
                out_p.with_suffix(".pck").write_bytes(pck.build_header((4, 7, 2), 7))
            return RunResult(0, "savepack: end", tuple(argv))
        return RunResult(2, "unexpected argv", tuple(argv))


def _engine_certify(root: Path, fake: FakeEngine, **kw) -> report.CertificationReport:
    opts = certify.Options(godot="godot", **kw)
    return certify.certify(root, opts, GodotRunner("godot", exec_fn=fake))


def test_engine_flow_ships_and_exports(good, tmp_path):
    fake = FakeEngine()
    out = tmp_path / "out"
    rep = _engine_certify(good, fake, export=True, out_dir=out)
    assert rep.ship, rep.to_markdown()
    assert not rep.failures, rep.to_markdown()
    assert {"GFB-01", "GFD-01", "GFD-02", "GFD-03", "GFD-04", "GFX-05", "GFX-06", "GFX-07"} <= _ids(rep, True)
    assert sum(1 for r in rep.results if r.case_id == "GFX-05") == 2
    assert (out / "build/linux/gfd_fixture.x86_64").is_file() and (out / "build/web/index.html").is_file()
    assert all(c[1] == "--headless" for c in fake.calls if "--version" not in c)
    assert sum(1 for c in fake.calls if "--check-only" in c) == 2


def test_engine_preset_filter(good, tmp_path):
    fake = FakeEngine()
    rep = _engine_certify(good, fake, export=True, out_dir=tmp_path, presets=["Web"])
    assert [r.subject for r in rep.results if r.case_id == "GFX-05"] == ["Web"]


def test_engine_version_mismatch_blocks(good):
    rep = _engine_certify(good, FakeEngine(version="4.3.stable.official"))
    assert "GFB-01" in _ids(rep, False) and not rep.ship


def test_engine_import_errors_block(good):
    rep = _engine_certify(good, FakeEngine(import_out="ERROR: Condition \"!f\" is true.\n"
                                                      "Failed loading resource: res://gone.png\n"))
    assert {"GFD-02", "GFD-05"} <= _ids(rep, False) and not rep.ship


def test_engine_check_only_failure_blocks(good):
    rep = _engine_certify(good, FakeEngine(bad_script="res://scripts/player.gd"))
    gfd04 = next(r for r in rep.results if r.case_id == "GFD-04")
    assert not gfd04.passed and gfd04.detail[0]["script"] == "res://scripts/player.gd"


def test_engine_export_failure_blocks(good, tmp_path):
    rep = _engine_certify(good, FakeEngine(fail_export=True), export=True, out_dir=tmp_path)
    assert "GFX-05" in _ids(rep, False) and "GFX-06" not in _ids(rep)


def test_engine_export_skipped_when_presets_block(tmp_path):
    root = tmp_path / "broken"
    shutil.copytree(FIXTURES / "broken", root)
    fake = FakeEngine()
    rep = _engine_certify(root, fake, export=True, out_dir=tmp_path / "out")
    assert not any("--export-release" in c for c in fake.calls)
    assert not rep.ship


def test_sha_pin(good, tmp_path):
    binary = tmp_path / "godot"
    binary.write_bytes(b"fake engine")
    from skeleton.godot_export.binary import Pin, check_sha, sha256_file
    assert check_sha(binary, Pin()).passed
    assert check_sha(binary, Pin(sha256=sha256_file(binary).upper())).passed
    assert not check_sha(binary, Pin(sha256="0" * 64)).passed
    assert not check_sha(tmp_path / "absent", Pin(sha256="0" * 64)).passed
    opts = certify.Options(godot=str(binary), pin=Pin(sha256="0" * 64))
    rep = certify.certify(good, opts, GodotRunner(str(binary), exec_fn=FakeEngine()))
    assert "GFB-02" in _ids(rep, False)


def test_subprocess_exec_failures_are_receipts(tmp_path):
    r = subprocess_exec([str(tmp_path / "no-such-godot"), "--version"], tmp_path, 5)
    assert r.launch_failed and r.code == 127 and "launch failed" in r.output
    t = subprocess_exec(["sleep", "5"], tmp_path, 1)
    assert t.timed_out and "Godot timed out" in t.output


def test_runner_argv_and_bad_mode(tmp_path):
    seen = []
    r = GodotRunner("godot", exec_fn=lambda a, c, t: seen.append(list(a)) or RunResult(0, ""))
    r.import_project(tmp_path)
    r.export(tmp_path, "Linux", "out.x86_64", "pack")
    assert seen[0][:2] == ["godot", "--headless"] and "--import" in seen[0]
    assert "--export-pack" in seen[1]
    with pytest.raises(ValueError):
        r.export(tmp_path, "Linux", "x", "shipit")
    assert GodotRunner("godot", headless=False).argv(["--import"]) == ["godot", "--import"]


# --- CLI ----------------------------------------------------------------------

def test_cli_cases_lists_catalogue(capsys):
    assert cli.main(["cases"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == len(cases.CASES) and lines[0].startswith("GFD-00\tSev1\t")


def test_cli_certify_json_and_markdown(capsys):
    assert cli.main(["certify", str(FIXTURES / "good")]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["ship"] is True
    assert cli.main(["certify", str(FIXTURES / "good"), str(FIXTURES / "broken"), "--format", "markdown"]) == 1
    out = capsys.readouterr().out
    assert "**Verdict:** SHIP" in out and "**Verdict:** NO-SHIP" in out


def test_cli_missing_binary_fails_closed(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("GODOT_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cli.main(["certify", str(FIXTURES / "good"), "--godot", str(tmp_path / "missing")]) == 1
    assert json.loads(capsys.readouterr().out)["case"] == "GFB-01"
