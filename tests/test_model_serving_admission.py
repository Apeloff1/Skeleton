from skeleton.ai.model_serving.admission import ServingPolicy, admit


def test_admission():
    policy = ServingPolicy('sha256:model', 'sha256:eval', 'local', 4096, 512)
    base = dict(model_digest='sha256:model', evaluation_digest='sha256:eval',
                backend='local', context_tokens=100, output_tokens=10)
    assert admit(policy, **base)
    for change in ({'model_digest': 'other'}, {'evaluation_digest': ''},
                   {'backend': 'remote'}, {'context_tokens': 4097},
                   {'output_tokens': 513}, {'output_tokens': 0},
                   {'context_tokens': -1}, {'context_tokens': True}):
        assert not admit(policy, **(base | change))
    assert not admit(ServingPolicy('', 'sha256:eval', 'local', 4096, 512), **base)
