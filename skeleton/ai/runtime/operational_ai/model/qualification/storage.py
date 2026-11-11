"""Atomic no-clobber publication of strictly output-free native model metrics."""
from __future__ import annotations

from hashlib import sha256
import math
import os
from pathlib import Path
import secrets
from .contracts import BurnInPolicy, QualificationHeld, SHA
from .latency import summarize
from ..admission.canonical import canonical
from ..admission.paths import verified_dir


def _exact_keys(value: object, expected: set[str]) -> None:
    # A dict can contain foreign keys with attacker-controlled __eq__/__hash__.
    # Never construct a set or perform a string-key lookup before this check.
    if (type(value) is not dict or len(value) != len(expected)
            or any(type(key) is not str for key in value)):
        raise QualificationHeld('native report contains hostile mapping keys')
    if set(value) != expected:
        raise QualificationHeld('native report has unsupported fields')


def _digest(value: object) -> None:
    if type(value) is not str or len(value) != 64 or SHA.fullmatch(value) is None:
        raise QualificationHeld('invalid native report digest')


def publish_private(root:Path|str,name:str,report:dict)->dict:
    if (type(name) is not str or not name.endswith('.json') or '/' in name
        or '\\' in name or len(name)>100 or name.startswith('.')
        or any(ord(c)<33 for c in name)):
        raise QualificationHeld('private report file name must be a direct JSON child')
    # Validate all mapping keys and bounded collections before membership,
    # dictionary equality or canonical serialization of untrusted reports.
    _exact_keys(report, {
        'schema','status','model_sha256','tokenizer_sha256',
        'policy','summary','trials','claims_excluded'})
    if (type(report['schema']) is not str
        or report['schema'] != 'skeleton.native-gguf-endurance.v1'
        or type(report['status']) is not str
        or report['status'] != 'backend-receipts-observed-not-release-certified'):
        raise QualificationHeld('native report has an unsupported publication schema')
    if (type(report['trials']) is not list or not 1<=len(report['trials'])<=256
        or type(report['claims_excluded']) is not list
        or len(report['claims_excluded']) != 6
        or any(type(value) is not str for value in report['claims_excluded'])):
        raise QualificationHeld('invalid native trial manifest')
    _exact_keys(report['policy'], {
        'trials','max_output_tokens','inference_ms','context_tokens',
        'maximum_p99_ms','maximum_consecutive_faults','minimum_generated_tokens'})
    _exact_keys(report['summary'], {
        'observations','p50_ns','p95_ns','p99_ns','max_ns','total_ns',
        'generated_tokens','generated_tokens_per_second','kind'})
    if report['claims_excluded'] != [
        'model-quality','rights','GPU-qualification',
        'device-compatibility','full-release','consumer-install']:
        raise QualificationHeld('native report must retain all qualification holds')
    _digest(report['model_sha256'])
    _digest(report['tokenizer_sha256'])
    policy = BurnInPolicy(**report['policy'])
    if policy.trials != len(report['trials']):
        raise QualificationHeld('native trial policy is inconsistent')
    summary = report['summary']
    if (type(summary['observations']) is not int
        or summary['observations'] != len(report['trials'])
        or type(summary['kind']) is not str
        or summary['kind'] != 'observed-native-returns-not-sampling-prefill-qualified'):
        raise QualificationHeld('native trial summary is inconsistent')
    for key in ('observations','p50_ns','p95_ns','p99_ns','max_ns',
                'total_ns','generated_tokens'):
        if type(summary[key]) is not int or summary[key] < 0:
            raise QualificationHeld('noncanonical numerical native summary')
    rate = summary['generated_tokens_per_second']
    if type(rate) is not float or not math.isfinite(rate) or rate < 0:
        raise QualificationHeld('noncanonical native response rate')
    trial_keys = {
        'trial','elapsed_ns','prompt_tokens','generated_tokens',
        'output_sha256','finish_reason'}
    times: list[int] = []
    tokens: list[int] = []
    for index, trial in enumerate(report['trials'], start=1):
        _exact_keys(trial, trial_keys)
        if type(trial['trial']) is not int or trial['trial'] != index:
            raise QualificationHeld('noncanonical native trial ordering')
        elapsed = trial['elapsed_ns']
        prompt = trial['prompt_tokens']
        generated = trial['generated_tokens']
        if (type(elapsed) is not int or not 0 < elapsed <= policy.inference_ms*1_000_000
            or type(prompt) is not int or not 0 <= prompt <= policy.context_tokens
            or type(generated) is not int
            or not policy.minimum_generated_tokens <= generated <= policy.max_output_tokens):
            raise QualificationHeld('noncanonical native trial accounting')
        _digest(trial['output_sha256'])
        if type(trial['finish_reason']) is not str or trial['finish_reason'] not in ('stop','length','eos'):
            raise QualificationHeld('unsupported native trial completion')
        times.append(elapsed)
        tokens.append(generated)
    if (summary != summarize(times, tokens)
        or summary['p99_ns'] > policy.maximum_p99_ms*1_000_000):
        raise QualificationHeld('native report metrics disagree with trial receipts')
    raw=canonical(report,maximum=131072)
    root_fd=verified_dir(root)
    temporary='.native-report-'+secrets.token_hex(16)+'.pending'
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,
                   0o600,dir_fd=root_fd)
        try:
            cursor=0
            while cursor<len(raw):
                count=os.write(fd,raw[cursor:])
                if count<=0:raise QualificationHeld('incomplete native report write')
                cursor+=count
            os.fsync(fd)
        finally:
            os.close(fd)
        # A hard-link publish is atomic, unlike writing a partially visible
        # destination file. It never overwrites an existing report, including
        # an existing symlink. Both names refer to the same private inode.
        os.link(temporary,name,src_dir_fd=root_fd,dst_dir_fd=root_fd,follow_symlinks=False)
        os.fsync(root_fd)
    finally:
        try:os.unlink(temporary,dir_fd=root_fd)
        except FileNotFoundError:pass
        finally:os.close(root_fd)
    return {'status':'private-report-atomically-created-no-clobber',
            'report_sha256':sha256(raw).hexdigest(),'bytes':len(raw)}
