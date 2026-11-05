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


def test_png_chunk_integrity_and_order_fail_closed():
    valid = png()
    crc_corrupt = bytearray(valid)
    crc_corrupt[29] ^= 1  # First IHDR CRC byte; dimensions remain unchanged.
    idat_offset = valid.index(b"IDAT") - 4
    idat_length = struct.unpack_from(">I", valid, idat_offset)[0]
    without_idat = valid[:idat_offset] + valid[idat_offset + 12 + idat_length:]
    # Valid-looking terminal marker must not hide arbitrary trailing bytes.
    for invalid in (bytes(crc_corrupt), without_idat, valid + b"hidden",
                    valid[:-1], valid[:8] + b"\xff\xff\xff\xff" + valid[12:]):
        with pytest.raises(AssetImportError):
            import_bytes("corrupt.png", invalid)
    assert import_bytes("good.png", valid).metadata["channels"] == 4


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



def test_gltf_rejects_ambiguous_json_nonfinite_and_boolean_accessors():
    hostile = (
        b'{"asset":{"version":"2.0"},"asset":{"version":"2.0"}}',
        b'{"asset":{"version":"2.0"},"extras":{"bad":NaN}}',
        b'{"asset":{"version":"2.0"},"accessors":[{}],"meshes":'
        b'[{"primitives":[{"attributes":{"POSITION":true}}]}]}',
        b'{"asset":{"version":"2.0"},"meshes":[{"primitives":'
        b'[{"attributes":{"POSITION":0,"POSITION":1}}]}],"accessors":[{},{}]}',
    )
    for document in hostile:
        for extension, payload in ((".gltf", document), (".glb", glb(document))):
            with pytest.raises(AssetImportError):
                import_bytes("hostile" + extension, payload)


def test_gltf_rejects_nonfinite_exponents_and_oversized_number_tokens():
    # JSON syntax permits huge exponents even when Python's float becomes inf.
    # A syntactically valid document must not silently admit unrepresentable
    # numbers in extensions or extras ignored by the metadata extractor.
    hostile = (b"1e10000", b"-1e10000", b"9" * 129,
               b"0." + b"1" * 130)
    for number in hostile:
        document = b'{"asset":{"version":"2.0"},"extras":{"value":' + number + b'}}'
        for extension, payload in ((".gltf", document), (".glb", glb(document))):
            with pytest.raises(AssetImportError, match="nonfinite|exceeds bound"):
                import_bytes("hostile" + extension, payload)

    finite = b'{"asset":{"version":"2.0"},"extras":{"value":-1.25e4,"count":123}}'
    assert import_bytes("finite.gltf", finite).metadata["meshes"] == 0


def test_glb_valid_bin_chunk_and_rejects_forged_framing():
    valid = glb(GLTF)
    bin_chunk = struct.pack("<I4s", 4, b"BIN\x00") + b"\x00" * 4
    with_bin = valid[:8] + struct.pack("<I", len(valid) + len(bin_chunk)) + valid[12:] + bin_chunk
    assert import_bytes("valid.glb", with_bin).metadata["primitives"] == 1

    def append_chunk(original: bytes, chunk: bytes) -> bytes:
        return (original[:8] + struct.pack("<I", len(original) + len(chunk))
                + original[12:] + chunk)

    malformed = (
        append_chunk(valid, b"\x00" * 4),
        append_chunk(valid, struct.pack("<I4s", 4, b"JUNK") + b"abcd"),
        append_chunk(valid, valid[12:]),
        append_chunk(valid, struct.pack("<I4s", 8, b"BIN\x00") + b"abcd"),
        valid[:12] + bin_chunk + valid[12:],
        valid[:8] + struct.pack("<I", len(valid) + 1) + valid[12:] + b"X",
    )
    for payload in malformed:
        with pytest.raises(AssetImportError):
            import_bytes("forged.glb", payload)



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
    # A mixed trusted/invalid package must never expose a partial manifest.
    # Rejected batches preserve diagnostic issues but discard all imported state.
    assert not r.ok
    assert r.imported == [] and r.duplicates == []
    assert r.manifest.entries == []
    assert r.manifest.to_dict()["paths"] == 0


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
    for bad in ("folder" + chr(92) + "hero.png", "folder" + chr(0) + "hero.png",
                "../hero.png", "folder/line\nfeed.png", "folder/tab\tasset.png",
                "folder/bidi\u202easset.png", "folder/paragraph\u2029asset.png"):
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


def test_root_ancestor_symlink_is_rejected(tmp_path):
    """O_NOFOLLOW on the final root component is not enough."""
    source = tmp_path / "source"
    nested = source / "assets"
    nested.mkdir(parents=True)
    (nested / "hero.png").write_bytes(png())
    (tmp_path / "shortcut").symlink_to(source, target_is_directory=True)
    report = import_files(tmp_path / "shortcut" / "assets", ["hero.png"])
    assert not report.ok
    assert not report.imported
    assert report.issues[0].code == "unsafe"


def test_root_parent_replacement_keeps_original_directory_fd(tmp_path, monkeypatch):
    """A replaced parent pathname cannot redirect an already opened dirfd."""
    from skeleton.game.build.asset_ingest import pipeline

    parent = tmp_path / "parent"
    root = parent / "assets"
    root.mkdir(parents=True)
    original_bytes = png()
    (root / "hero.png").write_bytes(original_bytes)
    outside = tmp_path / "outside"
    (outside / "assets").mkdir(parents=True)
    (outside / "assets" / "hero.png").write_bytes(b"forged source")
    original_open = pipeline.os.open
    swapped = [False]

    def swap_ancestor(name, flags, *args, **kwargs):
        if name == "assets" and kwargs.get("dir_fd") is not None and not swapped[0]:
            swapped[0] = True
            parent.rename(tmp_path / "retired")
            parent.symlink_to(outside, target_is_directory=True)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(pipeline.os, "open", swap_ancestor)
    report = pipeline.import_files(root, ["hero.png"])
    assert swapped[0]
    assert report.ok, report.issues
    assert report.manifest.resolve("hero.png").size == len(original_bytes)


def test_leaf_swap_to_symlink_fails_closed(tmp_path, monkeypatch):
    from skeleton.game.build.asset_ingest import pipeline

    root = tmp_path / "assets"
    root.mkdir()
    target = tmp_path / "outside.png"
    target.write_bytes(png())
    leaf = root / "hero.png"
    leaf.write_bytes(png())
    original_open = pipeline.os.open
    swapped = [False]

    def swap_leaf(name, flags, *args, **kwargs):
        if name == "hero.png" and kwargs.get("dir_fd") is not None and not swapped[0]:
            swapped[0] = True
            leaf.unlink()
            leaf.symlink_to(target)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(pipeline.os, "open", swap_leaf)
    report = pipeline.import_files(root, ["hero.png"])
    assert swapped[0]
    assert not report.ok
    assert report.imported == []
    assert any(issue.code == "unsafe" for issue in report.issues)


def test_sparse_oversize_and_aggregate_volume_limits(tmp_path, monkeypatch):
    from skeleton.game.build.asset_ingest import pipeline
    from skeleton.game.build.asset_ingest.importers import MAX_ASSET_BYTES

    oversized = tmp_path / "oversized.png"
    with oversized.open("wb") as dest:
        dest.truncate(MAX_ASSET_BYTES + 1)
    report = pipeline.import_files(tmp_path, ["oversized.png"])
    assert not report.ok and not report.imported
    assert any("exceeds size limit" in issue.detail for issue in report.issues)

    (tmp_path / "a.png").write_bytes(png(4, 4))
    (tmp_path / "b.png").write_bytes(png(8, 4))
    monkeypatch.setattr(pipeline, "MAX_IMPORT_TOTAL_BYTES", len(png(4, 4)) + 1)
    report = pipeline.import_files(tmp_path, ["a.png", "b.png"])
    assert not report.ok
    assert any("aggregate asset bytes exceed bound" in issue.detail for issue in report.issues)
    monkeypatch.setattr(pipeline, "MAX_IMPORT_FILES", 1)
    report = pipeline.import_files(tmp_path, ["a.png", "b.png"])
    assert not report.ok
    assert any("file count exceeds bound" in issue.detail for issue in report.issues)


def test_global_input_limits_never_publish_partial_manifest(tmp_path, monkeypatch):
    """An input-volume failure must not leave apparently usable partial assets."""
    from skeleton.game.build.asset_ingest import pipeline

    (tmp_path / "a.png").write_bytes(png(4, 4))
    (tmp_path / "b.png").write_bytes(png(8, 4))

    monkeypatch.setattr(pipeline, "MAX_IMPORT_FILES", 1)
    report = pipeline.import_files(tmp_path, ["a.png", "b.png"])
    assert not report.ok
    assert report.imported == [] and report.duplicates == []
    assert report.manifest.entries == []
    assert any("file count exceeds bound" in issue.detail for issue in report.issues)

    monkeypatch.setattr(pipeline, "MAX_IMPORT_FILES", 8192)
    monkeypatch.setattr(pipeline, "MAX_IMPORT_TOTAL_BYTES", len(png(4, 4)) + 1)
    report = pipeline.import_files(tmp_path, ["a.png", "b.png"])
    assert not report.ok
    assert report.imported == [] and report.duplicates == []
    assert report.manifest.entries == []
    assert any("aggregate asset bytes exceed bound" in issue.detail for issue in report.issues)


def test_directory_tree_limit_never_publishes_partial_manifest(tmp_path, monkeypatch):
    from skeleton.game.build.asset_ingest import pipeline

    (tmp_path / "a.png").write_bytes(png(4, 4))
    (tmp_path / "b.png").write_bytes(png(8, 4))
    monkeypatch.setattr(pipeline, "MAX_TREE_ENTRIES", 1)
    report = pipeline.import_directory(tmp_path)
    assert not report.ok
    assert report.imported == [] and report.manifest.entries == []
    assert any("tree entries exceed bound" in issue.detail for issue in report.issues)


def test_directory_rejects_regular_leaf_replacement_after_scan(tmp_path, monkeypatch):
    """Scanning a pathname must not authorize opening a different inode."""
    from skeleton.game.build.asset_ingest import pipeline

    root = tmp_path / "assets"
    root.mkdir()
    asset = root / "hero.png"
    asset.write_bytes(png(4, 4))
    original_import = pipeline._import_from_fd
    replaced = [False]

    def swap_after_scan(fd, paths, **kwargs):
        if not replaced[0]:
            replaced[0] = True
            asset.rename(root / "retired.png")
            asset.write_bytes(png(8, 4))
        return original_import(fd, paths, **kwargs)

    monkeypatch.setattr(pipeline, "_import_from_fd", swap_after_scan)
    report = pipeline.import_directory(root)
    assert replaced[0]
    assert not report.ok
    assert report.imported == []
    assert any("changed after directory scan" in issue.detail for issue in report.issues)


def test_directory_rejects_parent_subtree_replacement_after_scan(tmp_path, monkeypatch):
    """Each reopened ancestor must match the inode enumerated by scandir."""
    from skeleton.game.build.asset_ingest import pipeline

    root = tmp_path / "assets"
    child = root / "scenes"
    child.mkdir(parents=True)
    (child / "hero.png").write_bytes(png(4, 4))
    original_import = pipeline._import_from_fd

    def swap_after_scan(fd, paths, **kwargs):
        child.rename(root / "retired")
        child.mkdir()
        (child / "hero.png").write_bytes(png(8, 4))
        return original_import(fd, paths, **kwargs)

    monkeypatch.setattr(pipeline, "_import_from_fd", swap_after_scan)
    report = pipeline.import_directory(root)
    assert not report.ok
    assert report.imported == []
    assert any("directory changed after scan" in issue.detail for issue in report.issues)


def test_directory_rejects_sidecar_replacement_after_scan(tmp_path, monkeypatch):
    """An external asset reference must stay bound to its scanned inode."""
    from skeleton.game.build.asset_ingest import pipeline

    root = tmp_path / "assets"
    root.mkdir()
    (root / "mesh.obj").write_bytes(OBJ)
    sidecar = root / "cube.mtl"
    sidecar.write_bytes(b"newmtl stone\n")
    original_import = pipeline._import_from_fd

    def swap_after_scan(fd, paths, **kwargs):
        sidecar.rename(root / "retired.mtl")
        sidecar.write_bytes(b"newmtl different\n")
        return original_import(fd, paths, **kwargs)

    monkeypatch.setattr(pipeline, "_import_from_fd", swap_after_scan)
    report = pipeline.import_directory(root)
    assert not report.ok
    assert any(issue.code == "missing_reference" and "changed after directory scan" in issue.detail
               for issue in report.issues)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO required")
def test_descriptor_leaf_fifo_fails_closed_without_blocking(tmp_path):
    """A hostile leaf must not block open() while waiting for a FIFO writer."""
    from skeleton.game.build.asset_ingest import pipeline

    fifo = tmp_path / "swapped.png"
    os.mkfifo(fifo)
    report = pipeline.import_files(tmp_path, ["swapped.png"])
    assert not report.ok
    assert not report.imported
    assert any(issue.path == "swapped.png" and issue.code == "broken"
               and "not a regular file" in issue.detail for issue in report.issues)


def test_descriptor_import_rejects_invisible_and_control_character_paths(tmp_path):
    """Untrusted filenames must not carry log controls or bidi overrides into manifests."""
    from skeleton.game.build.asset_ingest import pipeline

    for char in ("\n", "\r", "\t", "\x1b", "\x7f", "\x85", "\u202e", "\u2066", "\u2028", "\u2029"):
        name = "asset" + char + ".png"
        report = pipeline.import_files(tmp_path, [name])
        assert not report.ok
        assert report.manifest.entries == []
        assert report.imported == []
        assert any(issue.code == "unsafe" for issue in report.issues)


def test_descriptor_import_rejects_unbounded_external_references_transactionally(tmp_path):
    from skeleton.game.build.asset_ingest import pipeline

    doc = {"asset": {"version": "2.0"},
           "buffers": [{"uri": f"missing_{i}.bin"} for i in range(257)]}
    (tmp_path / "oversized.gltf").write_text(json.dumps(doc))
    for importer in (pipeline.import_files, pipeline.import_directory):
        if importer is pipeline.import_files:
            report = importer(tmp_path, ["oversized.gltf"])
        else:
            report = importer(tmp_path)
        assert not report.ok
        assert not report.manifest.entries
        assert not report.imported
        assert any("external reference count exceeds bound" in issue.detail
                   for issue in report.issues)

def test_directory_unsafe_scan_discards_partial_manifest(tmp_path):
    """A rejected filename cannot leave other scanned assets publishable."""
    (tmp_path / "a.png").write_bytes(png())
    (tmp_path / "bad\nname.png").write_bytes(png(8, 4))
    report = import_directory(tmp_path)
    assert not report.ok
    assert report.imported == [] and report.duplicates == []
    assert report.manifest.entries == []
    assert any(issue.code == "unsafe" for issue in report.issues)


def test_directory_missing_sidecar_discards_partial_manifest(tmp_path):
    """Unresolved external source evidence invalidates the directory snapshot."""
    (tmp_path / "a.png").write_bytes(png())
    (tmp_path / "mesh.obj").write_bytes(OBJ)
    report = import_directory(tmp_path)
    assert not report.ok
    assert report.imported == [] and report.duplicates == []
    assert report.manifest.entries == []
    assert any(issue.code == "missing_reference" for issue in report.issues)

def test_directory_symlink_swap_discards_all_scanned_assets(tmp_path, monkeypatch):
    """A leaf replaced after enumeration cannot publish unrelated assets."""
    from skeleton.game.build.asset_ingest import pipeline

    root = tmp_path / "assets"
    root.mkdir()
    (root / "a.png").write_bytes(png())
    leaf = root / "hero.png"
    leaf.write_bytes(png(8, 4))
    outside = tmp_path / "outside.png"
    outside.write_bytes(png())
    original_import = pipeline._import_from_fd

    def replace_after_scan(fd, paths, **kwargs):
        leaf.unlink()
        leaf.symlink_to(outside)
        return original_import(fd, paths, **kwargs)

    monkeypatch.setattr(pipeline, "_import_from_fd", replace_after_scan)
    report = pipeline.import_directory(root)
    assert not report.ok
    assert report.imported == [] and report.manifest.entries == []
    assert any(issue.code == "unsafe" for issue in report.issues)


def test_duplicate_mesh_alias_requires_each_source_relative_sidecar(tmp_path):
    """Content deduplication cannot hide a missing dependency of an alias."""
    for directory in ("a", "z"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "mesh.obj").write_bytes(OBJ)
    (tmp_path / "a" / "cube.mtl").write_text("newmtl stone\n")
    paths = ["a/mesh.obj", "z/mesh.obj"]

    report = import_files(tmp_path, paths)
    assert not report.ok
    assert any(issue.path == "z/mesh.obj" and issue.code == "missing_reference"
               for issue in report.issues)

    scanned = import_directory(tmp_path)
    assert not scanned.ok
    assert scanned.manifest.entries == []
    assert any(issue.path == "z/mesh.obj" and issue.code == "missing_reference"
               for issue in scanned.issues)

    (tmp_path / "z" / "cube.mtl").write_text("newmtl stone\n")
    report = import_files(tmp_path, paths)
    assert report.ok, report.issues
    assert report.duplicates == ["z/mesh.obj"]
    assert len(report.manifest.entries) == 1
    assert import_directory(tmp_path).ok


def test_duplicate_mesh_alias_symlink_sidecar_is_not_trusted(tmp_path):
    """A valid canonical sidecar does not authorize an alias symlink."""
    for directory in ("a", "z"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "mesh.obj").write_bytes(OBJ)
    sidecar = tmp_path / "a" / "cube.mtl"
    sidecar.write_text("newmtl stone\n")
    (tmp_path / "z" / "cube.mtl").symlink_to(sidecar)
    report = import_files(tmp_path, ["a/mesh.obj", "z/mesh.obj"])
    assert not report.ok
    assert any(issue.path == "z/mesh.obj" and issue.code == "missing_reference"
               for issue in report.issues)
    scanned = import_directory(tmp_path)
    assert not scanned.ok and scanned.manifest.entries == []


def test_duplicate_mesh_alias_reference_budget_is_global(tmp_path, monkeypatch):
    """An alias multiplies source references and consumes the same global cap."""
    from skeleton.game.build.asset_ingest import pipeline

    for directory in ("a", "z"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "mesh.obj").write_bytes(OBJ)
        (tmp_path / directory / "cube.mtl").write_text("newmtl stone\n")
    monkeypatch.setattr(pipeline, "MAX_TOTAL_EXTERNAL_REFS", 1)
    report = pipeline.import_files(tmp_path, ["a/mesh.obj", "z/mesh.obj"])
    assert not report.ok
    assert report.manifest.entries == []
    assert report.imported == []
    assert any("external reference count exceeds bound" in issue.detail
               for issue in report.issues)


def test_explicit_batch_missing_sidecar_never_publishes_valid_asset(tmp_path):
    """A missing dependency must invalidate even previously imported assets."""
    (tmp_path / "a.png").write_bytes(png())
    (tmp_path / "mesh.obj").write_bytes(OBJ)
    report = import_files(tmp_path, ["a.png", "mesh.obj"])
    assert not report.ok
    assert any(issue.code == "missing_reference" for issue in report.issues)
    assert report.manifest.entries == []
    assert report.imported == [] and report.duplicates == []


def test_explicit_batch_invalid_or_missing_path_is_transactional(tmp_path):
    """Reject mixed batches rather than returning a publishable partial manifest."""
    (tmp_path / "a.png").write_bytes(png())
    for invalid in ("../outside.png", "missing.png", "notes.txt"):
        report = import_files(tmp_path, ["a.png", invalid])
        assert not report.ok
        assert report.issues
        assert report.manifest.entries == []
        assert report.imported == [] and report.duplicates == []


def test_external_sidecar_aggregate_volume_is_bounded_and_transactional(tmp_path, monkeypatch):
    """Unimported glTF sidecars still consume bounded source-package volume."""
    from skeleton.game.build.asset_ingest import pipeline

    document = {"asset": {"version": "2.0"},
                "buffers": [{"uri": "a.bin"}, {"uri": "b.bin"}]}
    (tmp_path / "scene.gltf").write_text(json.dumps(document))
    for name in ("a.bin", "b.bin"):
        with (tmp_path / name).open("wb") as sidecar:
            sidecar.truncate(8)

    monkeypatch.setattr(pipeline, "MAX_EXTERNAL_TOTAL_BYTES", 15)
    explicit = pipeline.import_files(tmp_path, ["scene.gltf"])
    scanned = pipeline.import_directory(tmp_path)
    for report in (explicit, scanned):
        assert not report.ok
        assert report.imported == [] and report.manifest.entries == []
        assert any("aggregate external reference bytes exceed bound" in issue.detail
                   for issue in report.issues)

    monkeypatch.setattr(pipeline, "MAX_EXTERNAL_TOTAL_BYTES", 16)
    assert pipeline.import_files(tmp_path, ["scene.gltf"]).ok
    assert pipeline.import_directory(tmp_path).ok


def test_jpeg_rejects_forged_frame_inside_malformed_segment():
    # The old scanner could accept a forged SOF outside a valid segment.
    sof = (b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", 3, 5)
           + b"\x03" + b"\x00" * 9)
    valid = b"\xff\xd8\xff\xe0\x00\x04\x00\x00" + sof
    assert import_bytes("valid.jpg", valid).metadata["width"] == 5
    invalid = (
        b"\xff\xd8\xff\xe0\x00\x01" + sof,  # invalid short segment
        b"\xff\xd8\xff\xe0\x00\x20\x00\x00" + sof,  # segment overruns source
        b"\xff\xd8\xff\xd9" + sof,  # terminal marker before frame
        b"\xff\xd8" + sof[:3] + b"\x07" + sof[4:],  # frame length shorter than header
        b"\xff\xd8" + sof[:9] + b"\x00" + sof[10:],  # zero channel count
    )
    for forged in invalid:
        with pytest.raises(AssetImportError):
            import_bytes("forged.jpg", forged)


@pytest.mark.parametrize("extension", [".gltf", ".glb"])
def test_deeply_nested_gltf_json_fails_closed_without_partial_manifest(tmp_path, extension):
    """Hostile JSON nesting must become a reported asset error, not a crash."""
    nested = b"[" * 2048 + b"0" + b"]" * 2048
    if extension == ".glb":
        payload = (b"glTF" + struct.pack("<II", 2, 20 + len(nested))
                   + struct.pack("<I4s", len(nested), b"JSON") + nested)
    else:
        payload = nested

    with pytest.raises(AssetImportError):
        import_bytes("hostile" + extension, payload)

    (tmp_path / ("hostile" + extension)).write_bytes(payload)
    (tmp_path / "valid.png").write_bytes(png())
    report = import_files(tmp_path, ["valid.png", "hostile" + extension])
    assert not report.ok
    assert report.manifest.entries == []
    assert report.imported == [] and report.duplicates == []
    assert any(issue.path == "hostile" + extension and issue.code == "broken"
               for issue in report.issues)


def test_manifest_rejects_duplicate_json_keys_at_all_levels():
    """A signed-looking digest must not hide ambiguous last-wins JSON keys."""
    manifest = AssetManifest()
    manifest.add(import_bytes("hero.png", png()))
    canonical = manifest.to_json()
    assert AssetManifest.from_json(canonical).to_json() == canonical
    root_duplicate = canonical.replace('"schema":', '"schema":"forged","schema":', 1)
    nested_duplicate = canonical.replace('"metadata":{', '"metadata":{"shadow":1,"shadow":2,', 1)
    for hostile in (root_duplicate, nested_duplicate):
        with pytest.raises(AssetImportError, match="duplicate JSON key"):
            AssetManifest.from_json(hostile)


def test_manifest_rejects_nonfinite_json_and_invalid_unicode():
    manifest = AssetManifest()
    manifest.add(import_bytes("hero.png", png()))
    canonical = manifest.to_json()
    for token in ("NaN", "Infinity", "-Infinity"):
        hostile = canonical.replace('"paths":1', '"paths":' + token, 1)
        assert hostile != canonical
        with pytest.raises(AssetImportError, match="nonfinite JSON"):
            AssetManifest.from_json(hostile)
    with pytest.raises(AssetImportError, match="utf-8"):
        AssetManifest.from_json('"' + chr(0xD800) + '"')


def test_manifest_rejects_excessive_json_nesting_and_nodes(monkeypatch):
    from skeleton.game.build.asset_ingest import manifest as manifest_module
    deep = '{"nested":' * 70 + '0' + '}' * 70
    with pytest.raises(AssetImportError, match="structure exceeds bound"):
        AssetManifest.from_json(deep)
    monkeypatch.setattr(manifest_module, "MAX_MANIFEST_JSON_NODES", 4)
    with pytest.raises(AssetImportError, match="structure exceeds bound"):
        AssetManifest.from_json('{"schema":"skeleton.game.asset_manifest.v1","entries":[1,2,3]}')

def test_path_iterator_failure_never_publishes_partial_assets(tmp_path):
    (tmp_path / "good.png").write_bytes(png())

    def hostile_paths():
        yield "good.png"
        raise RuntimeError("untrusted path producer failed")

    report = import_files(tmp_path, hostile_paths())
    assert not report.ok
    assert report.imported == [] and report.duplicates == []
    assert report.manifest.entries == []
    assert [(issue.path, issue.code, issue.detail) for issue in report.issues] == [
        (".", "unsafe", "asset path iterator failed")
    ]


def test_hostile_path_objects_never_run_user_defined_string_hooks(tmp_path):
    (tmp_path / "good.png").write_bytes(png())

    class HostilePath(str):
        def __str__(self):
            raise AssertionError("hostile __str__ executed")

        def __hash__(self):
            raise AssertionError("hostile __hash__ executed")

        def __lt__(self, other):
            raise AssertionError("hostile __lt__ executed")

    report = import_files(tmp_path, ["good.png", HostilePath("good.png"), object()])
    assert not report.ok
    assert report.imported == [] and report.duplicates == []
    assert report.manifest.entries == []
    assert len(report.issues) == 2
    assert all(issue.path == "<non-text>" and issue.code == "unsafe" for issue in report.issues)


def test_wav_strict_riff_framing_rejects_hidden_or_ambiguous_payloads():
    """Malformed RIFF envelopes cannot produce trusted source metadata."""
    good = wav(rate=8000, ch=2, frames=4)
    assert import_bytes("good.wav", good).metadata["frames"] == 4

    def riff(chunks):
        return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks

    fmt_chunk, data_chunk = good[12:36], good[36:]
    extra_fmt = riff(fmt_chunk + fmt_chunk + data_chunk)
    extra_data = riff(fmt_chunk + data_chunk + data_chunk)
    unknown_truncated = riff(fmt_chunk + data_chunk + b"JUNK" + struct.pack("<I", 9) + b"x")
    missing_padding = riff(fmt_chunk + data_chunk + b"JUNK" + struct.pack("<I", 1) + b"x")
    misaligned = riff(fmt_chunk + b"data" + struct.pack("<I", 3) + b"abc" + b"\0")
    malformed_pcm = bytearray(fmt_chunk)
    struct.pack_into("<I", malformed_pcm, 16, 123)  # Incorrect byte rate.
    invalid = (
        good[:-1], good + b"hidden", good[:4] + struct.pack("<I", 0) + good[8:],
        extra_fmt, extra_data, unknown_truncated, missing_padding, misaligned,
        riff(bytes(malformed_pcm) + data_chunk),
    )
    for payload in invalid:
        with pytest.raises(AssetImportError):
            import_bytes("hostile.wav", payload)


def test_wav_chunk_iteration_is_bounded():
    """A hostile chain of zero-length chunks must not monopolize parsing."""
    fmt = wav(rate=8000, ch=1, frames=1)[12:36]
    data = b"data" + struct.pack("<I", 2) + b"\0\0"
    junk = (b"JUNK" + struct.pack("<I", 0)) * 8193
    body = fmt + junk + data
    payload = b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body
    with pytest.raises(AssetImportError, match="chunk count exceeds bound"):
        import_bytes("hostile.wav", payload)


@pytest.mark.skipif(not (hasattr(os, "link") and os.name == "posix"),
                    reason="POSIX hard links required")
def test_descriptor_import_rejects_hard_linked_sources_and_sidecars(tmp_path):
    """An in-root hard link must not smuggle an outside inode into an asset manifest."""
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "safe.png").write_bytes(png())
    outside_asset = outside / "private.png"
    outside_asset.write_bytes(png(8, 4))
    os.link(outside_asset, root / "alias.png")

    explicit = import_files(root, ["safe.png", "alias.png"])
    scanned = import_directory(root)
    for report in (explicit, scanned):
        assert not report.ok
        assert report.imported == [] and report.duplicates == []
        assert report.manifest.entries == []
        assert any(issue.path == "alias.png" and issue.code == "unsafe"
                   and "hard-linked" in issue.detail for issue in report.issues)

    (root / "alias.png").unlink()
    (root / "mesh.obj").write_bytes(OBJ)
    outside_sidecar = outside / "cube.mtl"
    outside_sidecar.write_text("newmtl stone\\n")
    os.link(outside_sidecar, root / "cube.mtl")
    explicit = import_files(root, ["safe.png", "mesh.obj"])
    scanned = import_directory(root)
    for report in (explicit, scanned):
        assert not report.ok
        assert report.imported == [] and report.duplicates == []
        assert report.manifest.entries == []
        assert any(issue.path == "mesh.obj" and issue.code == "missing_reference"
                   and "hard-linked" in issue.detail for issue in report.issues)


def test_mutable_asset_buffer_cannot_change_receipt_after_parse(monkeypatch):
    """Parser metadata and digest must describe the same immutable input."""
    from hashlib import sha256
    from skeleton.game.build.asset_ingest import importers as importer_module

    caller_buffer = bytearray(b"original asset bytes")
    expected = bytes(caller_buffer)
    seen = []

    def parsing_hook(payload):
        assert type(payload) is bytes
        seen.append(payload)
        caller_buffer[:] = b"tampered after parsing"
        return {"verified": True}

    monkeypatch.setitem(importer_module._PARSERS, ".png", parsing_hook)
    result = importer_module.import_bytes("mutable.png", caller_buffer)
    assert seen == [expected]
    assert result.size == len(expected)
    assert result.sha256 == sha256(expected).hexdigest()
    assert result.metadata == {"verified": True}
    assert bytes(caller_buffer) != expected
