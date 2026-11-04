"""Portable archive acceptance refuses hostile ZIP metadata."""
from __future__ import annotations
import io
import zipfile
import pytest
from skeleton.game.gameplay.ridge_rescue.consumer_bundle import BundleError, build_bytes, verify_bytes


def rewritten(extra=None, compression=zipfile.ZIP_DEFLATED, mode=0o100644):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(build_bytes())) as original:
        with zipfile.ZipFile(output, "w") as dest:
            for name in original.namelist():
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = compression
                info.external_attr = mode << 16
                dest.writestr(info, original.read(name))
            if extra:
                info = zipfile.ZipInfo(extra, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                dest.writestr(info, b"payload")
    return output.getvalue()


@pytest.mark.parametrize("member", [
    "ridge_rescue/./extra.py",
    "ridge_rescue//extra.py",
    "ridge_rescue/../extra.py",
    "ridge_rescue/extra" + chr(92) + "evil.py",
])
def test_noncanonical_member_refused(member):
    with pytest.raises(BundleError):
        verify_bytes(rewritten(extra=member))


def test_uncompressed_archive_refused():
    with pytest.raises(BundleError, match="unsafe archive encoding"):
        verify_bytes(rewritten(compression=zipfile.ZIP_STORED))


def test_symlink_archive_refused():
    with pytest.raises(BundleError, match="non-regular"):
        verify_bytes(rewritten(mode=0o120777))


def test_canonical_archive_still_accepted():
    assert verify_bytes(build_bytes())["python_required"]
