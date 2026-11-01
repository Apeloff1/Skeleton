import json
import os
import struct
import zlib

import pytest

from skeleton.game.build.asset_ingest import (
    AssetImportError, AssetManifest, detect_kind, import_bytes, import_directory, import_files,
)


def png(w=4, h=4, ctype=6):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0" * 8)) + chunk(b"IEND", b""))


def wav(rate=8000, ch=1, frames=800):
    data = b"\0\0" * ch * frames
    fmt = struct.pack("<HHIIHH", 1, ch, rate, rate * 2 * ch, 2 * ch, 16)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + struct.pack("<I", 16)
            + fmt + b"data" + struct.pack("<I", len(data)) + data)


def ogg_vorbis(rate=44100, granule=44100):
    pkt = b"\x01vorbis" + struct.pack("<IBI", 0, 2, rate) + b"\0" * 16
    page = b"OggS\0\x02" + struct.pack("<q", 0) + b"\0" * 12 + bytes([1, len(pkt)]) + pkt
    last = b"OggS\0\x04" + struct.pack("<q", granule) + b"\0" * 12 + b"\x01\x00"
    return page + last


OBJ = b"mtllib cube.mtl\no cube\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 2\nusemtl stone\nf 1 2 3 4\n"
GLTF = json.dumps({"asset": {"version": "2.0"}, "meshes": [{"primitives": [
    {"attributes": {"POSITION": 0}, "indices": 1}]}], "accessors": [{}, {}],
    "buffers": [{"uri": "mesh.bin"}]}).encode()


def glb(doc: bytes):
    doc += b" " * (-len(doc) % 4)
    body = struct.pack("<I4s", len(doc), b"JSON") + doc
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def test_detect_kind():
    assert detect_kind("a/b.PNG") == "texture"
    assert detect_kind("m.glb") == "mesh"
    assert detect_kind("s.ogg") == "audio"
    with pytest.raises(AssetImportError):
        detect_kind("notes.txt")


def test_png_metadata():
    a = import_bytes("t.png", png(8, 4))
    assert a.metadata == {"width": 8, "height": 4, "bit_depth": 8, "channels": 4,
                          "has_alpha": True, "power_of_two": True}
    assert a.receipt().source_digest == a.sha256


def test_jpeg_bmp_tga_metadata():
    jpg = b"\xff\xd8\xff\xe0\x00\x04\0\0\xff\xc0\x00\x11\x08" + struct.pack(">HH", 3, 5) + b"\x03" + b"\0" * 9
    assert import_bytes("a.jpeg", jpg).metadata["width"] == 5
    bmp = b"BM" + b"\0" * 16 + struct.pack("<ii", 2, -3) + b"\0\0" + struct.pack("<H", 32)
    assert import_bytes("b.bmp", bmp).metadata == {"width": 2, "height": 3, "bit_depth": 32,
                                                   "has_alpha": True, "power_of_two": False}
    tga = bytes([0, 0, 2]) + b"\0" * 9 + struct.pack("<HH", 16, 16) + bytes([24, 0])
    assert import_bytes("c.tga", tga).metadata["power_of_two"] is True


@pytest.mark.parametrize("data", [b"\x89PNG\r\n\x1a\n" + b"\0" * 30, png()[:-12], png(0, 4)])
def test_broken_png(data):
    with pytest.raises(AssetImportError):
        import_bytes("t.png", data)


def test_obj_metadata_and_bad_index():
    m = import_bytes("m.obj", OBJ).metadata
    assert (m["vertices"], m["faces"], m["triangles"]) == (4, 1, 2)
    assert m["bounds"] == {"min": [0, 0, 0], "max": [1, 1, 2]}
    assert m["materials"] == ["stone"] and m["external_refs"] == ["cube.mtl"]
    with pytest.raises(AssetImportError, match="out of range"):
        import_bytes("m.obj", b"v 0 0 0\nv 1 0 0\nv 1 1 0\nf 1 2 9\n")
    with pytest.raises(AssetImportError, match="malformed"):
        import_bytes("m.obj", b"v 0 x 0\n")


def test_gltf_and_glb():
    assert import_bytes("m.gltf", GLTF).metadata["primitives"] == 1
    assert import_bytes("m.glb", glb(GLTF)).metadata["external_refs"] == ["mesh.bin"]
    with pytest.raises(AssetImportError, match="length"):
        import_bytes("m.glb", glb(GLTF)[:-4])
    bad = json.dumps({"asset": {"version": "2.0"}, "meshes": [{"primitives": [
        {"attributes": {"POSITION": 3}}]}], "accessors": []}).encode()
    with pytest.raises(AssetImportError, match="accessor"):
        import_bytes("m.gltf", bad)


def test_audio_metadata():
    w = import_bytes("s.wav", wav(8000, 2, 400)).metadata
    assert w == {"codec": "pcm", "channels": 2, "sample_rate": 8000, "bits_per_sample": 16,
                 "frames": 400, "duration_s": 0.05}
    o = import_bytes("s.ogg", ogg_vorbis()).metadata
    assert o == {"codec": "vorbis", "channels": 2, "sample_rate": 44100, "duration_s": 1.0}
    with pytest.raises(AssetImportError, match="truncated"):
        import_bytes("s.wav", wav()[:-100])


def test_manifest_dedup_and_roundtrip():
    m = AssetManifest()
    assert m.add(import_bytes("z/hero.png", png())) is True
    assert m.add(import_bytes("a/hero_copy.png", png())) is False
    assert m.add(import_bytes("music.wav", wav())) is True
    assert m.duplicates() == {"a/hero_copy.png": ["z/hero.png"]}
    assert m.resolve("z/hero.png").address.startswith("ca://game-assets/sha256/")
    again = AssetManifest.from_json(m.to_json())
    assert again.to_json() == m.to_json()
    tampered = json.loads(m.to_json())
    tampered["entries"][0]["size"] = 1
    with pytest.raises(AssetImportError, match="digest"):
        AssetManifest.from_json(json.dumps(tampered))


def test_manifest_digest_is_order_independent():
    a, b = AssetManifest(), AssetManifest()
    x, y = import_bytes("x.png", png()), import_bytes("y.wav", wav())
    a.add(x), a.add(y)
    b.add(y), b.add(x)
    assert a.to_dict()["digest"] == b.to_dict()["digest"]


def test_pipeline_reports_missing_broken_unsafe(tmp_path):
    (tmp_path / "tex").mkdir()
    (tmp_path / "tex" / "a.png").write_bytes(png())
    (tmp_path / "tex" / "b.png").write_bytes(png())
    (tmp_path / "bad.wav").write_bytes(b"RIFF....WAVE")
    (tmp_path / "cube.obj").write_bytes(OBJ)
    (tmp_path / "notes.txt").write_text("x")
    r = import_files(tmp_path, ["tex/a.png", "tex/b.png", "bad.wav", "gone.ogg", "../x.png",
                                "notes.txt", "cube.obj"])
    codes = {(i.path, i.code) for i in r.issues}
    assert codes == {("bad.wav", "broken"), ("gone.ogg", "missing"), ("../x.png", "unsafe"),
                     ("notes.txt", "unsupported"), ("cube.obj", "missing_reference")}
    assert r.imported == ["cube.obj", "tex/a.png"] and r.duplicates == ["tex/b.png"]
    assert not r.ok


def test_import_directory_resolves_sidecars_and_skips_symlinks(tmp_path):
    (tmp_path / "cube.obj").write_bytes(OBJ)
    (tmp_path / "cube.mtl").write_text("newmtl stone\n")
    (tmp_path / "m.gltf").write_bytes(GLTF)
    (tmp_path / "mesh.bin").write_bytes(b"\0" * 8)
    (tmp_path / "link.png").symlink_to(tmp_path / "cube.obj")
    r = import_directory(tmp_path)
    assert r.ok, r.issues
    assert sorted(e.kind for e in r.manifest.entries) == ["mesh", "mesh"]


def test_descriptor_import_rejects_intermediate_symlink_and_external_reference(tmp_path):
    from skeleton.game.build.asset_ingest.pipeline import import_files
    source = tmp_path / "safe"
    source.mkdir()
    (source / "asset.png").write_bytes(png())
    (tmp_path / "link").symlink_to(source, target_is_directory=True)
    report = import_files(tmp_path, ["link/asset.png"])
    assert not report.ok
    assert report.imported == []
    assert any(issue.code == "unsafe" for issue in report.issues)
    (tmp_path / "mesh.obj").write_bytes(b"mtllib link/missing.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    report = import_files(tmp_path, ["mesh.obj"])
    assert any(issue.code == "missing_reference" for issue in report.issues)


def test_descriptor_import_rejects_parent_traversal_and_symlink_root(tmp_path):
    from skeleton.game.build.asset_ingest.pipeline import import_files
    root = tmp_path / "assets"
    root.mkdir()
    (root / "good.png").write_bytes(png())
    assert import_files(root, ["../good.png"]).issues[0].code == "unsafe"
    link = tmp_path / "root_link"
    link.symlink_to(root, target_is_directory=True)
    report = import_files(link, ["good.png"])
    assert report.imported == []
    assert report.issues[0].code == "unsafe"


def test_directory_scan_is_bounded_and_skips_symlinked_tree(tmp_path, monkeypatch):
    from skeleton.game.build.asset_ingest import pipeline
    source = tmp_path / "assets"
    source.mkdir()
    (source / "a.png").write_bytes(png())
    (source / "b.png").write_bytes(png())
    (tmp_path / "shortcut").symlink_to(source, target_is_directory=True)
    monkeypatch.setattr(pipeline, "MAX_TREE_ENTRIES", 1)
    report = pipeline.import_directory(tmp_path)
    assert not report.ok
    assert any("tree entries exceed bound" in issue.detail for issue in report.issues)


def test_directory_root_replacement_cannot_switch_imported_bytes(tmp_path, monkeypatch):
    from skeleton.game.build.asset_ingest import pipeline
    root = tmp_path / "assets"
    root.mkdir()
    (root / "a.png").write_bytes(png())
    original_scandir = pipeline.os.scandir
    swapped = [False]

    def replace_root_after_open(fd):
        if not swapped[0]:
            swapped[0] = True
            root.rename(tmp_path / "original")
            root.mkdir()
            (root / "a.png").write_bytes(b"forged replacement")
        return original_scandir(fd)

    monkeypatch.setattr(pipeline.os, "scandir", replace_root_after_open)
    report = pipeline.import_directory(root)
    assert report.ok, report.issues
    assert report.imported == ["a.png"]
    assert report.manifest.resolve("a.png").size == len(png())


def test_manifest_duplicate_kind_rejection_is_transactional():
    from dataclasses import replace
    m = AssetManifest()
    original = import_bytes("z/hero.png", png())
    assert m.add(original)
    before = m.to_json()
    with pytest.raises(AssetImportError, match="incompatible metadata"):
        m.add(replace(original, path="a/forged.obj", kind="mesh", format="obj"))
    assert m.to_json() == before
    with pytest.raises(AssetImportError, match="not in manifest"):
        m.resolve("a/forged.obj")


def test_manifest_canonical_alias_receipt_tracks_canonical_source():
    m = AssetManifest()
    m.add(import_bytes("z/hero.png", png()))
    canonical = import_bytes("a/hero.png", png())
    assert not m.add(canonical)
    assert m.resolve("z/hero.png").receipt_digest == canonical.receipt().digest
    assert AssetManifest.from_json(m.to_json()).to_json() == m.to_json()


def test_manifest_rejects_collision_summary_and_receipt_rewrites():
    from skeleton.game.build.flgb_build_runtime import dig
    m = AssetManifest()
    m.add(import_bytes("a/hero.png", png()))
    m.add(import_bytes("music.wav", wav()))
    forged = json.loads(m.to_json())
    forged["entries"][0]["aliases"].append("music.wav")
    forged["digest"] = dig(forged["entries"])
    with pytest.raises(AssetImportError, match="collide"):
        AssetManifest.from_json(json.dumps(forged))
    forged = json.loads(m.to_json())
    forged["paths"] += 1
    with pytest.raises(AssetImportError, match="summary"):
        AssetManifest.from_json(json.dumps(forged))
    forged = json.loads(m.to_json())
    forged["entries"][0]["receipt_digest"] = "0" * 64
    forged["digest"] = dig(forged["entries"])
    with pytest.raises(AssetImportError, match="receipt identity"):
        AssetManifest.from_json(json.dumps(forged))


def test_manifest_rejects_nul_and_windows_separator_paths():
    from dataclasses import replace
    original = import_bytes("hero.png", png())
    m = AssetManifest()
    for bad in ("folder" + chr(92) + "hero.png", "folder" + chr(0) + "hero.png", "../hero.png"):
        with pytest.raises(AssetImportError, match="invalid manifest asset path"):
            m.add(replace(original, path=bad))
    assert m.to_dict()["paths"] == 0


def test_same_size_in_place_mutation_with_restored_mtime_is_rejected(tmp_path, monkeypatch):
    from skeleton.game.build.asset_ingest import pipeline

    asset = tmp_path / "hero.png"
    asset.write_bytes(png())
    original_read = pipeline.os.read
    changed = [False]

    def rewrite_after_read(fd, size):
        chunk = original_read(fd, size)
        if chunk and not changed[0]:
            changed[0] = True
            before = os.fstat(fd)
            with asset.open("r+b") as writer:
                writer.seek(40)
                writer.write(b"X")
                writer.flush()
                os.fsync(writer.fileno())
            os.utime(asset, ns=(before.st_atime_ns, before.st_mtime_ns))
        return chunk

    monkeypatch.setattr(pipeline.os, "read", rewrite_after_read)
    report = pipeline.import_files(tmp_path, ["hero.png"])
    assert changed[0]
    assert not report.ok
    assert any(issue.code == "broken" and "changed during descriptor read" in issue.detail
               for issue in report.issues)
    assert report.imported == []
