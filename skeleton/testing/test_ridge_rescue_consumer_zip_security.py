"""Archive verifier rejects hostile zip members before decompression."""
from __future__ import annotations

import io
import stat
import zipfile

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_bundle import (
    build_bytes, verify_bytes, BundleError,
)


def test_symlink_member_refused():
    original = build_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as source:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as target:
            for member in source.infolist():
                data = source.read(member.filename)
                if member.filename == "ridge_rescue/consumer_cli.py":
                    member.external_attr = (stat.S_IFLNK | 0o777) << 16
                target.writestr(member, data)
    with pytest.raises(BundleError, match="unsafe archive member"):
        verify_bytes(buffer.getvalue())


def test_unexpected_archive_member_refused():
    original = build_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as source:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as target:
            for member in source.infolist():
                target.writestr(member, source.read(member.filename))
            target.writestr("unexpected.sh", b"exit 1")
    with pytest.raises(BundleError, match="unexpected"):
        verify_bytes(buffer.getvalue())


def test_local_header_timestamp_disagreement_refused():
    # Central-directory metadata stays intact; Python's ZIP reader tolerates
    # local-header timestamp disagreement, but our publisher must not.
    modified = bytearray(build_bytes())
    assert modified[:4] == bytes.fromhex("504b0304")
    modified[10] ^= 1
    with pytest.raises(BundleError, match="noncanonical portable archive bytes"):
        verify_bytes(bytes(modified))
