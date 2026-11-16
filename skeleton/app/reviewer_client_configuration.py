"""Operator-owned TLS and signer pin loader for guarded native startup.

This is an explicit trusted composition API, not a request/env configuration
loader. TLS trust is restricted to the exact independently pinned CA and
client certificate. Read-only file custody does not prove host isolation.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import ssl
import stat

from cryptography import x509

from skeleton.ai.runtime.inference.reviewer_custody import ReviewerCustodyError, ReviewerTrustAnchor
from skeleton.ai.runtime.inference.signed_reviewer_client import SignedReviewerClient


def _deny():
    return ReviewerCustodyError("independently pinned reviewer TLS configuration unavailable")


def _pin(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _read_file(path, maximum, *, private=False):
    if not isinstance(path, Path) or not path.is_absolute():
        raise _deny()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        def stamp(v):
            return v.st_dev, v.st_ino, v.st_mode, v.st_size, v.st_mtime_ns, v.st_ctime_ns
        if (not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= maximum
                or stamp(before) != stamp(path.lstat())):
            raise _deny()
        if private and (os.name != "posix" or before.st_uid != os.geteuid() or before.st_mode & 0o077):
            raise _deny()
        raw = bytearray()
        while len(raw) < before.st_size:
            block = os.read(fd, min(65536, before.st_size-len(raw)))
            if not block:
                raise _deny()
            raw.extend(block)
        if os.read(fd, 1) or stamp(before) != stamp(os.fstat(fd)) or stamp(before) != stamp(path.lstat()):
            raise _deny()
        return bytes(raw)
    finally:
        os.close(fd)


@dataclass(frozen=True, slots=True)
class PinnedReviewerTLS:
    ca_path: Path
    ca_sha256: str
    client_cert_path: Path
    client_cert_sha256: str
    client_key_path: Path

    def __post_init__(self):
        if (not _pin(self.ca_sha256) or not _pin(self.client_cert_sha256)
                or any(not isinstance(v, Path) or not v.is_absolute()
                       for v in (self.ca_path, self.client_cert_path, self.client_key_path))):
            raise _deny()

    def context(self):
        try:
            ca = _read_file(self.ca_path, 256*1024)
            certificate = _read_file(self.client_cert_path, 256*1024)
            private_key = _read_file(self.client_key_path, 64*1024, private=True)
            if (hashlib.sha256(ca).hexdigest() != self.ca_sha256
                    or hashlib.sha256(certificate).hexdigest() != self.client_cert_sha256):
                raise _deny()
            # Parse the actual PEM certificates, not arbitrary OpenSSL config.
            ca_certs = x509.load_pem_x509_certificates(ca)
            leaf_chain = x509.load_pem_x509_certificates(certificate)
            if not 1 <= len(ca_certs) <= 16 or not 1 <= len(leaf_chain) <= 16:
                raise _deny()
            for cert in ca_certs:
                if cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is not True:
                    raise _deny()
            if leaf_chain[0].extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                raise _deny()
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            tls.minimum_version = ssl.TLSVersion.TLSv1_2
            tls.check_hostname = True
            tls.verify_mode = ssl.CERT_REQUIRED
            tls.load_verify_locations(cadata=ca.decode("ascii", "strict"))
            # SSLContext.load_cert_chain requires filenames. On Linux use
            # anonymous sealed descriptors; no persisted private key copy.
            if os.name != "posix" or not hasattr(os, "memfd_create"):
                raise _deny()
            import fcntl
            with ExitStack() as stack:
                def sealed(raw):
                    fd = os.memfd_create("skeleton-reviewer-tls", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
                    stack.callback(os.close, fd)
                    os.fchmod(fd, 0o600)
                    view = memoryview(raw)
                    while view:
                        count = os.write(fd, view)
                        if count <= 0:
                            raise _deny()
                        view = view[count:]
                    os.lseek(fd, 0, os.SEEK_SET)
                    seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
                    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
                    if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals != seals:
                        raise _deny()
                    return "/proc/self/fd/" + str(fd)
                tls.load_cert_chain(certfile=sealed(certificate), keyfile=sealed(private_key),
                                    password=lambda: b"")
            return tls
        except ReviewerCustodyError:
            raise
        except Exception:
            raise _deny() from None


def create_pinned_reviewer_client(*, endpoint, anchor, tls, timeout_seconds=3.0):
    if type(anchor) is not ReviewerTrustAnchor or type(tls) is not PinnedReviewerTLS:
        raise _deny()
    return SignedReviewerClient(base_url=endpoint, trust_anchor=anchor,
                                tls_context=tls.context(), timeout_seconds=timeout_seconds)


__all__ = ["PinnedReviewerTLS", "create_pinned_reviewer_client"]
