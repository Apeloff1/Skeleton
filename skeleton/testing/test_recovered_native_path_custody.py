"""Source-recovery regressions for private native artifact custody.

The root opener is isolated only in descriptor mechanics tests because pytest
temporary roots may sit under world-writable /tmp. Production retains the
canonical ancestry guard and performs no path-based mkdir.
"""
import os
from pathlib import Path

import pytest

from skeleton.ai.runtime.operational_ai import recovered_path_custody as custody


def test_concrete_path_and_rejected_unsafe_paths(tmp_path):
    assert custody.require_absolute_directory(tmp_path) == tmp_path
    for path in (str(tmp_path), Path("relative"), Path(tmp_path.anchor), tmp_path / ".." / "x"):
        with pytest.raises(ValueError):
            custody.require_absolute_directory(path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_descriptor_leaf_create_and_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(custody, "open_trusted_root", lambda path: os.open(path, os.O_RDONLY | os.O_DIRECTORY))
    leaf = tmp_path / "private"
    fd = custody.open_private_directory(leaf, create=True)
    try:
        assert os.fstat(fd).st_mode & 0o777 == 0o700
    finally:
        os.close(fd)
    fd = custody.open_private_directory(leaf, create=False)
    os.close(fd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_untrusted_parent_blocks_creation(tmp_path, monkeypatch):
    def reject(path):
        raise ValueError("untrusted parent")

    monkeypatch.setattr(custody, "open_trusted_root", reject)
    leaf = tmp_path / "denied"
    with pytest.raises(ValueError):
        custody.open_private_directory(leaf, create=True)
    assert not leaf.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_symlink_and_nonprivate_target_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(custody, "open_trusted_root", lambda path: os.open(path, os.O_RDONLY | os.O_DIRECTORY))
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(external, target_is_directory=True)
    with pytest.raises(OSError):
        custody.open_private_directory(link, create=True)
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    with pytest.raises(ValueError):
        custody.open_private_directory(shared, create=False)
