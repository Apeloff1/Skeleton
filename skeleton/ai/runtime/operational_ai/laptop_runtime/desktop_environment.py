"""Minimal host environment for a single offline, installed GGUF child.

A desktop process often inherits unrelated GitHub, cloud-provider, browser,
proxy and shell initialization credentials. A native model worker needs
platform process essentials and explicit device selectors, not this ambient
authority. Never read secret variable values or log omitted variables.
"""
from __future__ import annotations

import os
from typing import Mapping


class NativeChildEnvironmentHold(ValueError):
    """A local child could not be launched without unsafe inherited state."""


# Essentials for Windows/POSIX process startup, venv location, platform
# locale/timezone, native ABI and device selector discovery. Do not inherit
# PYTHONPATH/PYTHONHOME, proxy variables, shell hooks or preloaded DLLs.
_ALLOWED = frozenset({
    "PATH", "Path", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PUBLIC",
    "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TZ",
    "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
    "PYTHONUTF8", "PYTHONIOENCODING", "PYTHONUNBUFFERED",
    "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "CUDA_PATH",
    "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES",
    "NVIDIA_DRIVER_CAPABILITIES", "HIP_PATH", "ROCM_PATH",
    "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
    "GGML_CUDA_FORCE_MMQ", "GGML_CUDA_FORCE_CUBLAS",
    "GGML_VULKAN_DEBUG", "VULKAN_ICD_FILENAMES",
})
_MAX_VALUE_BYTES = 32768
_MAX_TOTAL_BYTES = 131072


def native_child_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a finite explicit allowlist without copying cloud credentials.

    Source defaults to the process environment. This routine never modifies
    its parent and returns only an independent exact map for Popen(env=...).
    """
    if source is None:
        source = os.environ
    if not isinstance(source, Mapping):
        raise NativeChildEnvironmentHold("local child environment must be a mapping")

    forwarded: dict[str, str] = {}
    total = 0
    for name in sorted(_ALLOWED):
        if name not in source:
            continue
        value = source[name]
        if not isinstance(value, str):
            raise NativeChildEnvironmentHold("invalid native platform environment value")
        try:
            raw = value.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise NativeChildEnvironmentHold("native environment contains invalid Unicode") from exc
        if (
            len(raw) > _MAX_VALUE_BYTES
            or any(character in value for character in ("\x00", "\r", "\n"))
        ):
            raise NativeChildEnvironmentHold("native platform environment exceeds its budget")
        total += len(name.encode("ascii")) + len(raw) + 2
        if total > _MAX_TOTAL_BYTES:
            raise NativeChildEnvironmentHold("native platform environment aggregate budget exceeded")
        forwarded[name] = value
    return forwarded


__all__ = ["NativeChildEnvironmentHold", "native_child_environment"]
