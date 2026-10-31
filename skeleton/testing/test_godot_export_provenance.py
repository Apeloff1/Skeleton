"""Deterministic export provenance manifests: build, round-trip, verify, CLI."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from skeleton.godot_export import cli, provenance

FIXTURES = Path(__file__).parent / "fixtures" / "godot_export"


@pytest.fixture()
def built(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "proj"
    shutil.copytree(FIXTURES / "good", root)
    out = root / "build" / "linux"
    out.mkdir(parents=True)
    (out / "gfd_fixture.x86_64").write_bytes(b"\x7fELF" + b"\1" * 60)
    (out / "gfd_fixture.pck").write_bytes(b"GDPC" + b"\2" * 60)
    return root, out


def test_tree_digest_ignores_build_and_cache_dirs(built):
    root, out = built
    before = provenance.tree_digest(root)
    (root / ".godot").mkdir()
    (root / ".godot" / "uid_cache.bin").write_bytes(b"x")
    (out / "extra.log").write_text("noise")
    assert provenance.tree_digest(root) == before
    (root / "scripts" / "game.gd").write_text("extends Node\n# edited\n")
    assert provenance.tree_digest(root) != before


def test_tree_digest_independent_of_location(built, tmp_path):
    root, _ = built
    other = tmp_path / "elsewhere"
    shutil.copytree(FIXTURES / "good", other)
    assert provenance.tree_digest(other) == provenance.tree_digest(root)


def test_manifest_is_deterministic_and_round_trips(built):
    root, out = built
    arts = {"Linux": out / "gfd_fixture.x86_64", "Linux.pck": out / "gfd_fixture.pck"}
    a = provenance.build(root, "4.7.2.stable.official", "SHIP", arts)
    b = provenance.build(root, "4.7.2.stable.official", "SHIP", dict(reversed(list(arts.items()))))
    assert a.dumps() == b.dumps()
    d = json.loads(a.dumps())
    assert d["schema"] == provenance.SCHEMA and d["project"] == "proj"
    assert [x["path"] for x in d["artifacts"]] == ["build/linux/gfd_fixture.x86_64", "build/linux/gfd_fixture.pck"]
    assert d["artifacts"][0]["size"] == 64
    again = provenance.Manifest.loads(a.dumps())
    assert again.dumps() == a.dumps()
    assert provenance.verify(again, root, root) == []


def test_verify_detects_tamper_missing_tree_and_verdict(built):
    root, out = built
    m = provenance.build(root, "4.7.2", "SHIP", {"Linux": out / "gfd_fixture.x86_64",
                                                 "pck": out / "gfd_fixture.pck"})
    (out / "gfd_fixture.x86_64").write_bytes(b"\x7fELF tampered")
    (out / "gfd_fixture.pck").unlink()
    (root / "main.tscn").write_text((root / "main.tscn").read_text() + "\n")
    problems = provenance.verify(m, root, root)
    assert any("sha256 mismatch" in p for p in problems)
    assert any("missing build/linux/gfd_fixture.pck" in p for p in problems)
    assert "project tree changed since manifest" in problems
    no_ship = provenance.Manifest(m.project, m.tree, m.engine, "NO-SHIP", m.git, [])
    assert provenance.verify(no_ship, root) == ["manifest verdict is NO-SHIP"]


def test_loads_rejects_unknown_schema():
    with pytest.raises(ValueError):
        provenance.Manifest.loads(json.dumps({"schema": "other/v9"}))


def test_artifact_outside_base_is_rejected(built, tmp_path):
    root, _ = built
    stray = tmp_path / "stray.bin"
    stray.write_bytes(b"x")
    with pytest.raises(ValueError):
        provenance.build(root, "4.7.2", "SHIP", {"Linux": stray})


def test_git_head(tmp_path):
    assert provenance.git_head(tmp_path) is None
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    (tmp_path / "f").write_text("x")
    run("add", "f")
    run("-c", "user.email=t@example.invalid", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit", "-qm", "x")
    head = provenance.git_head(tmp_path)
    assert head is not None and len(head) == 40


def test_cli_provenance_and_verify(built, capsys):
    root, out = built
    manifest = root.parent / "manifest.json"
    art = out / "gfd_fixture.x86_64"
    assert cli.main(["provenance", str(root), "--artifact", f"Linux={art}", "--verdict", "SHIP",
                     "--out", str(manifest)]) == 0
    assert json.loads(manifest.read_text())["artifacts"][0]["preset"] == "Linux"
    assert cli.main(["verify", str(manifest), "--base", str(root), "--project", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    art.write_bytes(b"changed")
    assert cli.main(["verify", str(manifest), "--base", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert cli.main(["provenance", str(root), "--artifact", "nopath", "--verdict", "SHIP"]) == 2
    assert cli.main(["provenance", str(root), "--verdict", "NO-SHIP"]) == 0
