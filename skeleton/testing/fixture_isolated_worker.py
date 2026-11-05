"""TEST ONLY. Deterministic protocol simulation, never a release/model proof.

Only unit tests may patch the production process owner to point here. The
shipped production launcher has one hard-coded worker module and cannot be
redirected by user input, environment variables or HTTP requests.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import os
import sys
import time
from skeleton.ai.runtime.operational_ai.model.isolation.wire import read_frame, write_frame


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--mode', default='normal')
    mode = p.parse_args().mode
    stdin, stdout = sys.stdin.fileno(), sys.stdout.fileno()
    deadline = lambda: time.monotonic_ns() + 120 * 1_000_000_000
    boot = read_frame(stdin, deadline(), 16384)
    if mode == 'early_boot_exit':
        return 7
    model = boot['model_sha256']
    manifest = boot['manifest_sha256']
    if mode == 'wrong_model':
        model = '0' * 64 if model != '0' * 64 else '1' * 64
    tokenizer = model if mode != 'wrong_tokenizer' else 'f'*64
    write_frame(stdout, {'version': 1, 'type': 'ready', 'model_sha256': model,
                         'tokenizer_sha256': tokenizer, 'manifest_sha256': manifest}, deadline(), 16384)
    seq = 0
    while True:
        message = read_frame(stdin, deadline(), boot['max_frame_bytes'])
        if message['type'] == 'shutdown':
            return 0
        seq += 1
        if mode == 'stall':
            time.sleep(10)
            continue
        if mode == 'exit_after_request':
            os._exit(8)
        if message['type'] == 'ping':
            write_frame(stdout, {'version': 1, 'type': 'pong',
                                 'model_sha256': model, 'request': message['request'] + (1 if mode=='stale_pong' else 0)},
                        deadline(), 16384)
            continue
        if mode == 'invalid_frame':
            os.write(stdout, b'\xff\xff\xff\xff')
            continue
        text = 'original fixture result 🧪\nline two'
        if mode == 'credential_echo':
            text = 'secret present' if 'SKELETON_TEST_SECRET_ENV' in os.environ else 'secret absent'
        usage = len(message['messages']) + 3
        response = {'version': 1, 'type': 'result', 'request': message['request'],
                    'text': text, 'output_digest': sha256(text.encode('utf8')).hexdigest(),
                    'model_digest': model, 'tokenizer_digest': tokenizer,
                    'prompt_tokens': usage, 'generated_tokens': 6,
                    'finish_reason': 'stop'}
        if mode == 'stale_result':
            response['request'] -= 1
        elif mode == 'bad_hash':
            response['output_digest'] = '0' * 64
        elif mode == 'bad_usage':
            response['prompt_tokens'] = 100_000
        elif mode == 'native_role':
            response['tool_calls'] = ['unauthorized']
        elif mode == 'wrong_output_model':
            response['model_digest'] = '9' * 64
        elif mode == 'bad_version':
            response['version'] = 999
        elif mode == 'bad_finish_reason':
            response['finish_reason'] = 'tool_calls'
        elif mode == 'nonint_token':
            response['prompt_tokens'] = True
        write_frame(stdout, response, deadline(), boot['max_frame_bytes'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
