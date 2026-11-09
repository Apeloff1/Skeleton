"""Read-only structural verification of operator-issued qualification receipt."""
from __future__ import annotations
from hashlib import sha256
from ...orchestration.execution_spine.contracts import canonical,hexdigest
from .contracts import QualificationError

FIELDS={'schema','model_sha256','tokenizer_sha256','session_sha256','request_id_sha256',
        'request_sha256','output_sha256','transcript_sha256','revision',
        'generated_tokens','prompt_tokens','context_sha256',
        'replay_without_regeneration','database_turns','checkpoint_execution_mode',
        'status','proof_sha256'}


def verify(record:dict, *, require_real:bool=True)->dict:
    if type(record) is not dict or set(record)!=FIELDS:
        raise QualificationError('qualification report schema mismatch')
    if record['schema']!='skeleton.ai.first-boot-qualification.v1':
        raise QualificationError('unknown qualification report schema')
    for key in ('model_sha256','tokenizer_sha256','session_sha256','request_id_sha256',
                'request_sha256','output_sha256','transcript_sha256','context_sha256','proof_sha256'):
        hexdigest(record[key],key)
    for key in ('revision','generated_tokens','prompt_tokens','database_turns'):
        if type(record[key])is not int or record[key]<0:
            raise QualificationError('invalid numeric qualification evidence')
    if record['replay_without_regeneration'] is not True:
        raise QualificationError('restart replay was not proven')
    is_real=record['checkpoint_execution_mode']=='actual-gguf-llama-cpp' and record['status']=='real-first-boot-replay-probe-not-release-certified'
    is_fixture=record['checkpoint_execution_mode']=='injected-test-double' and record['status']=='fixture-only-not-production-certified'
    if not (is_real or is_fixture):
        raise QualificationError('unsupported checkpoint execution provenance')
    if require_real and not is_real:
        raise QualificationError('fixture cannot satisfy real-model qualification')
    expected=sha256(canonical({key:value for key,value in record.items() if key!='proof_sha256'})).hexdigest()
    if expected!=record['proof_sha256']:
        raise QualificationError('qualification proof digest mismatch')
    return {'status':'structurally-valid-receipt-no-external-attestation',
            'real_model_executed':is_real,'proof_sha256':expected}
