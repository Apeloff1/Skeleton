"""Real-model operator canary through the killable sidecar, without mock mode.

No prompt, user data, generated plaintext, private model path or secrets are
logged. Successful native execution proves only that the configured local
runtime generated valid receipts, not semantic quality or device readiness.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
from .client import IsolatedGGUFBackend
from .contracts import IsolationFailure
from ..gguf.service import load_approved_manifest

_PROBE = 'Describe in one short sentence what an offline language model does.'


def run(*, model_root: Path, threads: int, context_tokens: int,
        max_output_tokens: int, repetitions: int, timeout_ms: int) -> dict:
    if type(repetitions) is not int or not 1 <= repetitions <= 20:
        raise IsolationFailure('invalid finite canary repetition count')
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 1024:
        raise IsolationFailure('invalid canary output ceiling')
    manifest = load_approved_manifest(model_root)
    durations = []
    completions = []
    with IsolatedGGUFBackend(model_root.absolute(), manifest, n_threads=threads,
                             n_ctx=context_tokens, inference_ms=timeout_ms) as backend:
        probe = backend.probe(deadline_ms=min(5000, timeout_ms))
        for n in range(repetitions):
            before = time.monotonic_ns()
            result = backend.generate([{'role': 'system', 'content': 'Do not use tools.'},
                {'role': 'user', 'content': _PROBE}], max_output_tokens=max_output_tokens,
                seed=101 + n, temperature=0.5)
            durations.append(time.monotonic_ns() - before)
            completions.append({'output_sha256': result.output_digest,
                'prompt_tokens': result.prompt_tokens,
                'generated_tokens': result.generated_tokens,
                'finish_reason': result.finish_reason})
        health = backend.health()
    sorted_durations = sorted(durations)
    return {'status': 'live-GGUF-subprocess-canary-not-quality-certified',
            'model_sha256': manifest.model_sha256,
            'manifest_sha256': manifest.manifest_digest,
            'worker_status': probe['status'],
            'repetitions': repetitions, 'completion_receipts': completions,
            'minimum_elapsed_ns': sorted_durations[0],
            'median_elapsed_ns': sorted_durations[(len(sorted_durations)-1)//2],
            'p95_elapsed_ns': sorted_durations[(95*len(sorted_durations)-1)//100],
            'maximum_elapsed_ns': sorted_durations[-1],
            'requests_failed': health['requests_failed'],
            'qualification': 'local-inference-only-full-device-and-restart-unverified'}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='Native GGUF killable-subprocess canary')
    p.add_argument('--model-root', type=Path, required=True)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--context', type=int, default=2048)
    p.add_argument('--max-new-tokens', type=int, default=128)
    p.add_argument('--repetitions', type=int, default=3)
    p.add_argument('--timeout-ms', type=int, default=90000)
    args = p.parse_args(argv)
    try:
        report = run(model_root=args.model_root, threads=args.threads,
                     context_tokens=args.context, max_output_tokens=args.max_new_tokens,
                     repetitions=args.repetitions, timeout_ms=args.timeout_ms)
    except BaseException as exc:
        print(json.dumps({'status': 'held', 'error_class': type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
