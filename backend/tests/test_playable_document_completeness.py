"""Closed markup is mandatory even when a candidate contains every game keyword.

This does not qualify JavaScript syntax or game behavior; those need a separate
browser observation. No model, generated game, or untrusted script is executed.
"""
from copy import deepcopy
import importlib
import json
from types import SimpleNamespace

import pytest

from routes.playable_htmlutils import _extract_html, _sanitize, _validate, passes_playability_gate

SCRIPT = """const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');
let state='menu',score=0,last=performance.now();
addEventListener('pointerdown',()=>state='playing');
function loop(timestamp){const delta=timestamp-last;last=timestamp;
ctx.fillText('Score '+score,10,20);requestAnimationFrame(loop)}
requestAnimationFrame(loop);localStorage.getItem('best');
const dpr=devicePixelRatio;const audio=new AudioContext();
function resize(){canvas.width=innerWidth;canvas.height=innerHeight}resize();
""" + "/* measured fixture padding */" * 60
COMPLETE = '<!DOCTYPE html><html><head><style>body{margin:0}</style></head><body><canvas></canvas><script>' + SCRIPT + '</script></body></html>'
# Same failure shape as actual model checkpoint450f13a8: high keyword score,
# but output ends midway through handleInput(window.event and no raw-text end.
TRUNCATED = COMPLETE.rsplit('</script>', 1)[0] + 'function playGame(){update();handleInput(window.event'


def test_complete_document_retains_weighted_score_without_claiming_execution():
    result = _validate(COMPLETE)
    assert result['score'] >= 70
    assert passes_playability_gate(result, 70)
    assert result['structurally_complete'] is True
    assert result['javascript_syntax_checked'] is False
    assert result['runtime_checked'] is False


@pytest.mark.parametrize('candidate,missing', [
    (TRUNCATED, 'raw_text_complete'),
    (COMPLETE.removesuffix('</html>'), 'document_complete'),
    (COMPLETE.replace('</body>', ''), 'document_complete'),
    ('<!doctype html><html><body><style>canvas{color:red}</body></html>', 'raw_text_complete'),
    ('<!doctype html><html><body><script/>console.log(1);</body></html>', 'raw_text_complete'),
    ('<!doctype html><html><body><style/>canvas{color:red}</body></html>', 'raw_text_complete'),
    ('<!doctype html><html><body/><canvas></canvas></html>', 'document_complete'),
    ('<!doctype html><html><body><script>const fake="</body></html>";', 'document_complete'),
    (COMPLETE.replace('</html>', '<!-- </html> -->'), 'document_complete'),
])
def test_keyword_rich_or_fake_closures_cannot_pass_even_a_lowered_floor(candidate, missing):
    clean, _ = _sanitize(_extract_html(candidate))
    result = _validate(clean)
    assert result['score'] < 70
    assert result['structurally_complete'] is False
    assert missing in result['missing']
    assert passes_playability_gate(result, 1) is False
    assert passes_playability_gate(result, 0) is False


@pytest.mark.parametrize('fragment', [
    '<canvas></canvas><script>function loop(){requestAnimationFrame(loop)',
    '<canvas></canvas><style>canvas{color:red}',
    '<canvas></canvas><script/>function loop(){requestAnimationFrame(loop)',
])
def test_extraction_keeps_truncated_fragment_without_fabricating_document_closures(fragment):
    extracted = _extract_html(fragment)
    assert extracted == fragment
    assert '</html>' not in extracted and '</body>' not in extracted
    assert not passes_playability_gate(_validate(extracted), 0)


def test_complete_fragment_can_still_use_the_existing_document_shell():
    fragment = '<canvas></canvas><script>' + SCRIPT + '</script>'
    extracted = _extract_html(fragment)
    assert extracted.endswith('</body></html>')
    assert passes_playability_gate(_validate(extracted), 70)


@pytest.mark.parametrize('script', [
    'if (key) /[}]/.test(key);',
    'function f(){} /[}]/.test(key);',
    'const literal="unbalanced-looking {[("; // } is a comment',
    'const template=`text with {[( is not code`;'
])
def test_completeness_does_not_pretend_to_parse_javascript_or_reject_valid_regex(script):
    result = _validate(COMPLETE.replace(SCRIPT, SCRIPT + '\n' + script + '\n'))
    assert passes_playability_gate(result, 70)
    assert result['javascript_syntax_checked'] is False


def test_self_closing_looking_script_still_requires_and_accepts_an_actual_end_tag():
    # HTML5 ignores '/' on a non-void script start; the actual close matters.
    result = _validate(COMPLETE.replace('<script>', '<script/>'))
    assert passes_playability_gate(result, 70)


class _Collection:
    def __init__(self, row):
        self.row, self.writes = deepcopy(row), []
    async def find_one(self, *args, **kwargs):
        return deepcopy(self.row)
    async def update_one(self, *args, **kwargs):
        self.writes.append(('update', args, kwargs))
    async def insert_one(self, document):
        self.writes.append(('insert', deepcopy(document)))


@pytest.mark.asyncio
@pytest.mark.parametrize('name,method,extra,result_key', [
    ('edit', '_do_edit', ('finetune', 'Change the color'), 'edited'),
    ('repair', '_do_repair', ('SyntaxError: unexpected end',), 'repaired'),
    ('artwire', '_do_artwire', (), 'applied'),
    ('kbwire', '_do_kbwire', (), 'applied'),
    ('aesthetics', '_do_aesthetics', (), 'applied'),
    ('factions_wire', '_do_factions', (), 'applied'),
    ('physics', '_do_physics', (), 'applied'),
    ('sentience', '_do_sentience', (), 'applied'),
])
async def test_each_mutation_keeps_the_previous_artifact_when_model_output_is_truncated(monkeypatch, name, method, extra, result_key):
    module = importlib.import_module('routes.playable_' + name)
    old = {'playable_id': 'existing', 'html': COMPLETE, 'playability_score': 0, 'brief': 'Original fixture', 'version': 3}
    store = _Collection(old)
    db = SimpleNamespace(playables=store, game_kb=_Collection({'artifacts': {'core_specs': {'title': 'Original'}}}))
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        content = (json.dumps({'schema_version': 1, 'edits': [{'find': '</html>', 'replace': TRUNCATED}]})
                   if name == 'repair' else TRUNCATED)
        return {'content': content, 'model': 'fixture'}
    monkeypatch.setattr(module, '_db', db)
    monkeypatch.setattr(module, '_llm_in_thread', model)
    monkeypatch.setattr(module, 'PLAYABILITY_THRESHOLD', 1)
    if name == 'artwire':
        async def assets(*args, **kwargs):
            return {'hero': 'data:image/png;base64,AA=='}, [{'key': 'hero', 'kind': 'sprite', 'description': 'original'}]
        monkeypatch.setattr(module, '_collect_assets', assets)
    result = await getattr(module, method)('existing', *extra)
    assert result[result_key] is False
    assert 'raw_text_complete' in result['missing']
    assert calls == [1]
    assert store.writes == []
    assert store.row == old


@pytest.mark.asyncio
async def test_derived_partial_is_preserved_as_failed_even_with_a_lowered_score_floor(monkeypatch):
    from routes import playable_derive as module
    old = {'playable_id': 'existing', 'html': COMPLETE, 'playability_score': 90, 'brief': 'Original fixture', 'title': 'Original', 'version': 3}
    store = _Collection(old)
    monkeypatch.setattr(module, '_db', SimpleNamespace(playables=store))
    monkeypatch.setattr(module, 'PLAYABILITY_THRESHOLD', 1)
    async def generation(*args, **kwargs):
        return {'routed': {}, 'html': TRUNCATED, 'removed': [], 'val': _validate(TRUNCATED), 'trail': [], 'evaluation': {'available': False}}
    monkeypatch.setattr(module, '_codegen_quality_loop', generation)
    result = await module._do_derive(old, 'remix', 'Change the color', 'fast')
    assert result['status'] == 'failed'
    inserted = next(row[1] for row in store.writes if row[0] == 'insert')
    assert inserted['status'] == 'failed' and inserted['html'] == TRUNCATED
    assert store.row == old


_MUTATORS = [
    ('edit', '_do_edit', ('finetune', 'Change the color')),
    ('repair', '_do_repair', ('SyntaxError: unexpected end',)),
    ('artwire', '_do_artwire', ()),
    ('kbwire', '_do_kbwire', ()),
    ('aesthetics', '_do_aesthetics', ()),
    ('factions_wire', '_do_factions', ()),
    ('physics', '_do_physics', ()),
    ('sentience', '_do_sentience', ()),
]


def _failing_mutator(monkeypatch, name, method, extra, failure):
    module = importlib.import_module('routes.playable_' + name)
    old = {'playable_id': 'existing', 'html': COMPLETE, 'playability_score': 90,
           'brief': 'Original fixture', 'version': 3}
    store = _Collection(old)
    monkeypatch.setattr(module, '_db', SimpleNamespace(
        playables=store,
        game_kb=_Collection({'artifacts': {'core_specs': {'title': 'Original'}}}),
    ))
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        raise failure
    monkeypatch.setattr(module, '_llm_in_thread', model)
    if name == 'artwire':
        async def assets(*args, **kwargs):
            return {'hero': 'data:image/png;base64,AA=='}, [{'key': 'hero', 'kind': 'sprite', 'description': 'original'}]
        monkeypatch.setattr(module, '_collect_assets', assets)
    return lambda: getattr(module, method)('existing', *extra), store, old, calls


@pytest.mark.asyncio
@pytest.mark.parametrize('name,method,extra', _MUTATORS)
@pytest.mark.parametrize('failure_kind', ['unconfirmed', 'confirmed', 'http403', 'http404'])
async def test_mutator_preserves_typed_model_or_authority_failure_identity(monkeypatch, name, method, extra, failure_kind):
    from fastapi import HTTPException
    from routes.playable import PlayableModelFailure
    if failure_kind.startswith('http'):
        failure = HTTPException(int(failure_kind[4:]), 'PRIVATE-AUTHORITY-DETAIL')
    else:
        failure = PlayableModelFailure('project_model_execution_unconfirmed' if failure_kind == 'unconfirmed'
                                       else 'project_model_transfer_denied',
                                       unconfirmed=failure_kind == 'unconfirmed', request_key='engine-chat:original')
    work, store, old, calls = _failing_mutator(monkeypatch, name, method, extra, failure)
    with pytest.raises(type(failure)) as raised:
        await work()
    assert raised.value is failure
    assert calls == [1]
    assert store.writes == [] and store.row == old


@pytest.mark.asyncio
@pytest.mark.parametrize('name,method,extra', _MUTATORS)
async def test_uncertain_mutator_job_retains_original_nonterminal_custody(monkeypatch, name, method, extra):
    from routes import playable
    failure = playable.PlayableModelFailure('project_model_execution_unconfirmed', unconfirmed=True,
                                           request_key='engine-chat:original')
    work, store, old, calls = _failing_mutator(monkeypatch, name, method, extra, failure)
    jobs = _Collection({'job_id': 'original-job', 'job_status': 'running'})
    monkeypatch.setattr(playable, '_db', SimpleNamespace(playable_jobs=jobs))
    async def authorize(**kwargs):
        return {'owner_id': 'owner', 'tenant_id': 'tenant'}
    monkeypatch.setattr(playable, 'reauthorize_project_context', authorize)
    await playable._run_job('original-job', work())
    assert calls == [1] and store.writes == [] and store.row == old
    assert len(jobs.writes) == 1
    result = jobs.writes[0][1][1]['$set']
    assert result['job_status'] == 'unconfirmed'
    assert result['engine_request_key'] == 'engine-chat:original'
    assert result['retry_same_request'] is True
    assert not any(key in result for key in ('repaired', 'applied', 'edited', 'playable_id'))


@pytest.mark.asyncio
@pytest.mark.parametrize('name,method,extra', _MUTATORS)
@pytest.mark.parametrize('status', [403, 404])
async def test_revoked_mutator_cannot_publish_job_completion_or_late_artifact(monkeypatch, name, method, extra, status):
    from fastapi import HTTPException
    from routes import playable
    failure = HTTPException(status, 'PRIVATE-REVOKED-SOURCE')
    work, store, old, calls = _failing_mutator(monkeypatch, name, method, extra, failure)
    jobs = _Collection({'job_id': 'original-job', 'job_status': 'running'})
    monkeypatch.setattr(playable, '_db', SimpleNamespace(playable_jobs=jobs))
    async def authorize(**kwargs):
        return {'owner_id': 'owner', 'tenant_id': 'tenant'}
    monkeypatch.setattr(playable, 'reauthorize_project_context', authorize)
    with pytest.raises(HTTPException) as raised:
        await playable._run_job('original-job', work())
    assert raised.value is failure
    assert calls == [1] and jobs.writes == [] and store.writes == [] and store.row == old
