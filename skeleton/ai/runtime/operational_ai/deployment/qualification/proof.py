"""Privacy-preserving qualification evidence digest; not a model quality claim."""
from __future__ import annotations
import hashlib, json
from ...orchestration.execution_spine.contracts import canonical,hexdigest
from .contracts import QualificationError


def construct(model: str, tokenizer: str, session: str,
              request: str, first: dict, replayed: dict,
              history: tuple[dict, ...], diagnostics: dict,
              *, exact_native: bool) -> dict:
    hexdigest(model, 'model digest');hexdigest(tokenizer, 'tokenizer digest')
    if type(exact_native) is not bool:
        raise QualificationError('qualification backend proof missing')
    if not isinstance(first,dict) or not isinstance(replayed,dict):
        raise QualificationError('missing inference receipts')
    if first.get('replayed') is not False or replayed.get('replayed') is not True:
        raise QualificationError('restarted invocation did not prove replay')
    if first.get('revision') != 1 or replayed.get('revision') != first['revision']:
        raise QualificationError('replay changed conversation revision')
    if first.get('output_sha256') != replayed.get('output_sha256'):
        raise QualificationError('inference output changed across restart')
    if first.get('request_sha256') != replayed.get('request_sha256'):
        raise QualificationError('request identity changed across restart')
    if len(history) != 2 or history[0].get('role') != 'user' or history[1].get('role') != 'assistant':
        raise QualificationError('committed transcript did not replay exactly')
    if hashlib.sha256(history[1]['content'].encode('utf8')).hexdigest()!=first['output_sha256']:
        raise QualificationError('durable output does not match generation receipt')
    if not isinstance(diagnostics,dict) or diagnostics.get('turns') != 1:
        raise QualificationError('database integrity doctor did not prove the turn')
    proof = {
        'schema':'skeleton.ai.first-boot-qualification.v1',
        'model_sha256':model,'tokenizer_sha256':tokenizer,
        'session_sha256':hashlib.sha256(session.encode('ascii')).hexdigest(),
        'request_id_sha256':hashlib.sha256(request.encode('ascii')).hexdigest(),
        'request_sha256':first['request_sha256'],
        'output_sha256':first['output_sha256'],
        'transcript_sha256':hashlib.sha256(canonical(history)).hexdigest(),
        'revision':first['revision'],
        'generated_tokens':first['generated_tokens'],
        'prompt_tokens':first['prompt_tokens'],
        'context_sha256':first['context_sha256'],
        'replay_without_regeneration':True,
        'database_turns':diagnostics['turns'],
        'checkpoint_execution_mode':'actual-gguf-llama-cpp' if exact_native else 'injected-test-double',
        'status':'real-first-boot-replay-probe-not-release-certified' if exact_native else 'fixture-only-not-production-certified',
    }
    proof['proof_sha256']=hashlib.sha256(canonical(proof)).hexdigest()
    return proof
