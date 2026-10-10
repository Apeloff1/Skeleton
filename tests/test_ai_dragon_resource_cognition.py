from dataclasses import replace
from datetime import datetime, timezone
import sqlite3
from uuid import uuid4

import pytest
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample, SessionTask, DragonResourceSession, plan_resources
from skeleton.ai.webcrawler.dragon_reasoning_matrix import Truth, EvidenceFact, MatrixRule, evaluate_matrix, conjunction, disjunction, exception_action
from skeleton.ai.webcrawler.dragon_microknowledge import DragonMicroKnowledge
from skeleton.ai.webcrawler.dragon_knowledge_graph import DragonKnowledgeGraph, KnowledgeConcept
from skeleton.ai.webcrawler.dragon_conversation_micro_logs import DragonConversationMicroLogs
from skeleton.ai.webcrawler.dragon_companion_runtime import DragonCognitionSession
from skeleton.contracts.conversation import ConversationThread, ConversationMessage, ConversationAuthorType


def hardware(**kw):
    return replace(HardwareSample(256 * 1024**2, 4, .1, .9, True, False, 10), **kw)


@pytest.mark.parametrize('changes,reason', [({'sampled_at': 0}, 'stale_telemetry'),
    ({'thermal_limited': True}, 'thermal_or_pressure'), ({'pressure': .96}, 'thermal_or_pressure'),
    ({'available_memory_bytes': 1024}, 'memory_reserve')])
def test_hardware_defers(changes, reason):
    plan = plan_resources(hardware(**changes), now=10, foreground=True)
    assert plan.memory_bytes == 0 and plan.effort == 'defer' and plan.reason == reason


def test_battery_background_and_foreground():
    sample = hardware(battery_fraction=.1, charging=False)
    assert not plan_resources(sample, now=10, foreground=False).background_allowed
    assert plan_resources(sample, now=10, foreground=True).memory_bytes > 0


@pytest.mark.parametrize('field,value', [('pressure', float('nan')), ('cpu_units', True),
    ('available_memory_bytes', -1), ('charging', 1), ('battery_fraction', 2)])
def test_invalid_hardware(field, value):
    with pytest.raises(ValueError):
        hardware(**{field: value})


def test_background_reservation_not_released_until_stopped():
    session = DragonResourceSession()
    bg = SessionTask('learn', 'acquisition', 16 * 1024**2, 1)
    assert session.dispatch((bg,), hardware(), now=10).admitted == ('learn',)
    user = SessionTask('chat', 'user', 16 * 1024**2, 2)
    decision = session.dispatch((user,), hardware(), now=10)
    assert not decision.foreground_ready and decision.checkpoint_requested == ('learn',)
    assert decision.reason == 'draining_background'
    session.stopped('learn')
    assert session.dispatch((user,), hardware(), now=10).foreground_ready
    with pytest.raises(ValueError):
        session.dispatch((user,), hardware(), now=10)


def test_foreground_does_not_launch_background():
    session = DragonResourceSession()
    tasks = (SessionTask('chat', 'user', 1024, 1), SessionTask('train', 'training', 1024, 1))
    assert session.dispatch(tasks, hardware(), now=10).admitted == ('chat',)


@pytest.mark.parametrize('v', list(Truth))
def test_logic_unknown_not_false(v):
    assert conjunction((Truth.TRUE, v)) == v
    assert disjunction((Truth.FALSE, v)) == v


def test_exception_unknown_blocks_even_when_proposal_true():
    rule = MatrixRule('release', ('built',), unless=('rights_block',), required_slots=('this',))
    facts = (EvidenceFact('built', Truth.TRUE, 'build_receipt', 20),)
    d = evaluate_matrix(rule, facts, {'this': 'artifact'}, now=10, genre='rpg', era='1990', engine='nes')
    assert not d.eligible and 'rights_block' in d.missing and d.search_queries
    clear = facts + (EvidenceFact('rights_block', Truth.FALSE, 'human_review', 20),)
    assert evaluate_matrix(rule, clear, {'this': 'artifact'}, now=10, genre='rpg', era='1990', engine='nes').eligible
    assert not evaluate_matrix(rule, clear, {}, now=10, genre='rpg', era='1990', engine='nes').eligible
    assert not evaluate_matrix(rule, clear, {'this': 'artifact'}, now=21, genre='rpg', era='1990', engine='nes').eligible


def test_exception_retries_bounded():
    assert exception_action('transient_network', 0)[1]
    assert not exception_action('transient_network', 2)[1]
    assert not exception_action('rights', 0)[1]
    assert exception_action('novel', 0) == ('stop_operator_review', False)


def knowledge():
    db = sqlite3.connect(':memory:')
    graph = DragonKnowledgeGraph(db)
    graph.put_concept('a', KnowledgeConcept('jump', 'gameplay', 'Original jump physics with bounded velocity.'), authorized=True)
    graph.put_concept('a', KnowledgeConcept('modern', 'gameplay', 'Jump physics on a modern engine.'), authorized=True)
    store = DragonMicroKnowledge(graph)
    store.index('a', 'jump', {'era': '1990', 'genre': 'platformer'}, evidence_ref='source_ref', expires_at=30, authorized=True)
    store.index('a', 'modern', {'era': '2020', 'genre': 'platformer'}, evidence_ref='modern_ref', expires_at=30, authorized=True)
    return db, graph, store


def test_microknowledge_facets_expiry_scope_and_budget():
    db, graph, store = knowledge()
    plan = plan_resources(hardware(), now=10, foreground=True)
    hit = store.retrieve('a', 'jump physics', {'era': '1990'}, plan, now=10, authorized=True)
    assert [h.concept_id for h in hit.hits] == ['jump']
    assert hit.bytes_used <= plan.context_bytes and hit.hits[0].trust == 'untrusted_reference'
    assert not store.retrieve('b', 'jump', {}, plan, now=10, authorized=True).hits
    assert not store.retrieve('a', 'jump', {}, plan, now=40, authorized=True).hits
    assert not store.retrieve('a', 'jump', {}, replace(plan, context_bytes=8), now=10, authorized=True).hits
    with pytest.raises(PermissionError):
        store.retrieve('a', 'jump', {}, plan, now=10, authorized=False)
    with pytest.raises(ValueError):
        store.index('b', 'jump', {}, evidence_ref='ref', expires_at=20, authorized=True)
    store.remove('a', 'jump', authorized=True)
    assert not store.retrieve('a', 'jump', {'era': '1990'}, plan, now=10, authorized=True).hits


def test_projection_corruption_fails_closed():
    db, graph, store = knowledge()
    db.execute("UPDATE dragon_knowledge_concepts SET statement='Changed jump' WHERE concept_id='jump'")
    with pytest.raises(ValueError, match='drift'):
        store.retrieve('a', 'jump', {'era': '1990'}, plan_resources(hardware(), now=10, foreground=True), now=10, authorized=True)


def test_indexed_query_plan_uses_covering_postings():
    db, _, _ = knowledge()
    plan = db.execute("EXPLAIN QUERY PLAN SELECT concept_id FROM dragon_micro_postings WHERE owner=? AND term=?", ('a', 'jump')).fetchall()
    assert any('COVERING INDEX' in str(row) for row in plan)


def thread_window():
    now = datetime.now(timezone.utc)
    thread = ConversationThread(str(uuid4()), 'tenant', 'a', now, now, 1, 10, str(uuid4()))
    messages = tuple(ConversationMessage(str(uuid4()), thread.thread_id, thread.active_branch_id,
        i, ConversationAuthorType.USER, now, f'step-{i}', content='private raw transcript') for i in range(1, 11))
    return thread, messages


def test_ten_step_projection_disk_reopen_and_privacy(tmp_path):
    path = tmp_path / 'existing-owner.sqlite'
    db = sqlite3.connect(path)
    store = DragonConversationMicroLogs(db)
    thread, messages = thread_window()
    digest = store.checkpoint(thread, messages, {'genre': 'platformer', 'era': '1990'}, tenant='tenant', owner='a',
        expires_at=30, authorized=True, retention_consent=True, now=10)
    assert digest and store.checkpoint(thread, messages, {'genre': 'platformer', 'era': '1990'}, tenant='tenant', owner='a',
        expires_at=30, authorized=True, retention_consent=True, now=10) == digest
    db.close()
    db = sqlite3.connect(path)
    store = DragonConversationMicroLogs(db)
    result = store.retrieve(thread, 'platformer', tenant='tenant', owner='a', now=10, authorized=True)
    assert len(result) == 1 and not result[0]['training_eligible']
    assert 'private raw transcript' not in str(result)
    with pytest.raises(PermissionError):
        store.retrieve(thread, 'platformer', tenant='tenant', owner='b', now=10, authorized=True)
    with pytest.raises(PermissionError):
        store.checkpoint(thread, messages, {}, tenant='tenant', owner='a', expires_at=30, authorized=True, retention_consent=False)
    assert store.expire(now=31) == 1
    assert not store.retrieve(thread, 'platformer', tenant='tenant', owner='a', now=10, authorized=True)


def test_ten_steps_reject_uncommitted_and_integrity():
    db = sqlite3.connect(':memory:')
    store = DragonConversationMicroLogs(db)
    thread, messages = thread_window()
    with pytest.raises(ValueError):
        store.checkpoint(replace(thread, message_sequence=9), messages, {}, tenant='tenant', owner='a', expires_at=30, authorized=True, retention_consent=True, now=10)
    store.checkpoint(thread, messages, {'genre': 'platformer'}, tenant='tenant', owner='a', expires_at=30, authorized=True, retention_consent=True, now=10)
    db.execute("UPDATE dragon_conversation_micro_logs SET payload='{}'")
    with pytest.raises(ValueError, match='integrity'):
        store.retrieve(thread, 'platformer', tenant='tenant', owner='a', now=10, authorized=True)


def test_cognition_composition_evidence_before_worker_admission():
    _, graph, _ = knowledge()
    session = DragonCognitionSession('a', graph)
    rule = MatrixRule('build', ('consent',))
    kwargs = dict(now=10, authorized=True)
    task = (SessionTask('chat', 'user', 1024, 1),)
    result = session.prepare(task, hardware(), rule, (), {}, 'jump', {'era': '1990'}, **kwargs)
    assert result['dispatch'] is None and not result['logic'].eligible
    facts = (EvidenceFact('consent', Truth.TRUE, 'consent_ref', 30),)
    result = session.prepare(task, hardware(), rule, facts, {}, 'jump', {'era': '1990'}, **kwargs)
    assert result['dispatch'].foreground_ready and result['context'].hits


def test_gap_matrix_ranks_measured_deficits_not_invented_grades():
    from skeleton.ai.webcrawler.dragon_capability_gap_matrix import CapabilityGap, prioritize_gaps
    gaps = (CapabilityGap('era', '1990', 10, 9, .9, 'review_a', 20),
            CapabilityGap('engine', 'nes', 10, 2, .9, 'review_b', 20),
            CapabilityGap('story', 'original', 10, 0, 1., 'stale_review', 5))
    result = prioritize_gaps(gaps, now=10)
    assert [g.factor for g in result] == ['engine', 'era']
    assert result[0].score == .72 and result[0].missing_checks == 8
    with pytest.raises(ValueError):
        prioritize_gaps((gaps[0], gaps[0]), now=10)


def test_low_memory_changes_context_not_permitted_era():
    small = plan_resources(hardware(available_memory_bytes=32 * 1024**2), now=10, foreground=True)
    large = plan_resources(hardware(available_memory_bytes=8 * 1024**3, cpu_units=32), now=10, foreground=True)
    assert small.context_bytes < large.context_bytes
    assert small.effort == 'low' and large.effort == 'high'
    _, _, store = knowledge()
    assert store.retrieve('a', 'jump', {'era': '2020'}, small, now=10, authorized=True).hits


def test_deictic_binding_and_conflicting_fact_do_not_grant_authority():
    rule = MatrixRule('design', ('known',), required_slots=('that', 'where'))
    facts = (EvidenceFact('known', Truth.CONFLICT, 'review', 20),)
    d = evaluate_matrix(rule, facts, {'that': 'project', 'where': 'renaissance'}, now=10, genre='rpg', era='1990', engine='nes')
    assert d.truth == Truth.CONFLICT and not d.eligible
    assert 'known' in d.incomplete


def test_checkpoint_deletion_removes_index_and_is_thread_scoped():
    db = sqlite3.connect(':memory:')
    store = DragonConversationMicroLogs(db)
    thread, messages = thread_window()
    store.checkpoint(thread, messages, {'engine': 'nes'}, tenant='tenant', owner='a', expires_at=30, authorized=True, retention_consent=True, now=10)
    store.delete_thread('tenant', 'b', thread.thread_id, authorized=True)
    assert store.retrieve(thread, 'nes', tenant='tenant', owner='a', now=10, authorized=True)
    store.delete_thread('tenant', 'a', thread.thread_id, authorized=True)
    assert not db.execute('SELECT 1 FROM dragon_conversation_micro_terms').fetchone()


def test_foreground_batch_admission_is_atomic_and_retryable():
    session = DragonResourceSession()
    requests = (SessionTask('chat_1', 'user', 1024, 2), SessionTask('chat_2', 'user', 1024, 2))
    decision = session.dispatch(requests, hardware(), now=10)
    assert not decision.admitted and not decision.foreground_ready
    assert session.dispatch(requests[:1], hardware(), now=10).foreground_ready


def test_noncheckpointable_work_cannot_be_assumed_stopped():
    session = DragonResourceSession()
    session.dispatch((SessionTask('native', 'autonomous', 1024, 1, False),), hardware(), now=10)
    d = session.dispatch((SessionTask('chat', 'user', 1024, 1),), hardware(), now=10)
    assert not d.admitted and not d.checkpoint_requested and d.reason == 'draining_background'
    session.stopped('native')
    assert session.dispatch((SessionTask('chat', 'user', 1024, 1),), hardware(), now=10).foreground_ready


def test_concurrent_admission_never_exceeds_session_cpu_budget():
    from concurrent.futures import ThreadPoolExecutor
    session = DragonResourceSession()
    def admit(i):
        return session.dispatch((SessionTask(f'chat_{i}', 'user', 1024, 1),), hardware(), now=10)
    with ThreadPoolExecutor(max_workers=8) as executor:
        decisions = tuple(executor.map(admit, range(8)))
    assert sum(len(d.admitted) for d in decisions) == 2
    assert sum(d.effort == 'high' for d in decisions) == 1


def global_scheduler():
    from skeleton.kernel.global_resource_scheduler import GlobalResourceScheduler, GlobalResourcePolicy, ResourceVector, PlanePolicy
    return GlobalResourceScheduler(GlobalResourcePolicy(ResourceVector(cpu_millis=2000, memory_mb=128, provider_tokens=100),
        (PlanePolicy('interactive', 2, ResourceVector(), 1.0), PlanePolicy('background', 1, ResourceVector(), 1.0))))


def test_global_ledger_shared_across_dragon_sessions_and_other_planes():
    scheduler = global_scheduler()
    a = DragonResourceSession(global_resources=scheduler, tenant='tenant_a')
    b = DragonResourceSession(global_resources=scheduler, tenant='tenant_b')
    task = SessionTask('chat', 'user', 1024, 2, provider_tokens=80)
    decision = a.dispatch((task,), hardware(), now=10)
    assert decision.execution_authorized and decision.foreground_ready
    assert scheduler.usage('interactive').provider_tokens == 80
    denied = b.dispatch((task,), hardware(), now=10)
    assert not denied.admitted and not denied.execution_authorized
    assert denied.reason == 'global_capacity'
    a.stopped('chat')
    assert scheduler.usage('interactive').empty
    assert b.dispatch((task,), hardware(), now=10).execution_authorized
    b.stopped('chat')


def test_global_provider_token_budget_blocks_before_execution():
    scheduler = global_scheduler()
    session = DragonResourceSession(global_resources=scheduler, tenant='a')
    task = SessionTask('chat', 'user', 1024, 1, provider_tokens=101)
    decision = session.dispatch((task,), hardware(), now=10)
    assert not decision.admitted and not decision.execution_authorized
    assert scheduler.usage('interactive').empty


def test_local_planning_alone_is_never_execution_authority():
    decision = DragonResourceSession().dispatch((SessionTask('chat', 'user', 1024, 1),), hardware(), now=10)
    assert decision.foreground_ready and not decision.execution_authorized


def test_global_priority_translation_preserves_user_first():
    scheduler = global_scheduler()
    session = DragonResourceSession(global_resources=scheduler, tenant='a')
    session.dispatch((SessionTask('chat', 'user', 1024, 1),), hardware(), now=10)
    grant = scheduler.active_grants()[0]
    assert grant.priority == 0
    session.stopped('chat')
    session.dispatch((SessionTask('learn', 'acquisition', 1024, 1),), hardware(), now=10)
    assert scheduler.active_grants()[0].priority == 6
    session.stopped('learn')
