"""Untrusted repair data stays source-bound, atomic and within finite limits."""
from dataclasses import FrozenInstanceError
import hashlib
import json

import pytest

from core import playable_literal_patch as patch
from skeleton.automation.build_edits import FileEditPlan
from skeleton.skills.tool_contract import validate_json_schema, validate_json_value


def digest(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def proposal(edits, source=None, **extra):
    result = {'schema_version': 1, 'edits': [{'find': a, 'replace': b} for a, b in edits]}
    if source is not None:
        result['source_sha256'] = digest(source)
    return json.dumps({**result, **extra}, ensure_ascii=False)


def apply(source, edits, **extra):
    return patch.apply_literal_patch(source, proposal(edits, **extra), expected_source_sha256=digest(source))


def test_unique_anchors_apply_via_canonical_plans_in_descending_original_positions(monkeypatch):
    source = 'const best=0; const score=1;'
    real, calls = patch.apply_edit_plan, []
    def canonical(content, plan, *, budget):
        assert isinstance(plan, FileEditPlan)
        calls.append((content, plan, budget))
        return real(content, plan, budget=budget)
    monkeypatch.setattr(patch, 'apply_edit_plan', canonical)
    result = apply(source, [('const best=0;', 'let best=0;'), ('const score=1;', 'let score=2;')])
    assert result.candidate == 'let best=0; let score=2;'
    assert [call[1].edits[0].anchor for call in calls] == ['const score=1;', 'const best=0;']
    assert len(calls) == result.edit_count == 2
    assert all(call[2].max_files == 1 and call[2].max_file_bytes == 65536 for call in calls)
    assert result.before_digest == digest(source)
    assert result.after_digest == digest(result.candidate)
    assert result.evidence[0].before_digest == result.before_digest
    assert result.evidence[-1].after_digest == result.after_digest
    assert result.evidence[0].after_digest == result.evidence[1].before_digest
    assert result.patch_fingerprint == apply(source, [('const score=1;', 'let score=2;'), ('const best=0;', 'let best=0;')]).patch_fingerprint
    with pytest.raises(FrozenInstanceError):
        result.candidate = 'changed'
    with pytest.raises(FrozenInstanceError):
        result.evidence[0].before_digest = 'changed'


@pytest.mark.parametrize('echo', [False, True])
def test_source_digest_is_server_owned_and_optional_correct_model_echo_is_accepted(echo):
    source = 'const bestScore = 0;'
    response = proposal([('const bestScore', 'let bestScore')], source=source if echo else None)
    result = patch.apply_literal_patch(source, response, expected_source_sha256=digest(source))
    assert result.candidate == 'let bestScore = 0;'


@pytest.mark.parametrize('source,response,expected', [
    ('abc', proposal([('a', 'A')]), '0' * 64),
    ('abc', proposal([('a', 'A')], source_sha256='0' * 64), digest('abc')),
    ('abc', proposal([('a', 'A')]), 'X' * 64),
    ('abc', proposal([('a', 'A')], source_sha256=True), digest('abc')),
])
def test_source_mismatch_or_invalid_digest_never_runs_edit_engine(monkeypatch, source, response, expected):
    def forbidden(*args, **kwargs):
        raise AssertionError('Edit owner must not run for an unbound source')
    monkeypatch.setattr(patch, 'apply_edit_plan', forbidden)
    with pytest.raises(patch.LiteralPatchError):
        patch.apply_literal_patch(source, response, expected_source_sha256=expected)


@pytest.mark.parametrize('source,edits,code', [
    ('abc', [('x', 'y')], 'literal_patch_anchor_missing'),
    ('aaaa', [('aaa', 'X')], 'literal_patch_anchor_ambiguous'),
    ('same same', [('same', 'different')], 'literal_patch_anchor_ambiguous'),
    ('abcdef', [('abc', 'X'), ('bcde', 'Y')], 'literal_patch_overlapping_edits'),
    ('abcdef', [('abc', 'X'), ('abc', 'Y')], 'literal_patch_duplicate_edit'),
    ('abcdef', [('abc', 'abc')], 'literal_patch_no_change'),
    ('abcdef', [('', 'x')], 'literal_patch_invalid_text'),
])
def test_original_anchors_must_be_unique_including_overlaps_and_ranges_disjoint(source, edits, code):
    with pytest.raises(patch.LiteralPatchError) as error:
        apply(source, edits)
    assert error.value.code == code


def test_all_original_edits_are_prevalidated_before_any_edit_can_apply(monkeypatch):
    calls = []
    monkeypatch.setattr(patch, 'apply_edit_plan', lambda *args, **kwargs: calls.append(1))
    source = 'unique A and unique B'
    with pytest.raises(patch.LiteralPatchError, match='literal_patch_anchor_missing'):
        apply(source, [('unique A', 'changed A'), ('missing B', 'changed B')])
    assert source == 'unique A and unique B' and calls == []


def test_replacement_created_ambiguity_is_rejected_without_retargeting_or_partial_result():
    source = 'one -- two'
    with pytest.raises(patch.LiteralPatchError, match='literal_patch_anchor_ambiguous'):
        apply(source, [('one', 'ONE'), ('two', 'one')])
    assert source == 'one -- two'


def test_replacement_created_overlapping_ambiguity_is_also_rejected():
    # Replacing b on the right creates aaa at positions0 and1. Canonical
    # str.count('aaa') would report one, but this adapter must reject both.
    source = 'aaab'
    with pytest.raises(patch.LiteralPatchError, match='literal_patch_anchor_ambiguous'):
        apply(source, [('aaa', 'Z'), ('b', 'a')])
    assert source == 'aaab'


def test_unicode_whitespace_and_delete_edits_preserve_exact_untouched_bytes():
    source = '  const récolte = "🐲";\nkeep();\n'
    result = apply(source, [('const récolte', 'let récolte'), ('keep();\n', '')])
    assert result.candidate == '  let récolte = "🐲";\n'
    assert result.before_digest == digest(source) and result.after_digest == digest(result.candidate)


@pytest.mark.parametrize('response', [
    '', 'not json', '```json\n{}\n```', '[]', '{}',
    '{"schema_version":1,"schema_version":1,"edits":[{"find":"a","replace":"b"}]}',
    '{"schema_version":1,"edits":[{"find":"a","find":"a","replace":"b"}]}',
    '{"schema_version":1,"edits":[{"find":"a","replace":NaN}]}',
    '{"schema_version":1,"edits":[{"find":"a","replace":Infinity}]}',
    '{"schema_version":1e999,"edits":[]}',
    proposal([('a', 'b')], schema_version=True),
    proposal([('a', 'b')], schema_version=1.0),
    proposal([('a', 'b')], extra='PRIVATE-CONTENT'),
    '{"schema_version":1,"edits":[{"find":"a","replace":"b","extra":"PRIVATE-CONTENT"}]}',
    '{"schema_version":1,"edits":[{"find":"a"}]}',
    '{"schema_version":1,"edits":[]}',
    '{"schema_version":1,"edits":{}}',
    '{"schema_version":1,"edits":[{"find":"a","replace":true}]}',
    '{"schema_version":1,"edits":[{"find":"a","replace":"\\u0000"}]}',
    '{"schema_version":1,"edits":[{"find":"a","replace":"\\ud800"}]}',
    b'\xff', '\ud800',
])
def test_strict_json_schema_unicode_and_duplicate_field_failures_are_content_free(response):
    with pytest.raises(patch.LiteralPatchError) as error:
        patch.apply_literal_patch('a PRIVATE-CONTENT', response, expected_source_sha256=digest('a PRIVATE-CONTENT'))
    assert error.value.code.startswith('literal_patch_')
    assert 'PRIVATE-CONTENT' not in str(error.value)
    assert 'find' not in str(error.value) and 'replace' not in str(error.value)


@pytest.mark.parametrize('source,edits', [
    ('a' * 65537, [('a', 'b')]),
    ('🐲' * 16385, [('🐲', 'b')]),
    ('x' * 4097, [('x' * 4097, 'b')]),
    ('🐲' * 1025, [('🐲' * 1025, 'b')]),
    ('a', [('a', '🐲' * 1025)]),
    ('a', [('a', 'b' * 4097)]),
], ids=['ascii-source-limit','utf8-source-limit','ascii-anchor-limit','utf8-anchor-limit','utf8-replacement-limit','ascii-replacement-limit'])
def test_source_anchor_and_replacement_limits_count_utf8_bytes(source, edits):
    with pytest.raises(patch.LiteralPatchError, match='literal_patch_limit_exceeded'):
        apply(source, edits)


def test_response_total_edit_and_candidate_limits_remain_finite():
    source = 'a'
    with pytest.raises(patch.LiteralPatchError, match='literal_patch_limit_exceeded'):
        patch.apply_literal_patch(source, proposal([('a', 'b')]) + ' ' * 32768, expected_source_sha256=digest(source))
    with pytest.raises(patch.LiteralPatchError, match='literal_patch_invalid_edits'):
        apply('012345678', [(str(i), 'x') for i in range(9)])
    anchors = [str(i) * 2048 for i in range(5)]
    with pytest.raises(patch.LiteralPatchError, match='literal_patch_limit_exceeded'):
        apply('|'.join(anchors), [(anchor, 'x' * 2048) for anchor in anchors])
    with pytest.raises(patch.LiteralPatchError):
        apply('a' + 'b' * 65535, [('a', 'x' * 4096)])


def test_exact_byte_and_edit_count_boundaries_are_accepted():
    source = 'A' + 'x' * 65535
    response = proposal([('A', 'B')])
    response += ' ' * (patch.MAX_RESPONSE_BYTES - len(response.encode('utf-8')))
    result = patch.apply_literal_patch(source, response, expected_source_sha256=digest(source))
    assert len(result.candidate.encode('utf-8')) == patch.MAX_CANDIDATE_BYTES
    assert result.candidate == 'B' + 'x' * 65535
    assert apply('01234567', [(str(i), 'x') for i in range(8)]).candidate == 'x' * 8
    assert apply('🐲' * 1024, [('🐲' * 1024, 'kept')]).candidate == 'kept'
    anchors = [str(i) * 2048 for i in range(4)]
    edits = [(anchor, chr(65 + i) * 2048) for i, anchor in enumerate(anchors)]
    assert sum(len(a.encode()) + len(b.encode()) for a, b in edits) == patch.MAX_TOTAL_EDIT_BYTES
    assert apply('|'.join(anchors), edits).edit_count == 4


def test_extra_response_data_and_regex_or_fuzzy_anchors_are_rejected():
    source = 'actual source'
    with pytest.raises(patch.LiteralPatchError, match='literal_patch_invalid_json'):
        patch.apply_literal_patch(source, proposal([('actual', 'new')]) + '{}', expected_source_sha256=digest(source))
    for anchor in ('.*', 'ACTUAL', 'actual  source'):
        with pytest.raises(patch.LiteralPatchError, match='literal_patch_anchor_missing'):
            apply(source, [(anchor, 'new')])


def test_unexpected_canonical_error_is_atomic_and_does_not_leak_source(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE-CANONICAL-CONTENT')
    monkeypatch.setattr(patch, 'apply_edit_plan', fail)
    source = 'one'
    with pytest.raises(patch.LiteralPatchError) as error:
        apply(source, [('one', 'ONE')])
    assert error.value.code == 'literal_patch_apply_failed'
    assert 'PRIVATE' not in str(error.value) and source == 'one'


def test_exported_response_schema_accepts_optional_echo_but_not_unknown_keys():
    valid = json.loads(proposal([('a', 'b')]))
    validate_json_schema(patch.RESPONSE_SCHEMA)
    validate_json_value(patch.RESPONSE_SCHEMA, valid)
    validate_json_value(patch.RESPONSE_SCHEMA, {**valid, 'source_sha256': digest('a')})
    with pytest.raises(ValueError):
        validate_json_value(patch.RESPONSE_SCHEMA, {**valid, 'unknown': 'value'})
