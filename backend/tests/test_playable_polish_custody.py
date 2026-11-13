"""The finite polish chain cannot advance after uncertain or revoked work."""
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from routes import playable, playable_polish


class _Jobs:
    def __init__(self):
        self.writes = []
    async def update_one(self, query, update):
        self.writes.append((query, update))


def _chain(monkeypatch, failure, fail_index=0):
    calls, artifacts = [], ['original-artifact']
    jobs = _Jobs()
    monkeypatch.setattr(playable_polish, '_db', SimpleNamespace(playable_jobs=jobs))
    steps = []
    for index, name in enumerate(('sentience', 'physics', 'aesthetics')):
        async def step(pid, index=index, name=name):
            calls.append((name, pid))
            if index == fail_index:
                raise failure
            artifacts.append(name + '-confirmed')
            return {'applied': True, 'version': 4 + index, 'score': 90 + index}
        steps.append((name, name.title(), step))
    monkeypatch.setattr(playable_polish, '_STEPS', steps)
    return jobs, calls, artifacts


def _failure(kind):
    if kind.startswith('http'):
        return HTTPException(int(kind[4:]), 'PRIVATE-AUTHORITY-DETAIL')
    return playable.PlayableModelFailure(
        'project_model_execution_unconfirmed' if kind == 'unconfirmed' else 'project_model_transfer_denied',
        unconfirmed=kind == 'unconfirmed', request_key='engine-chat:original-polish-step',
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['unconfirmed', 'confirmed', 'http403', 'http404'])
@pytest.mark.parametrize('fail_index', [0, 1])
async def test_typed_step_failure_stops_chain_without_another_model_or_helper_call(monkeypatch, kind, fail_index):
    failure = _failure(kind)
    jobs, calls, artifacts = _chain(monkeypatch, failure, fail_index)
    with pytest.raises(type(failure)) as raised:
        await playable_polish._do_polish('game', 'original-job')
    assert raised.value is failure
    assert calls == [(name, 'game') for name in ('sentience', 'physics')[:fail_index + 1]]
    assert artifacts == ['original-artifact'] + (['sentience-confirmed'] if fail_index else [])
    assert len(jobs.writes) == fail_index + 1
    assert all('job_status' not in update['$set'] for _, update in jobs.writes)
    assert jobs.writes[-1][1]['$set']['step'] == fail_index + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['unconfirmed', 'http403', 'http404'])
@pytest.mark.parametrize('fail_index', [0, 1])
async def test_polish_shared_runner_retains_uncertainty_and_rethrows_authority_denials(monkeypatch, kind, fail_index):
    failure = _failure(kind)
    jobs, calls, artifacts = _chain(monkeypatch, failure, fail_index)
    monkeypatch.setattr(playable, '_db', SimpleNamespace(playable_jobs=jobs))
    async def authorize(**kwargs):
        return {'owner_id': 'owner', 'tenant_id': 'tenant'}
    monkeypatch.setattr(playable, 'reauthorize_project_context', authorize)
    if kind == 'unconfirmed':
        await playable._run_job('original-job', playable_polish._do_polish('game', 'original-job'))
        terminal = jobs.writes[-1]
        assert terminal[0] == {'job_id': 'original-job'}
        update = terminal[1]['$set']
        assert update['job_status'] == 'unconfirmed'
        assert update['engine_request_key'] == 'engine-chat:original-polish-step'
        assert update['retry_same_request'] is True
        assert not any(key in update for key in ('applied', 'count', 'playable_id'))
    else:
        with pytest.raises(HTTPException) as raised:
            await playable._run_job('original-job', playable_polish._do_polish('game', 'original-job'))
        assert raised.value is failure
    assert calls == [(name, 'game') for name in ('sentience', 'physics')[:fail_index + 1]]
    assert artifacts == ['original-artifact'] + (['sentience-confirmed'] if fail_index else [])
    assert not any(update['$set'].get('job_status') == 'done' for _, update in jobs.writes)


@pytest.mark.asyncio
async def test_ordinary_confirmed_step_failure_is_still_skipped_in_the_finite_three_step_chain(monkeypatch):
    jobs, calls, artifacts = _chain(monkeypatch, RuntimeError('PRIVATE-UNEXPECTED-DETAIL'))
    result = await playable_polish._do_polish('game', 'original-job')
    assert calls == [('sentience', 'game'), ('physics', 'game'), ('aesthetics', 'game')]
    assert len(jobs.writes) == 3
    assert result['skipped'] == ['sentience']
    assert result['applied'] == ['physics', 'aesthetics']
    assert result['count'] == 2 and result['version'] == 6
    assert result['steps'][0]['error'] == 'polish_step_failed'
    assert 'PRIVATE-UNEXPECTED-DETAIL' not in str(result)
    assert artifacts == ['original-artifact', 'physics-confirmed', 'aesthetics-confirmed']
