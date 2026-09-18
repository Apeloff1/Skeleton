from __future__ import annotations

import base64
import gzip
import json

import pytest

from core import unbulk


def _packed_json(payload: object) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return unbulk._MAGIC + base64.b64encode(gzip.compress(raw)).decode("ascii")


def test_unpack_rejects_decompression_bomb_over_output_limit(monkeypatch) -> None:
    monkeypatch.setattr(unbulk, "MAX_UNPACKED_BYTES", 64)
    blob = _packed_json({"data": "x" * 4096})

    with pytest.raises(ValueError, match="decompressed payload exceeds size limit"):
        unbulk.unpack(blob)


def test_unpack_rejects_invalid_base64_encoding() -> None:
    with pytest.raises(ValueError, match="invalid packed payload encoding"):
        unbulk.unpack(unbulk._MAGIC + "!!!!")


def test_pack_refuses_payload_larger_than_reader_limit(monkeypatch) -> None:
    monkeypatch.setattr(unbulk, "MAX_UNPACKED_BYTES", 64)

    with pytest.raises(ValueError, match="uncompressed size limit"):
        unbulk.pack({"data": "x" * 4096})


def test_manifest_reader_rejects_gzip_bomb(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(unbulk, "MAX_UNPACKED_BYTES", 64)
    manifest = tmp_path / "manifest.json"
    gz = manifest.with_suffix(".json.gz")
    gz.write_bytes(gzip.compress(json.dumps({"data": "x" * 4096}).encode("utf-8")))

    with pytest.raises(ValueError, match="decompressed manifest exceeds size limit"):
        unbulk.read_manifest_json(manifest)


def test_manifest_writer_refuses_oversized_source(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(unbulk, "MAX_UNPACKED_BYTES", 64)
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b"x" * 65)

    with pytest.raises(ValueError, match="uncompressed size limit"):
        unbulk._gzip_file(manifest)

    assert manifest.exists()
    assert not manifest.with_suffix(".json.gz").exists()


def test_normal_payload_round_trip_still_works() -> None:
    value = {"hello": ["world", 1, True]}
    assert unbulk.unpack(unbulk.pack(value)) == value
