"""Dedicated GGUF inference subprocess (only fixed trusted entry point).

Do not use stdout for diagnostics: it is reserved for framed, typed IPC. All
model loading is delegated to the existing sealed model admission. No remote
API, plaintext model dump, model-selected tools, or mock substitution exists.
"""
from __future__ import annotations
from contextlib import ExitStack
import os
import sys
import time
from .contracts import IsolationProtocolError, IsolationPolicy, integer, digest
from .wire import read_frame, write_frame
from .messages import validate
from .receipts import emit_generation


def _deadline(minutes: int = 525600) -> int:
    return time.monotonic_ns() + minutes * 60 * 1_000_000_000


def serve() -> None:
    if os.name != 'posix':
        raise IsolationProtocolError('worker requires POSIX custody')
    boot = read_frame(sys.stdin.fileno(), _deadline(), 16_384)
    expected = {'version', 'type', 'model_root', 'manifest_name', 'context_tokens',
                'threads', 'gpu_layers', 'model_sha256', 'manifest_sha256',
                'request_timeout_ms', 'max_frame_bytes'}
    if set(boot) != expected or type(boot['version']) is not int or boot['version'] != 1 or boot['type'] != 'boot':
        raise IsolationProtocolError('malformed model boot request')
    root = boot['model_root']
    filename = boot['manifest_name']
    if not isinstance(root, str) or not root.startswith('/') or len(root) > 2048:
        raise IsolationProtocolError('invalid model root')
    if not isinstance(filename, str) or not filename or '/' in filename or '\\' in filename:
        raise IsolationProtocolError('invalid model manifest name')
    context = integer(boot['context_tokens'], 'context', 128, 131072)
    threads = integer(boot['threads'], 'threads', 1, 64)
    gpu_layers = integer(boot['gpu_layers'], 'gpu layers', 0, 256)
    integer(boot['request_timeout_ms'], 'request time limit', 100, 600000)
    frame_limit = integer(boot['max_frame_bytes'], 'frame size', 8192, 2097152)
    expected_model = digest(boot['model_sha256'], 'model')
    expected_manifest = digest(boot['manifest_sha256'], 'manifest')
    from ..gguf.service import load_approved_manifest, activate_model
    manifest = load_approved_manifest(root, filename)
    if manifest.model_sha256 != expected_model or manifest.manifest_digest != expected_manifest:
        raise IsolationProtocolError('operator model changed before activation')
    with ExitStack() as stack:
        model = stack.enter_context(activate_model(root, manifest,
            n_ctx=context, n_threads=threads, n_gpu_layers=gpu_layers))
        write_frame(sys.stdout.fileno(), {'version': 1, 'type': 'ready',
            'model_sha256': model.model_digest,
            'tokenizer_sha256': model.tokenizer_digest,
            'manifest_sha256': manifest.manifest_digest}, _deadline(), 16_384)
        last_id = 0
        while True:
            req = read_frame(sys.stdin.fileno(), _deadline(), frame_limit)
            if req == {'version': 1, 'type': 'shutdown'}:
                return
            if set(req) == {'version', 'type', 'request'} and req['type'] == 'ping':
                if (type(req['version']) is not int or req['version'] != 1
                        or type(req['request']) is not int or req['request'] != last_id + 1):
                    raise IsolationProtocolError('heartbeat sequence mismatch')
                last_id = req['request']
                write_frame(sys.stdout.fileno(), {'version': 1, 'type': 'pong',
                    'request': last_id, 'model_sha256': model.model_digest},
                    _deadline(), 16384)
                continue
            if set(req) != {'version', 'type', 'request', 'messages',
                            'max_output_tokens', 'seed', 'temperature'}:
                raise IsolationProtocolError('unknown worker request type or keys')
            if (type(req['version']) is not int or req['version'] != 1 or req['type'] != 'generate'
                    or type(req['request']) is not int or req['request'] != last_id + 1):
                raise IsolationProtocolError('worker request ordering violated')
            messages = validate(req['messages'], req['max_output_tokens'],
                                req['seed'], req['temperature'],
                                IsolationPolicy(
                                    context_tokens=context, threads=threads,
                                    gpu_layers=gpu_layers, max_frame_bytes=frame_limit))
            last_id = req['request']
            result = model.generate(messages, max_output_tokens=req['max_output_tokens'],
                                    seed=req['seed'], temperature=float(req['temperature']))
            write_frame(sys.stdout.fileno(), emit_generation(result, last_id),
                        _deadline(), frame_limit)


def main() -> int:
    try:
        serve()
        return 0
    except BaseException:
        # No text or stack traces on the protocol channel or stderr.
        # The parent treats any early EOF as an uncertain operation.
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
