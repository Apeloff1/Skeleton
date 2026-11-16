"""Physical CPU exact-token qualification; never a production readiness grant.

The only model admitted here is the existing independently pinned chat recipe.
The executable digest is an external input (CI freshly built binary custody,
or operator-reviewed binary pin). This lane measures real native operations,
not chatbot quality, service startup, GPU, signer or release qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.provision_local_ai import MODEL, MODEL_IDS, _download_pinned, _verify
from skeleton.ai.runtime.inference.gguf_token_bridge import GgufTokenBridgeModel
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig, LlamaCppRuntimeError
from skeleton.ai.runtime.inference.local import LocalInferenceCancelled, LocalInferenceRequest

_SCHEMA = "skeleton.gguf.real_cpu_qualification.v1"
_SOURCE = "d81235049384534c167caea52b85a694f6103d14"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_TEST_TEXTS = (
    "Hello, native tokenizer!",
    "Norwegian: blåbær, 世界, 🌍",
    " leading spaces\tand\nnewlines ",
    "Literal <|im_start|> and <|im_end|> are not control tokens.",
)
_TEST_PROMPTS = ("Complete this sequence: one, two, three,",
                 "Continue the pattern: A, B, C, D,")


class QualificationError(RuntimeError):
    pass


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _assert_sha(value, pattern):
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise QualificationError("qualification identity invalid")
    return value


def _source_head(expected):
    _assert_sha(expected, _SHA)
    actual = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10,
    ).stdout.strip()
    if actual != expected:
        raise QualificationError("qualification source head mismatch")


def _assert_runtime(path, expected):
    _assert_sha(expected, _HEX)
    if path.is_symlink() or not path.is_absolute():
        raise QualificationError("runtime must be an absolute non-symlink file")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
        raise QualificationError("runtime is not executable")
    from scripts.provision_local_ai import _sha
    if _sha(path, max_bytes=256 * 1024 * 1024) != expected:
        raise QualificationError("runtime digest mismatch")


def _must_deny(action, exceptions):
    try:
        action()
    except exceptions:
        return
    raise QualificationError("negative boundary unexpectedly admitted")


def qualify(*, executable, executable_sha256, weights, head, threads=2):
    if not sys.platform.startswith("linux"):
        raise QualificationError("this qualification lane requires Linux")
    if type(threads) is not int or not 1 <= threads <= 8:
        raise QualificationError("qualification thread count invalid")
    _source_head(head)
    _assert_runtime(executable, executable_sha256)
    _verify(weights, MODEL)
    started = time.monotonic()
    backend = GgufTokenBridgeModel(LlamaCppConfig(
        executable=str(executable), model_path=str(weights), model_id=MODEL_IDS["chat"],
        context_size=512, threads=threads, batch_size=128, gpu_layers=0,
        timeout_seconds=180.0, max_output_bytes=65536, max_stderr_bytes=1024 * 1024,
    ))
    if (backend.runtime_digest != executable_sha256 or backend.model_digest != MODEL["sha256"]
            or backend.execution_snapshot()["private_transport"] != "linux_sealed_memfd"):
        raise QualificationError("activated native backend custody mismatch")
    tokens = []
    for text in _TEST_TEXTS:
        t0 = time.monotonic()
        sequence, echo = backend.roundtrip_ids(text)
        if (not sequence or echo != text or backend.encode_ids(text) != sequence
                or backend.decode_ids(sequence) != text):
            raise QualificationError("physical tokenizer roundtrip mismatch")
        tokens.append({"input_sha256": _digest(text.encode()), "token_count": len(sequence),
                       "roundtrip_and_split_equal": True,
                       "elapsed_ms": round((time.monotonic() - t0) * 1000, 3)})
    generations = []
    for prompt in _TEST_PROMPTS:
        request = LocalInferenceRequest(prompt=prompt, max_output_tokens=16, temperature=0)
        prepared = backend.prepare_input(request, scope_digest="a" * 64)
        if prepared.input_tokens <= 0:
            raise QualificationError("physical model preparation empty")
        _must_deny(lambda: backend.infer_prepared(
            request, threading.Event(), replace(prepared, token_sequence=(0,))),
            (ValueError, LlamaCppRuntimeError))
        cancelled = threading.Event()
        cancelled.set()
        _must_deny(lambda: backend.infer_prepared(request, cancelled, prepared),
                   (LocalInferenceCancelled,))
        before = backend.execution_snapshot()["processes_started"]
        t0 = time.monotonic()
        result = backend.infer_prepared(request, threading.Event(), prepared)
        elapsed = time.monotonic() - t0
        replay = backend.infer_prepared(request, threading.Event(), prepared)
        after = backend.execution_snapshot()["processes_started"]
        if (type(result.text) is not str or not result.text.strip()
                or not 1 <= result.output_tokens <= request.max_output_tokens
                or result.input_tokens != prepared.input_tokens
                or result.model_digest != MODEL["sha256"]
                or result.usage_source != "local_model"
                or result.execution_receipt_digest is None
                or result.text != replay.text
                or result.execution_receipt_digest != replay.execution_receipt_digest
                or after - before != 4):
            raise QualificationError("physical generation or deterministic replay mismatch")
        _assert_sha(result.execution_receipt_digest, _HEX)
        generations.append({
            "request_sha256": request.digest, "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens, "finish_reason": result.finish_reason,
            "output_sha256": _digest(result.text.encode()),
            "execution_receipt_sha256": result.execution_receipt_digest,
            "replay_identical": True, "subprocess_launches_including_echo_and_replay": after - before,
            "elapsed_ms_including_custody_and_echo": round(elapsed * 1000, 3),
        })
    backend.assert_identity()
    _assert_runtime(executable, executable_sha256)
    _verify(weights, MODEL)
    _source_head(head)
    final = backend.execution_snapshot()
    if (final["active_processes"] or final["spawning_processes"] or final["draining_processes"]
            or final["processes_started"] != final["processes_exited"]):
        raise QualificationError("native subprocesses not quiescent")
    value = {
        "schema": _SCHEMA, "source_head": head, "upstream_source_target": _SOURCE,
        "runtime_sha256": executable_sha256, "model_sha256": MODEL["sha256"],
        "model_bytes": MODEL["bytes"], "tokenizer_sha256": backend.tokenizer_digest,
        "runtime_profile_sha256": backend.execution_profile_digest,
        "device_class": "linux_cpu", "threads": threads,
        "context_tokens": 512, "transport": final["private_transport"],
        "scope": "real_pinned_model_tokenizer_and_direct_cpu_generation",
        "tokenizer_cases": tokens, "generation_cases": generations,
        "total_elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "native_processes_started": final["processes_started"],
        "native_processes_exited": final["processes_exited"],
        "held": ["production_activation", "independent_reviewer", "mongo_epoch",
                 "chat_quality", "gpu", "windows", "loader_closure", "release"],
    }
    value["receipt_sha256"] = _digest(_canonical(value))
    return value


def publish(path, receipt):
    # Create-only, atomic link. A failed or partial run creates no receipt.
    path = path.absolute()
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise QualificationError("receipt destination unavailable")
    candidate = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".gguf-qualification-",
                                         delete=False) as stream:
            candidate = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(_canonical(receipt) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(candidate, path)
        fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--executable-sha256", required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=2)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--model", type=Path, help="existing exact pinned chat model")
    group.add_argument("--download", action="store_true", help="explicit pinned model transfer")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
            raise QualificationError("receipt destination unavailable")
        _source_head(args.source_head)
        _assert_runtime(args.executable, args.executable_sha256)
        with tempfile.TemporaryDirectory(prefix="skeleton-physical-gguf-") as directory:
            weights = args.model
            if args.download:
                weights = Path(directory) / MODEL["filename"]
                _download_pinned(weights, MODEL)
            receipt = qualify(executable=args.executable, executable_sha256=args.executable_sha256,
                              weights=weights, head=args.source_head, threads=args.threads)
            publish(args.output, receipt)
        print(json.dumps(receipt, sort_keys=True, ensure_ascii=True))
        return 0
    except Exception:
        # Never dump model text, argv, private paths or driver output.
        print("Exact GGUF physical CPU qualification failed; no passing evidence.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
