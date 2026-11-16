"""Private native frame and artifact custody for Linux exact GGUF workers.

An opened file descriptor pins an inode, not immutable bytes. Mandatory full
digest checks before/after a worker remain necessary; independently controlled
read-only deployment storage and complete loader closure remain external holds.
memfd removes ordinary named prompt files, not RAM/swap or process inspection.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile

from .llama_cpp import ArtifactIdentity, LlamaCppRuntimeError


def _denied():
    return LlamaCppRuntimeError("exact GGUF descriptor custody denied")


def linux_descriptor_custody():
    return sys.platform.startswith("linux")


def _stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _verify_artifact(fd, identity, interrupt):
    if type(identity) is not ArtifactIdentity:
        raise _denied()
    before = os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_size != identity.size_bytes
            or before.st_mtime_ns != identity.mtime_ns or before.st_ino != identity.inode
            or _stamp(os.stat(identity.path, follow_symlinks=False)) != _stamp(before)):
        raise _denied()
    digest = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        interrupt()
        block = os.pread(fd, min(1024 * 1024, before.st_size - offset), offset)
        if not block:
            raise _denied()
        digest.update(block)
        offset += len(block)
    interrupt()
    if (digest.hexdigest() != identity.sha256 or _stamp(os.fstat(fd)) != _stamp(before)
            or _stamp(os.stat(identity.path, follow_symlinks=False)) != _stamp(before)):
        raise _denied()
    return _stamp(before)


def _open_artifact(stack, identity, interrupt):
    fd = os.open(identity.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    stack.callback(os.close, fd)
    _verify_artifact(fd, identity, interrupt)
    return fd


def _anon(stack, label):
    # Import only on Linux, never on Windows module import.
    import fcntl
    if not hasattr(os, "memfd_create") or not hasattr(os, "MFD_ALLOW_SEALING"):
        raise _denied()
    fd = os.memfd_create(label, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    stack.callback(os.close, fd)
    os.fchmod(fd, 0o600)
    return fd


def _seal(fd):
    import fcntl
    flags = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, flags)
    if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & flags != flags:
        raise _denied()


def _write_all(fd, raw):
    view = memoryview(raw)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            raise _denied()
        view = view[n:]
    os.lseek(fd, 0, os.SEEK_SET)


def _read_all(fd, limit):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= limit:
        raise _denied()
    chunks = []
    offset = 0
    while offset < info.st_size:
        block = os.pread(fd, min(1024 * 1024, info.st_size - offset), offset)
        if not block:
            raise _denied()
        chunks.append(block)
        offset += len(block)
    if _stamp(os.fstat(fd)) != _stamp(info):
        raise _denied()
    return b"".join(chunks)


class _LinuxFrame:
    def __init__(self, stack, base, runtime, model, payload, interrupt):
        self.base = base
        self._runtime, self._model = runtime, model
        self._runtime_fd = _open_artifact(stack, runtime, interrupt)
        self._model_fd = _open_artifact(stack, model, interrupt)
        self._input = _anon(stack, "skeleton-gguf-input")
        self._output = _anon(stack, "skeleton-gguf-output")
        self._stderr = _anon(stack, "skeleton-gguf-stderr")
        _write_all(self._input, payload)
        _seal(self._input)
        self.pass_fds = (self._runtime_fd, self._model_fd, self._input, self._output)
        self.executable = self._path(self._runtime_fd)
        self.model = self._path(self._model_fd)
        self.source = self._path(self._input)
        self.target = self._path(self._output)
        self.stderr = self._stderr
        # Validate procfs aliases in the parent before publishing any child.
        for value in self.pass_fds:
            if _stamp(os.stat(self._path(value))) != _stamp(os.fstat(value)):
                raise _denied()

    @staticmethod
    def _path(fd):
        return "/proc/self/fd/" + str(fd)

    def sizes(self):
        return os.fstat(self._output).st_size, os.fstat(self._stderr).st_size

    def verify(self, interrupt):
        _verify_artifact(self._runtime_fd, self._runtime, interrupt)
        _verify_artifact(self._model_fd, self._model, interrupt)

    def read(self, limit):
        # No other writer may change response after successful child exit.
        _seal(self._output)
        return _read_all(self._output, limit)


class _NamedFrame:
    """Historical non-Linux POSIX transport, explicitly not descriptor custody."""
    pass_fds = ()

    def __init__(self, stack, base, runtime, model, payload, interrupt):
        self.base = base
        self.executable, self.model = runtime.path, model.path
        self.source = base / "request.bin"
        self.target = base / "response.bin"
        self._stderr = base / "stderr.bin"
        for path, content in ((self.source, payload), (self.target, b"")):
            with path.open("xb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(content)
        self.stderr = stack.enter_context(self._stderr.open("xb"))
        os.fchmod(self.stderr.fileno(), 0o600)

    def sizes(self):
        return self.target.stat().st_size, self._stderr.stat().st_size

    def verify(self, interrupt):
        # Caller retains legacy full path-based artifact verification.
        interrupt()

    def read(self, limit):
        with self.target.open("rb") as stream:
            return stream.read(limit + 1)


@contextmanager
def private_frame(runtime, model, payload, interrupt):
    if type(payload) is not bytes:
        raise _denied()
    with ExitStack() as stack:
        base = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="skeleton-gguf-exact-")))
        cls = _LinuxFrame if linux_descriptor_custody() else _NamedFrame
        try:
            frame = cls(stack, base, runtime, model, payload, interrupt)
        except (OSError, AttributeError, ImportError):
            # Linux must fail closed if memfd/sealing/procfs is unavailable;
            # no downgrade to ordinary named prompt files.
            raise _denied() from None
        yield frame
