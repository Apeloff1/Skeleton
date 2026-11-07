"""scripts/install_godot.py: pinned, checksum-verified, fail-closed (no network)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("install_godot", ROOT / "scripts" / "install_godot.py")
ig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ig)

URL = "https://github.com/godotengine/godot/releases/download/4.3-stable/"


def _fixture(tmp_path, payload=b"fake-godot-binary", *, tamper=None):
    member = "Godot_v4.3-stable_linux.x86_64"
    src = tmp_path / "src"
    src.mkdir()
    zpath = src / "Godot_v4.3-stable_linux.x86_64.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(member, payload)
    tpz = src / "Godot_v4.3-stable_export_templates.tpz"
    with zipfile.ZipFile(tpz, "w") as zf:
        zf.writestr("templates/version.txt", "4.3.stable\n")
        zf.writestr("templates/linux_release.x86_64", b"tpl")
    manifest = {
        "version": "4.3-stable",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "archive": {"url": URL + zpath.name, "member": member,
                    "sha512": hashlib.sha512(zpath.read_bytes()).hexdigest()},
        "export_templates": {"url": URL + tpz.name,
                             "sha512": hashlib.sha512(tpz.read_bytes()).hexdigest(),
                             "install_dir": str(tmp_path / "templates"),
                             "members": ["templates/version.txt", "templates/linux_release.x86_64"]},
    }
    if tamper:
        tamper(manifest)
    mpath = tmp_path / "godot.artifact.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    return src, mpath


@pytest.fixture()
def offline(monkeypatch):
    def install(src):
        monkeypatch.setattr(ig, "_download", lambda url, dest: (
            dest.parent.mkdir(parents=True, exist_ok=True),
            dest.write_bytes((src / Path(url).name).read_bytes()),
        ))
    return install


def test_repo_manifest_is_fully_pinned():
    data = ig.load_manifest()
    assert data["version"] == "4.3-stable"
    assert len(data["sha256"]) == 64 and len(data["archive"]["sha512"]) == 128
    assert len(data["export_templates"]["sha512"]) == 128
    for url in (data["archive"]["url"], data["export_templates"]["url"]):
        assert url.startswith(URL)


def test_install_verifies_and_exports_env(tmp_path, offline, monkeypatch):
    src, mpath = _fixture(tmp_path)
    offline(src)
    env = tmp_path / "gh_env"
    monkeypatch.setenv("GITHUB_ENV", str(env))
    rc = ig.main(["--dest", str(tmp_path / "dest"), "--templates", "--manifest", str(mpath)])
    assert rc == 0
    binary = tmp_path / "dest" / "Godot_v4.3-stable_linux.x86_64"
    assert binary.read_bytes() == b"fake-godot-binary"
    assert env.read_text() == f"SKELETON_GODOT_BIN={binary}\n"
    assert (tmp_path / "templates" / "version.txt").read_text().strip() == "4.3.stable"


@pytest.mark.parametrize("tamper", [
    lambda m: m["archive"].update(sha512="0" * 128),
    lambda m: m.update(sha256="0" * 64),
    lambda m: m.update(bytes=1),
])
def test_install_fails_closed_on_mismatch(tmp_path, offline, tamper, monkeypatch):
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    src, mpath = _fixture(tmp_path, tamper=tamper)
    offline(src)
    assert ig.main(["--dest", str(tmp_path / "dest"), "--manifest", str(mpath)]) == 2


def test_refuses_unpinned_origin(tmp_path):
    with pytest.raises(ig.InstallError):
        ig._download("https://example.com/godot.zip", tmp_path / "x.zip")


def test_unpinned_manifest_rejected(tmp_path):
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps({"sha256": None, "bytes": 1, "archive": {}}), encoding="utf-8")
    with pytest.raises(ig.InstallError):
        ig.load_manifest(mpath)
