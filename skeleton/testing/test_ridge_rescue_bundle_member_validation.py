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


@pytest.mark.parametrize("member", [
    "ridge_rescue/CON.py",
    "ridge_rescue/nul.json",
    "ridge_rescue/LPT9.py",
    "ridge_rescue/aux.extra.py",
    "ridge_rescue/scene .py",
    "ridge_rescue/scene:.py",
    "ridge_rescue/épisode.py",
])
def test_windows_unsafe_member_refused(member):
    with pytest.raises(BundleError, match="unsafe Windows"):
        verify_bytes(rewritten(extra=member))


def test_windows_case_collision_refused():
    with pytest.raises(BundleError, match="case-colliding"):
        verify_bytes(rewritten(extra="RIDGE_RESCUE/CONSUMER_CLI.PY"))


@pytest.mark.parametrize("mutate", [
    lambda data: b"MZ" + data,
    lambda data: data + b"hidden-trailing-content",
    lambda data: data[:-2] + bytes((1, 0)) + b"X",
])
def test_noncanonical_zip_envelope_refused(mutate):
    with pytest.raises(BundleError, match="noncanonical ZIP envelope"):
        verify_bytes(mutate(build_bytes()))


def test_zip_member_extra_field_refused():
    archive = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(build_bytes())) as original:
        with zipfile.ZipFile(archive, "w") as dest:
            for name in original.namelist():
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                if name == "ridge_rescue/consumer_cli.py":
                    info.extra = b"\x01\x00\x00\x00"
                dest.writestr(info, original.read(name))
    with pytest.raises(BundleError, match="unsafe archive encoding"):
        verify_bytes(archive.getvalue())


def test_zip_member_comment_refused():
    archive = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(build_bytes())) as original:
        with zipfile.ZipFile(archive, "w") as dest:
            for name in original.namelist():
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                if name == "ridge_rescue/consumer_cli.py":
                    info.comment = b"hidden metadata"
                dest.writestr(info, original.read(name))
    with pytest.raises(BundleError, match="unsafe archive encoding"):
        verify_bytes(archive.getvalue())
