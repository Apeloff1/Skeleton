"""Build an explicitly pinned offline GGUF quantization candidate.

Operator-only POSIX tool. The supplied quantizer is trusted executable code,
not sandboxed by its SHA. No automatic weight replacement, downloads, LoRA
training or inference activation. Output is create-only and unqualified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from typing import Sequence

from skeleton.ai.runtime.inference.llama_cpp import (
    LlamaCppRuntimeError, _inspect_gguf_stream, _serving_metadata,
)
from scripts.audit_consumer_gguf_shards import _open_directory, _open_file, _identity

_MAX = 1024**4
_HEX = re.compile(r"[0-9a-f]{64}")
_SCHEMES = frozenset({"Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"})
_TENSOR_TYPES = frozenset({"q4_K", "q5_K", "q6_K", "q8_0", "f16", "f32"})
_TENSOR_NAME = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+){0,12}")
# Independent child sets a hard output-file limit before exec. Static code,
# no interpolation of operator strings into the Python program.
_LIMIT_EXEC = (
    "import os,resource,sys;"
    "n=int(sys.argv[1]);resource.setrlimit(resource.RLIMIT_FSIZE,(n,n));"
    "os.execv(sys.argv[2],sys.argv[2:])"
)


def _validate_pin(pin):
    if not isinstance(pin, str) or not _HEX.fullmatch(pin):
        raise ValueError("explicit lowercase SHA-256 pin required")


def _path(path: Path) -> Path:
    if not isinstance(path, Path) or ".." in path.parts:
        raise ValueError("bounded explicit path required")
    return Path(os.path.abspath(path.expanduser()))


def _scan(path: Path, *, limit: int, pin: str | None = None,
          gguf: bool = False, executable: bool = False) -> tuple[str, tuple]:
    if pin is not None:
        _validate_pin(pin)
    directory = _open_directory(path.parent)
    try:
        fd = _open_file(directory, path.name)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            identity = _identity(info)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 1 <= info.st_size <= limit:
                raise ValueError("artifact violates file identity or byte cap")
            if executable and not info.st_mode & 0o111:
                raise ValueError("quantizer is not executable")
            if gguf:
                header = _inspect_gguf_stream(stream)
                _serving_metadata(path, header, stream=stream).require_single_file(header)
            stream.seek(0)
            digest = hashlib.sha256()
            received = 0
            while True:
                chunk = stream.read(min(1024 * 1024, limit-received+1))
                if not chunk:
                    break
                received += len(chunk)
                if received > limit:
                    raise ValueError("artifact grew beyond byte cap")
                digest.update(chunk)
            result = digest.hexdigest()
            if received != info.st_size or _identity(os.fstat(stream.fileno())) != identity:
                raise OSError("artifact changed while hashing")
            if pin is not None and result != pin:
                raise ValueError("artifact SHA-256 mismatch")
        current = _open_directory(path.parent)
        try:
            checked = _open_file(current, path.name)
            try:
                if _identity(os.fstat(checked)) != identity:
                    raise OSError("artifact replaced")
            finally:
                os.close(checked)
        finally:
            os.close(current)
        return result, identity
    finally:
        os.close(directory)


def recipe(scheme: str, overrides: Sequence[str], *, threads: int,
           has_imatrix: bool) -> tuple[str, ...]:
    if scheme not in _SCHEMES:
        raise ValueError("unreviewed global quantization scheme")
    if type(threads) is not int or not 1 <= threads <= 256:
        raise ValueError("quantization threads out of bounds")
    if len(overrides) > 128 or type(has_imatrix) is not bool:
        raise ValueError("too many tensor overrides or invalid calibration")
    parsed = {}
    for item in overrides:
        if not isinstance(item, str) or len(item) > 256 or item.count("=") != 1:
            raise ValueError("tensor override requires an exact tensor name and type")
        name, kind = item.split("=")
        if not _TENSOR_NAME.fullmatch(name) or kind not in _TENSOR_TYPES or name in parsed:
            raise ValueError("unsupported, duplicate or wildcard tensor override")
        parsed[name] = kind
    # llama-quantize's patterns select tensor names: anchor and escape every
    # dot, disallow user-supplied regular expressions or additional flags.
    result = []
    for name, kind in sorted(parsed.items()):
        result.extend(("--tensor-type", "^" + name.replace(".", r"\.") + "$=" + kind))
    return tuple(result)


def build_candidate(*, quantizer: Path, quantizer_sha256: str,
                    source: Path, source_sha256: str, output: Path,
                    scheme: str, overrides: Sequence[str] = (),
                    imatrix: Path | None = None, imatrix_sha256: str | None = None,
                    threads: int = 4, max_output_bytes: int,
                    timeout_seconds: int = 1800) -> dict:
    if os.name != "posix":
        raise OSError("POSIX file custody and native file ceiling required")
    if type(max_output_bytes) is not int or not 1024 <= max_output_bytes <= _MAX:
        raise ValueError("candidate byte cap outside bounds")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 86400:
        raise ValueError("quantization timeout outside bounds")
    if (imatrix is None) != (imatrix_sha256 is None):
        raise ValueError("calibration file and digest must be supplied together")
    options = recipe(scheme, overrides, threads=threads, has_imatrix=imatrix is not None)
    quantizer, source, output = map(_path, (quantizer, source, output))
    calibration = _path(imatrix) if imatrix is not None else None
    paths = [quantizer, source, output] + ([calibration] if calibration else [])
    if len(set(paths)) != len(paths) or output.suffix != ".gguf":
        raise ValueError("distinct artifact paths and GGUF output required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("candidate output is create-only")
    parent_fd = _open_directory(output.parent)
    try:
        parent_identity = os.fstat(parent_fd)
        # Reserve full configured file budget plus conservative disk headroom.
        if shutil.disk_usage(output.parent).free < max_output_bytes + 64 * 1024**2:
            raise OSError("insufficient staging capacity")
        inputs = [(quantizer, quantizer_sha256, 1024**3, False, True),
                  (source, source_sha256, _MAX, True, False)]
        if calibration is not None:
            inputs.append((calibration, imatrix_sha256, 16 * 1024**3, False, False))
        stable = [_scan(path, limit=limit, pin=pin, gguf=gguf, executable=exe)
                  for path, pin, limit, gguf, exe in inputs]
        with tempfile.TemporaryDirectory(prefix=".gguf-candidate-", dir=output.parent) as tmp:
            staging = Path(tmp)
            candidate = staging / "candidate.gguf"
            args = [str(quantizer), *options]
            if calibration is not None:
                args.extend(("--imatrix", str(calibration)))
            args.extend((str(source), str(candidate), scheme, str(threads)))
            # No inherited provider/proxy credentials, loader env or shell.
            environment = {"PATH": "/usr/bin:/bin", "HOME": tmp, "TMPDIR": tmp,
                           "LANG": "C", "LC_ALL": "C", "OMP_NUM_THREADS": str(threads)}
            proc = subprocess.Popen(
                [sys.executable, "-I", "-c", _LIMIT_EXEC, str(max_output_bytes), *args],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=staging, env=environment, start_new_session=True,
            )
            try:
                status = proc.wait(timeout=timeout_seconds)
            except BaseException:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                raise
            if status != 0:
                raise RuntimeError("pinned quantizer did not produce a successful candidate")
            # Reject any apparent input or executable changes. This is custody
            # checking, not a proof of in-flight immutability against a local attacker.
            observed = [_scan(path, limit=limit, pin=pin, gguf=gguf, executable=exe)
                        for path, pin, limit, gguf, exe in inputs]
            if observed != stable:
                raise OSError("quantization inputs changed")
            digest, identity = _scan(candidate, limit=max_output_bytes, gguf=True)
            with candidate.open("rb") as stream:
                os.fsync(stream.fileno())
            current = _open_directory(output.parent)
            try:
                actual = os.fstat(current)
                if (actual.st_dev, actual.st_ino) != (parent_identity.st_dev, parent_identity.st_ino):
                    raise OSError("output directory was replaced")
                # Publish only by create-exclusive hardlink inside the original
                # parent. TemporaryDirectory removes the staging name later.
                stage_fd = _open_directory(staging)
                try:
                    if _identity(os.stat(candidate.name, dir_fd=stage_fd, follow_symlinks=False)) != identity:
                        raise OSError("staged candidate changed before publication")
                    os.link(candidate.name, output.name, src_dir_fd=stage_fd,
                            dst_dir_fd=current, follow_symlinks=False)
                    os.fsync(current)
                finally:
                    os.close(stage_fd)
            finally:
                os.close(current)
        receipt = {
            "schema": "skeleton.gguf.quantization-candidate.v1",
            "status": "candidate_created_not_qualified",
            "source_sha256": source_sha256, "quantizer_sha256": quantizer_sha256,
            "imatrix_sha256": imatrix_sha256, "scheme": scheme,
            "tensor_overrides": sorted(overrides), "threads": threads,
            "candidate_sha256": digest, "candidate_bytes": identity[2],
            "activation_authorized": False,
        }
        receipt["receipt_sha256"] = hashlib.sha256(json.dumps(
            receipt, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
        return receipt
    finally:
        os.close(parent_fd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("quantizer", "source", "output", "imatrix"):
        parser.add_argument("--" + name, type=Path, required=name != "imatrix")
    for name in ("quantizer-sha256", "source-sha256", "imatrix-sha256"):
        parser.add_argument("--" + name, required=name != "imatrix-sha256")
    parser.add_argument("--scheme", choices=sorted(_SCHEMES), required=True)
    parser.add_argument("--tensor", action="append", default=[])
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-output-bytes", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = vars(parser.parse_args(argv))
    args["overrides"] = args.pop("tensor")
    try:
        result = build_candidate(**args)
    except (OSError, ValueError, RuntimeError, LlamaCppRuntimeError, subprocess.TimeoutExpired):
        parser.exit(2, "GGUF quantization candidate rejected or incomplete\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
