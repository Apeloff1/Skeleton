"""Regression suite: hostile collection names and symlinked vault shards."""
from __future__ import annotations

import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.vault_secure_fs import VaultPathError
from services import vault_loader


class _PassthroughZstd:
    """Exercise disk and scan custody without requiring zstd in the fixture."""

    def stream_reader(self, source):
        return nullcontext(source)


@pytest.fixture
def vault(monkeypatch, tmp_path: Path):
    directory = tmp_path / "vault"
    directory.mkdir()
    monkeypatch.setattr(vault_loader, "VAULT_DIR", directory)
    monkeypatch.setattr(vault_loader, "_HAS_ZSTD", True)
    monkeypatch.setattr(
        vault_loader,
        "zstd",
        SimpleNamespace(ZstdDecompressor=lambda: _PassthroughZstd()),
    )
    return directory


@pytest.mark.parametrize("bad", [
    "../etc/passwd", "../../data", "/etc/passwd", r"..\\private", "",
    "foo/bar", "foo\\bar", "é", "dot.", "x" * 97,
])
def test_collection_names_cannot_select_arbitrary_paths(vault, bad):
    with pytest.raises(ValueError):
        vault_loader.query_collection(bad)
    with pytest.raises(ValueError):
        vault_loader._validate_collection(bad)


@pytest.mark.parametrize("bad_limit", [-1, 101, True, False, 1.25, "5"])
def test_vault_reads_have_strict_limit_contract(vault, bad_limit):
    with pytest.raises(ValueError):
        vault_loader.query_collection("valid", limit=bad_limit)


def test_vault_reads_only_verified_regular_shard(vault):
    payload = b'{"hello":"world"}\n{"count":2}\n'
    (vault / "safe.jsonl.zst").write_bytes(payload)
    assert vault_loader.query_collection("safe") == [
        {"hello": "world"}, {"count": 2},
    ]
    assert vault_loader.query_collection("safe", limit=1) == [
        {"hello": "world"},
    ]
    assert vault_loader.list_collections() == ["safe"]
    stats = vault_loader.stats()
    assert stats["collections"] == 1
    assert stats["total_bytes"] == len(payload)
    assert "vault_dir" not in stats


def test_second_legacy_collection_filename_preserves_fallback(vault):
    (vault / "coll__history.jsonl.zst").write_bytes(b'{"ok":true}\n')
    assert vault_loader.query_collection("history") == [{"ok": True}]


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX openat custody")
def test_symlinked_shard_and_hardlink_denied(vault, tmp_path):
    outside = tmp_path / "secret"
    outside.write_bytes(b'{"token":"secret"}\n')
    (vault / "evil.jsonl.zst").symlink_to(outside)
    os.link(outside, vault / "linked.jsonl.zst")
    assert vault_loader.list_collections() == []
    for identifier in ("evil", "linked"):
        with pytest.raises((VaultPathError, OSError)):
            vault_loader.query_collection(identifier)
    assert outside.read_bytes() == b'{"token":"secret"}\n'


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX openat custody")
def test_replaced_directory_symlink_denied(vault, tmp_path):
    (vault / "safe.jsonl.zst").write_bytes(b'{"ok":true}\n')
    real = tmp_path / "real"
    vault.rename(real)
    vault.symlink_to(real, target_is_directory=True)
    with pytest.raises((VaultPathError, OSError)):
        vault_loader.query_collection("safe")
    with pytest.raises((VaultPathError, OSError)):
        vault_loader.list_collections()


def test_compressed_size_budget_blocks_oversized_file(vault, monkeypatch):
    monkeypatch.setattr(vault_loader, "_MAX_COMPRESSED_BYTES", 12)
    (vault / "too_big.jsonl.zst").write_bytes(b'{"text":"large"}\n')
    assert vault_loader.list_collections() == []
    with pytest.raises(VaultPathError):
        vault_loader.query_collection("too_big")


def test_decompression_budget_limits_stream_without_size_header(vault, monkeypatch):
    monkeypatch.setattr(vault_loader, "_MAX_EXPANDED_SCAN_BYTES", 16)
    (vault / "bomb.jsonl.zst").write_bytes(
        b'{"data":"' + b"x" * 64 + b'"}\n'
    )
    with pytest.raises(ValueError, match="decompression"):
        vault_loader.query_collection("bomb")


def test_line_budget_blocks_oversized_row(vault, monkeypatch):
    monkeypatch.setattr(vault_loader, "_MAX_LINE_BYTES", 10)
    (vault / "long.jsonl.zst").write_bytes(b'{"count":123456}\n')
    with pytest.raises(ValueError, match="row"):
        vault_loader.query_collection("long")


@pytest.mark.parametrize("payload", [
    b'["not","a","dict"]\n',
    b'{"duplicate":1,"duplicate":2}\n',
    b'{"nan":NaN}\n',
    b'{"not valid":',
])
def test_invalid_jsonl_fails_closed(vault, payload):
    (vault / "invalid.jsonl.zst").write_bytes(payload)
    with pytest.raises(ValueError):
        vault_loader.query_collection("invalid")


def test_filtered_query_and_topic_remain_available(vault):
    (vault / "audio-voice.jsonl.zst").write_bytes(
        b'{"topic":"sample"}\n{"topic":"another"}\n'
    )
    assert vault_loader.query_collection("audio-voice", contains="another") == [
        {"topic": "another"},
    ]
    assert vault_loader.query_topic("audio") == {
        "audio-voice": [{"topic": "sample"}, {"topic": "another"}],
    }


def test_rejects_path_based_direct_scanner_invocation(vault, tmp_path):
    with pytest.raises(ValueError):
        list(vault_loader._iter_jsonl(tmp_path / "secrets.jsonl.zst"))
    with pytest.raises(ValueError):
        list(vault_loader._iter_jsonl(vault / "bad" / "source.jsonl.zst"))
    with pytest.raises(ValueError):
        vault_loader.query_collection("safe", contains="x" * 513)
