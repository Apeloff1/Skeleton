"""Read-only candidate checkpoint doctor; no speculative model activation."""
from __future__ import annotations
from pathlib import Path
import os

from .strict import sha
from .errors import deny


def verify_checkpoint(directory: Path, expected_sha256: str, *,
                      max_bytes: int = 256000000) -> dict:
    from ..model.gguf.file_guard import open_trusted_root, regular_beneath
    sha(expected_sha256, "checkpoint")
    if type(directory) is not Path or not directory.is_absolute():
        deny("doctor-directory")
    if type(max_bytes) is not int or not 1 <= max_bytes <= 256000000:
        deny("doctor-size")
    fd = open_trusted_root(directory)
    try:
        leaf = expected_sha256 + ".native.json"
        stat_info = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
        if stat_info.st_size <= 0 or stat_info.st_size > max_bytes:
            deny("doctor-checkpoint-size")
        with regular_beneath(fd, leaf, stat_info.st_size) as handle:
            digest_data = __import__("hashlib").sha256()
            remaining = stat_info.st_size
            while remaining:
                data = os.read(handle, min(65536, remaining))
                if not data:
                    deny("doctor-short-read")
                digest_data.update(data)
                remaining -= len(data)
            if os.read(handle, 1):
                deny("doctor-extra-bytes")
        if digest_data.hexdigest() != expected_sha256:
            deny("doctor-checkpoint-sha")
        return {
            "checkpoint_sha256": expected_sha256,
            "bytes_verified": stat_info.st_size,
            "candidate_file_verified": True,
            "model_activated": False,
            "weights_quality_verified": False,
            "release_certified": False,
        }
    finally:
        os.close(fd)
