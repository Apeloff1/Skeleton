"""Export preset model and per-platform preset/artifact validators."""
from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from skeleton.godot_export import configfile, presets
from skeleton.godot_export.platforms import REGISTRY, get, known, linux, windows
from skeleton.godot_export.platforms.registry import canonical

FIXTURES = Path(__file__).parent / "fixtures" / "godot_export"


def _preset(platform: str, export_path: str, **options) -> presets.ExportPreset:
    return presets.ExportPreset(0, "P", platform, export_path, options=options)


def test_good_fixture_presets_load():
    ps = presets.load(FIXTURES / "good")
    assert [(p.index, p.name, p.platform) for p in ps] == [(0, "Linux", "Linux"), (1, "Web", "Web")]
    assert ps[0].runnable and not ps[1].runnable
    assert ps[0].option("binary_format/architecture") == "x86_64"
    assert all(p.export_path_is_relative for p in ps)


def test_preset_indices_must_be_contiguous():
    cfg = configfile.loads('[preset.0]\nname="a"\n\n[preset.2]\nname="b"\n')
    with pytest.raises(presets.PresetError):
        presets.from_config(cfg)


@pytest.mark.parametrize("path, ok", [
    ("build/game.x86_64", True), ("game.exe", True), ("", False), ("/abs/game", False),
    ("../outside/game", False), ("C:/games/x.exe", False), ("build\\..\\..\\x.exe", False),
])
def test_export_path_relative(path, ok):
    assert _preset("Linux", path).export_path_is_relative is ok


def test_secret_values_and_duplicates():
    p = _preset("Android", "a.apk", **{"keystore/release_password": "x", "keystore/debug_password": "",
                                       "package/unique_name": "com.example.g"})
    p.raw["encryption_key"] = "abcd"
    assert sorted(presets.secret_values(p)) == ["encryption_key", "keystore/release_password"]
    a, b = _preset("Linux", "a"), _preset("Linux", "b")
    assert presets.duplicate_names([a, b]) == ["P"]


def test_registry_and_aliases():
    assert set(REGISTRY) == {"Linux", "Windows Desktop", "macOS", "Web", "Android", "iOS"}
    assert canonical("Linux/X11") == "Linux" and known("HTML5") and known("Mac OSX")
    assert not known("Dreamcast")
    with pytest.raises(KeyError):
        get("Dreamcast")
    assert get("iOS").export_on_linux is False


@pytest.mark.parametrize("platform, path, options, n_problems", [
    ("Linux", "g.x86_64", {"binary_format/architecture": "x86_64"}, 0),
    ("Linux", "g.exe", {"binary_format/architecture": "x86_64"}, 1),
    ("Linux", "g.x86_64", {"binary_format/architecture": "sparc"}, 1),
    ("Windows Desktop", "g.exe", {"application/file_version": "1.0.0.0"}, 0),
    ("Windows Desktop", "g.exe", {"application/file_version": "1.0"}, 1),
    ("Windows Desktop", "g.exe", {"application/product_version": ""}, 0),
    ("macOS", "g.zip", {"application/bundle_identifier": "com.example.game"}, 0),
    ("macOS", "g.zip", {}, 1),
    ("macOS", "g.zip", {"application/bundle_identifier": "com.example.game", "notarization/notarization": 1,
                        "codesign/codesign": 0}, 1),
    ("Web", "index.html", {"variant/thread_support": False}, 0),
    ("Web", "index.html", {"variant/thread_support": "maybe"}, 1),
    ("Android", "g.apk", {"package/unique_name": "com.example.game", "gradle_build/min_sdk": "24"}, 0),
    ("Android", "g.aab", {"package/unique_name": "com.example.game", "gradle_build/min_sdk": "21"}, 1),
    ("Android", "g.apk", {"package/unique_name": "com.example.game", "gradle_build/min_sdk": "x"}, 1),
    ("Android", "g.apk", {}, 1),
    ("iOS", "g.ipa", {"application/bundle_identifier": "com.example.game", "application/app_store_team_id": "ABCDE12345"}, 0),
    ("iOS", "g.ipa", {"application/bundle_identifier": "com.example.game", "application/app_store_team_id": "short"}, 1),
])
def test_platform_preset_checks(platform, path, options, n_problems):
    assert len(get(platform).check_preset(_preset(platform, path, **options))) == n_problems


def _elf(machine: int) -> bytes:
    return b"\x7fELF\x02\x01\x01" + b"\0" * 11 + struct.pack("<H", machine) + b"\0" * 40


def _pe(machine: int) -> bytes:
    head = bytearray(b"MZ" + b"\0" * 0x7E)
    head[0x3C:0x40] = struct.pack("<I", 0x40)
    head[0x40:0x44] = b"PE\0\0"
    head[0x44:0x46] = struct.pack("<H", machine)
    return bytes(head)


def test_linux_and_windows_binary_detection(tmp_path):
    assert linux.elf_arch(_elf(0x3E)) == "x86_64"
    assert linux.elf_arch(_elf(0xB7)) == "arm64"
    assert linux.elf_arch(b"MZ") is None
    exe = tmp_path / "g.exe"
    exe.write_bytes(_pe(0x8664))
    assert windows.pe_arch(exe) == "x86_64"
    assert get("Windows Desktop").check_artifact(exe) == []
    elf = tmp_path / "g.x86_64"
    elf.write_bytes(_elf(0x3E))
    assert get("Linux").check_artifact(elf) == []
    assert get("Windows Desktop").check_artifact(elf)
    assert get("Linux").check_artifact(exe)


def test_artifact_missing_or_empty(tmp_path):
    spec = get("Linux")
    assert "missing" in spec.check_artifact(tmp_path / "nope")[0]
    empty = tmp_path / "e.x86_64"
    empty.touch()
    assert "empty" in spec.check_artifact(empty)[0]


def test_web_artifact(tmp_path):
    html = tmp_path / "index.html"
    html.write_text("<!DOCTYPE html><html><body></body></html>")
    assert len(get("Web").check_artifact(html)) == 3
    (tmp_path / "index.js").write_text("//")
    (tmp_path / "index.pck").write_bytes(b"GDPC")
    (tmp_path / "index.wasm").write_bytes(b"\0asm\1\0\0\0")
    assert get("Web").check_artifact(html) == []
    (tmp_path / "index.wasm").write_bytes(b"nope")
    assert get("Web").check_artifact(html) == ["index.wasm lacks wasm magic"]


def _zip(path: Path, names: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, "x")
    return path


def test_android_artifacts(tmp_path):
    spec = get("Android")
    assert spec.check_artifact(_zip(tmp_path / "ok.apk", ["AndroidManifest.xml", "classes.dex", "assets/game.pck"])) == []
    assert len(spec.check_artifact(_zip(tmp_path / "bad.apk", ["AndroidManifest.xml"]))) == 2
    assert spec.check_artifact(_zip(tmp_path / "ok.aab", ["base/manifest/AndroidManifest.xml", "base/assets/x.pck"])) == []
    bogus = tmp_path / "bogus.apk"
    bogus.write_bytes(b"not a zip")
    assert spec.check_artifact(bogus) == ["bogus.apk is not a zip"]


def test_macos_artifacts(tmp_path):
    spec = get("macOS")
    assert spec.check_artifact(_zip(tmp_path / "g.zip", ["G.app/Contents/Info.plist"])) == []
    assert spec.check_artifact(_zip(tmp_path / "n.zip", ["readme.txt"]))
    app = tmp_path / "G.app"
    (app / "Contents").mkdir(parents=True)
    assert spec.check_artifact(app)
    (app / "Contents" / "Info.plist").write_text("<plist/>")
    assert spec.check_artifact(app) == []
    dmg = tmp_path / "g.dmg"
    dmg.write_bytes(b"koly")
    assert spec.check_artifact(dmg) == []


def test_ios_artifact_needs_xcodeproj(tmp_path):
    ipa = tmp_path / "g.ipa"
    ipa.write_bytes(b"x")
    assert get("iOS").check_artifact(ipa) == ["missing g.xcodeproj"]
    (tmp_path / "g.xcodeproj").mkdir()
    assert get("iOS").check_artifact(ipa) == []
