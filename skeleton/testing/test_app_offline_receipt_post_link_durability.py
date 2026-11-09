"""Fail-closed no-clobber receipt publication across uncertain POSIX commits.

The final hardlink is observable before the directory fsync and post-link
identity checks. Any later failure must leave the published name untouched
for explicit operator quarantine; only the private temporary name is cleaned.
"""
from __future__ import annotations

from hashlib import sha256
import errno
import os
from pathlib import Path
import stat

import pytest

from skeleton.ai.game_builder import offline_receipt_publication as publication
from skeleton.ai.game_builder.dual_runtime_verify import (
    DualRuntimeVerificationError, _canonical_bytes,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="POSIX descriptor custody required",
)


def _receipt():
    return {
        "schema": "skeleton.game_builder.receipt_publication_post_link_test.v1",
        "offline_gameplay_reexecuted": True,
        "release_certified": False,
    }


def _publish(target: Path):
    return publication.publish_verified_receipt(
        _receipt(), target, protected_roots=(), authorized=True,
    )


def _assert_published(target: Path):
    data = target.read_bytes()
    assert data == _canonical_bytes(_receipt())
    assert stat.S_ISREG(target.lstat().st_mode)
    assert target.lstat().st_mode & 0o077 == 0
    assert target.stat().st_nlink == 1
    assert not list(target.parent.glob(".receipt-*"))
    assert sha256(data).hexdigest() == sha256(_canonical_bytes(_receipt())).hexdigest()
    # A retry must never overwrite or replace the already published receipt.
    original_inode = target.stat().st_ino
    with pytest.raises(publication.ReceiptPublicationError):
        _publish(target)
    assert target.stat().st_ino == original_inode
    assert target.read_bytes() == data


def test_directory_fsync_failure_after_hardlink_preserves_published_name(
    tmp_path, monkeypatch,
):
    target = tmp_path / "post-link-fsync.json"
    original_fsync = os.fsync
    failed = False

    def fail_directory_once(fd):
        nonlocal failed
        if not failed and stat.S_ISDIR(os.fstat(fd).st_mode):
            failed = True
            raise OSError(errno.EIO, "simulated directory durability failure")
        return original_fsync(fd)

    monkeypatch.setattr(publication.os, "fsync", fail_directory_once)
    with pytest.raises(publication.ReceiptPublicationError):
        _publish(target)
    assert failed
    _assert_published(target)


def test_post_link_root_replacement_alarm_preserves_published_name(
    tmp_path, monkeypatch,
):
    target = tmp_path / "post-link-identity.json"
    original_check = publication._assert_original_root
    calls = 0

    def fail_post_link(root, fd):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise DualRuntimeVerificationError("simulated parent identity swap")
        return original_check(root, fd)

    monkeypatch.setattr(publication, "_assert_original_root", fail_post_link)
    with pytest.raises(publication.ReceiptPublicationError):
        _publish(target)
    assert calls == 3
    _assert_published(target)


def test_pre_link_failure_never_creates_published_name(tmp_path, monkeypatch):
    target = tmp_path / "pre-link-failure.json"

    def reject_link(*args, **kwargs):
        raise OSError(errno.EPERM, "simulated denied publication")

    monkeypatch.setattr(publication.os, "link", reject_link)
    with pytest.raises(publication.ReceiptPublicationError):
        _publish(target)
    assert not target.exists()
    assert not list(tmp_path.glob(".receipt-*"))


def test_post_link_error_cannot_clobber_concurrent_observer(
    tmp_path, monkeypatch,
):
    target = tmp_path / "observer.json"
    original_fsync = os.fsync
    observed = []

    def observe_then_fail(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode) and not observed:
            observed.append(target.read_bytes())
            raise OSError(errno.EIO, "observer saw committed hardlink")
        return original_fsync(fd)

    monkeypatch.setattr(publication.os, "fsync", observe_then_fail)
    with pytest.raises(publication.ReceiptPublicationError):
        _publish(target)
    assert observed == [_canonical_bytes(_receipt())]
    _assert_published(target)
