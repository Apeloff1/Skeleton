"""Atomic no-clobber publication of strictly output-free native model metrics."""
from __future__ import annotations
from hashlib import sha256
import os
from pathlib import Path
import secrets
from .contracts import QualificationHeld
from ..admission.canonical import canonical
from ..admission.paths import verified_dir


def publish_private(root:Path|str,name:str,report:dict)->dict:
    if (not isinstance(name,str) or not name.endswith('.json') or '/' in name
        or '\\' in name or len(name)>100 or name.startswith('.')
        or any(ord(c)<33 for c in name)):
        raise QualificationHeld('private report file name must be a direct JSON child')
    # No arbitrary text values accepted at this publication boundary. A caller
    # cannot accidentally persist raw prompts, completions, or API credentials.
    if (type(report) is not dict or set(report)!={
        'schema','status','model_sha256','tokenizer_sha256',
        'policy','summary','trials','claims_excluded'}
        or report['schema']!='skeleton.native-gguf-endurance.v1'
        or report['status']!='backend-receipts-observed-not-release-certified'):
        raise QualificationHeld('native report has an unsupported publication schema')
    if (type(report['trials']) is not list or not 1<=len(report['trials'])<=256
        or type(report['claims_excluded']) is not list or not isinstance(report['summary'],dict)
        or not isinstance(report['policy'],dict)):
        raise QualificationHeld('invalid native trial manifest')
    from ..admission.contracts import sha256 as require_sha
    require_sha(report['model_sha256'],'report model')
    require_sha(report['tokenizer_sha256'],'report tokenizer')
    policy_keys={'trials','max_output_tokens','inference_ms','context_tokens',
                 'maximum_p99_ms','maximum_consecutive_faults','minimum_generated_tokens'}
    summary_keys={'observations','p50_ns','p95_ns','p99_ns','max_ns','total_ns',
                  'generated_tokens','generated_tokens_per_second','kind'}
    if set(report['policy'])!=policy_keys or set(report['summary'])!=summary_keys:
        raise QualificationHeld('native report policy or summary contains unknown fields')
    if report['claims_excluded']!=['model-quality','rights','GPU-qualification',
            'device-compatibility','full-release','consumer-install']:
        raise QualificationHeld('native report must retain all qualification holds')
    if (type(report['summary']['observations']) is not int
        or report['summary']['observations']!=len(report['trials'])
        or type(report['policy']['trials']) is not int
        or report['policy']['trials']!=len(report['trials'])
        or report['summary']['kind']!='observed-native-returns-not-sampling-prefill-qualified'):
        raise QualificationHeld('native trial summary is inconsistent')
    for key in (summary_keys-{'kind','generated_tokens_per_second'}):
        value=report['summary'][key]
        if type(value)is not int or value<0:
            raise QualificationHeld('noncanonical numerical native summary')
    rate=report['summary']['generated_tokens_per_second']
    import math
    if type(rate) not in (float,int) or not math.isfinite(rate) or rate<0:
        raise QualificationHeld('noncanonical native response rate')
    for key in policy_keys:
        if type(report['policy'][key])is not int or report['policy'][key]<0:
            raise QualificationHeld('noncanonical native probe configuration')
    trial_keys={'trial','elapsed_ns','prompt_tokens','generated_tokens','output_sha256','finish_reason'}
    for index,t in enumerate(report['trials'],start=1):
        if type(t) is not dict or set(t)!=trial_keys:
            raise QualificationHeld('native trial may contain an unauthorized disclosure')
        if type(t['trial'])is not int or t['trial']!=index:
            raise QualificationHeld('noncanonical native trial ordering')
        for key in ('elapsed_ns','prompt_tokens','generated_tokens'):
            if type(t[key])is not int or t[key]<0:
                raise QualificationHeld('noncanonical native trial accounting')
        require_sha(t['output_sha256'],'native output')
        if t['finish_reason'] not in ('stop','length','eos'):
            raise QualificationHeld('unsupported native trial completion')
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
