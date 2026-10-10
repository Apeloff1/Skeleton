from skeleton.kv.prefix_cache import *


def key(scope="p", instruction="i", prompt="q", model="m", tokenizer="tok", version="v1"):
    return PrefixCacheKey(instruction, prompt, model, tokenizer, version, scope)


def test_instruction_or_scope_drift_blocks_reuse():
    artifact = PrefixArtifact(key(), True)
    assert not can_reuse(
        artifact,
        key(instruction="other"),
        {"p"},
    ).reusable
    assert not can_reuse(artifact, key(), set()).reusable


def test_nonsensitive_prefix_still_requires_scope_authorization():
    cache_key = key(scope="private", prompt="p", tokenizer="t", version="v")
    assert not can_reuse(PrefixArtifact(cache_key, False), cache_key, set()).reusable


def test_model_tokenizer_version_and_prompt_are_identity_bound():
    artifact = PrefixArtifact(key(), False)
    for candidate in (
        key(model="other"),
        key(tokenizer="other"),
        key(version="v2"),
        key(prompt="other"),
    ):
        assert not can_reuse(artifact, candidate, {"p"}).reusable


def test_string_scope_container_is_rejected_instead_of_substring_authorized():
    artifact = PrefixArtifact(key(scope="private"), False)
    decision = can_reuse(artifact, artifact.key, "private")
    assert not decision.reusable
    assert decision.reason == "invalid authorized scopes"
