"""Integration regressions for restored operator, context, and vault seams."""
from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from skeleton.cortex.deck import CommandDeck
from skeleton.memory.compaction import ContextCompactor, Turn
from skeleton.memory.guarded_compaction import RotGuardedCompactor, CompactionError
from skeleton.vault.kms import EnvelopeKMS
from skeleton.vault.keys import KeyRegistry


@pytest.mark.parametrize('field', ['ciphertext', 'nonce', 'key_nonce', 'wrapped_key'])
def test_vault_rejects_tampering(field):
    kms = EnvelopeKMS()
    envelope = kms.encrypt(b'private payload', 'tenant-a')
    envelope[field] = ('00' if envelope[field][:2] != '00' else '01') + envelope[field][2:]
    with pytest.raises(InvalidTag):
        kms.decrypt(envelope)


def test_vault_binds_context_and_rejects_wrong_master():
    kms = EnvelopeKMS()
    envelope = kms.encrypt(b'private payload', 'tenant-a')
    changed = {**envelope, 'context': 'tenant-b'}
    with pytest.raises(InvalidTag):
        kms.decrypt(changed)
    with pytest.raises(InvalidTag):
        EnvelopeKMS().decrypt(envelope)


def test_vault_rotation_preserves_prior_envelopes_and_is_atomic():
    master = b'a' * 32
    kms = EnvelopeKMS(master)
    envelope = kms.encrypt(b'private payload', 'tenant-a')
    registry = KeyRegistry(kms)
    key = kms.generate_data_key('tenant-a')
    registry.register(key)
    before = kms.unwrap_key(key)
    with pytest.raises(ValueError):
        registry.rotate(b'short')
    assert registry.current_generation() == kms.stats()['key_rotations'] == 0
    assert registry.rotate(b'b' * 32) == 2
    assert registry.generation_of(key.key_id) == 1
    assert not registry.pending_rotation()
    assert kms.unwrap_key(key) == before
    assert kms.decrypt(envelope) == b'private payload'
    assert EnvelopeKMS(master).decrypt(envelope) == b'private payload'
    assert kms.encrypt(b'private payload', 'tenant-a') != envelope


def test_vault_rejects_legacy_unauthenticated_format():
    with pytest.raises(ValueError, match='unauthenticated'):
        EnvelopeKMS().decrypt({'algorithm': 'envelope-xor-v1', 'ciphertext': '00', 'context': 'x'})


def test_guarded_compactor_preserves_buried_constraint_whole():
    constraint = 'NEVER DISCARD THIS REQUIREMENT'
    turns = [Turn('user', 'optional ' * 100), Turn('system', constraint),
             Turn('assistant', 'optional ' * 100)]
    compactor = RotGuardedCompactor(compactor=ContextCompactor(token_budget=20))
    result = compactor.process(turns, constraints=[constraint])
    assert result.compacted
    assert Turn('system', constraint) in result.turns
    assert sum(turn.tokens for turn in result.turns) <= 20
    assert compactor.stats() == {'checks': 1, 'interventions': 1}


def test_guarded_compactor_fails_when_constraint_cannot_fit():
    compactor = RotGuardedCompactor(compactor=ContextCompactor(token_budget=1))
    with pytest.raises(CompactionError):
        compactor.process([Turn('system', 'KEEP THIS ENTIRE REQUIREMENT')],
                          constraints=['KEEP THIS ENTIRE REQUIREMENT'])


def test_decks_keep_controls_and_persisted_policy_isolated(tmp_path):
    left, right = CommandDeck(root=tmp_path / 'a'), CommandDeck(root=tmp_path / 'b')
    left.steering_register('left')
    left.steering_activate('left')
    assert right.steering_composite()['card']['active_vectors'] == []
    version = left.save_policy_version(comment='snapshot')
    assert left.policy_versions()['total_versions'] == 1
    assert right.policy_versions()['total_versions'] == 0
    assert left.rollback_preview(version)['ok'] == 1
    assert left.verify_plan({})['accepted'] is False
    with pytest.raises(ValueError, match='unknown surface'):
        left.repair_orchestrate('missing', 'target')


def test_product_status_does_not_execute_repair(tmp_path, monkeypatch):
    from skeleton.organism.product import product_card
    deck = CommandDeck(root=tmp_path)
    def unexpected(*args, **kwargs):
        raise AssertionError('status must not execute a repair')
    monkeypatch.setattr(deck, 'repair_orchestrate', unexpected)
    assert product_card(deck=deck)['repair_orchestrator']['total_sessions'] == 0


def test_profile_status_does_not_reenter_caps_summary(monkeypatch):
    from skeleton.kernel.profiles import card
    def unexpected():
        raise AssertionError('profile selection must consume raw caps, not recurse through summary')
    monkeypatch.setattr('skeleton.organism.caps.card', unexpected)
    assert card()['profile'] in {'tight', 'mobile', 'desktop', 'max'}


def test_walk_budget_honors_tighter_overlay(monkeypatch):
    from skeleton.organism.budget import walk_limit
    monkeypatch.setattr('skeleton.kernel.profiles.live_overlay', lambda: {'walk_n': 1})
    assert walk_limit('max', 8) == 1


def test_context_mesh_respects_budget_even_for_first_record():
    from skeleton.testing.test_jeeves_context_mesh import _repository
    from skeleton.jeeves.agent.context_repository import ContextKind
    from skeleton.jeeves.agent.context_fabric import CognitiveContextFabric
    from skeleton.jeeves.agent.context_mesh import ContextRepositoryMesh
    from skeleton.jeeves.agent.memory_game_index import SourceTier
    repository = _repository('budget-tenant', 'user', 'a' * 25, kind=ContextKind.DIARY)
    mesh = ContextRepositoryMesh(CognitiveContextFabric())
    mesh.attach(repository)
    adapter = mesh.adapter(SourceTier.DIARY)
    assert adapter.fetch_refs(repository.namespace.key, ('shared-key',), max_records=1, max_tokens=6) == ()
    assert adapter.search(repository.namespace.key, 'a', max_records=1, max_tokens=6) == ()
    record, = adapter.fetch_refs(repository.namespace.key, ('shared-key',), max_records=1, max_tokens=7)
    assert record.token_estimate == 7


@pytest.mark.parametrize('constraints', ['not-a-list', [None], ['']])
def test_guarded_compactor_validates_constraints_before_fast_path(constraints):
    with pytest.raises(ValueError):
        RotGuardedCompactor().process([Turn('user', 'short')], constraints=constraints)


@pytest.mark.parametrize('amount', [0, -1, float('nan'), float('inf'), True])
def test_rate_limiter_rejects_invalid_debits(amount):
    from skeleton.resilience.rate_limiter import RateLimiter
    limiter = RateLimiter(capacity=1, refill_rate=1)
    with pytest.raises(ValueError):
        limiter.allow('user', amount)
    assert limiter.allow('user')
    assert not limiter.allow('user')


def test_dashboard_reports_its_own_alert_and_circuit_state(tmp_path):
    deck = CommandDeck(root=tmp_path)
    for _ in range(deck.circuit.policy.failure_threshold):
        deck.circuit.record_failure()
    alert = deck.dashboard.fire_alert('critical', 'resilience', 'offline')
    snapshot = deck.dashboard_card()
    assert snapshot['doctor']['circuit']['state'] == 'open'
    assert snapshot['product']['dashboard']['alerts'][0]['id'] == alert.id
    assert snapshot['nervous']['health']['circuit_state'] == 'open'


def test_journaled_bus_preserves_replay_and_subscription_contract():
    from skeleton.kernel.events import EventBus, DomainEvent
    from skeleton.foundation.journal import EventJournal, JournaledBus
    bus = JournaledBus(EventBus(), EventJournal())
    received = []
    unsubscribe = bus.subscribe('test.*', received.append, name='integration')
    event = DomainEvent('test.runtime', {'count': 1}, correlation_id='runtime-check')
    assert bus.publish(event) is event
    assert bus.replay('test.runtime') == received == [event]
    assert bus.trace('runtime-check') == [event]
    unsubscribe()
    bus.publish(event)
    assert len(received) == 1


def test_graph_snapshot_preserves_annotations_and_rejects_partial_restore():
    from skeleton.retrieval.kag import KnowledgeGraph
    from skeleton.persistence.snapshots import serialize_graph, restore_graph
    graph = KnowledgeGraph()
    graph.add('alpha', 'uses', 'beta', confidence=0.4, provenance='document:1')
    snapshot = serialize_graph(graph)
    restored = KnowledgeGraph()
    assert restore_graph(snapshot, restored) == 1
    assert restored.annotation_for('alpha', 'uses', 'beta') == graph.annotation_for('alpha', 'uses', 'beta')
    snapshot['annotations'][0]['confidence'] = float('nan')
    empty = KnowledgeGraph()
    with pytest.raises(ValueError):
        restore_graph(snapshot, empty)
    assert empty.stats()['triples'] == 0
    assert restore_graph({'triples': [['legacy', 'uses', 'fact']]}, empty) == 1


def test_repository_audits_preserve_large_route_sets_with_finite_limits():
    from skeleton.app.runtime.contract_safety import public_contract_payload, MAX_AUDIT_ITEMS
    from skeleton.app.runtime.command_contracts import CommandResult
    rows = [{'route': f'/api/{i}', 'token': 'secret'} for i in range(300)]
    result = CommandResult(command='capabilities', ok=True, data={'routes': rows}).to_payload()['data']
    assert len(result['routes']) == 300
    assert all(row['token'] != 'secret' for row in result['routes'])
    assert len(public_contract_payload(rows)) == 64
    assert len(public_contract_payload(list(range(MAX_AUDIT_ITEMS + 20)), repository_audit=True)) == MAX_AUDIT_ITEMS
    assert public_contract_payload(['x' * 4096] * 100, repository_audit=True) == {'truncated': True, 'reason': 'output_too_large'}


def test_consolidation_preserves_due_reviews_and_honors_zero_budget():
    import time
    from skeleton.memory.core import RepetitionScheduler
    from skeleton.memory.consolidation import ConsolidationCycle
    from skeleton.jeeves.matrices_llm import KnowledgeRetentionMatrix
    krem = KnowledgeRetentionMatrix()
    krem.observe('alpha')
    krem._cells['alpha'].last_seen = time.time() - krem.HALF_LIFE_HOURS * 20 * 3600
    scheduler = RepetitionScheduler()
    cycle = ConsolidationCycle(krem, scheduler)
    assert cycle.cycle()['scheduled'] == 1
    scheduler._schedule['krem:alpha']['next_review'] = time.time() - 1
    assert cycle.cycle(max_concepts=0)['refreshed'] == []
    report = cycle.cycle()
    assert report['scheduled'] == 0
    assert report['refreshed'] == ['alpha']


def test_seeded_entropy_bytes_are_reproducible_and_bounded():
    from skeleton.kernel.entropy import EntropyPool
    assert EntropyPool(42).random_bytes(12) == EntropyPool(42).random_bytes(12)
    for invalid in (True, -1, 1.5, 1_048_577):
        with pytest.raises(ValueError):
            EntropyPool(42).random_bytes(invalid)


def test_output_guard_blocks_exfiltration_even_when_content_guard_allows(monkeypatch):
    from skeleton.resilience.fortress import ResilienceFortress
    from types import SimpleNamespace
    fortress = ResilienceFortress()
    monkeypatch.setattr(fortress.guardrail, 'evaluate', lambda _: {'safe': True, 'score': 0.0})
    monkeypatch.setattr(fortress.exfiltration, 'monitor_query', lambda *_: SimpleNamespace(to_dict=lambda: {'blocked': True}))
    result = fortress.process_output('private response', 'user', 'query')
    assert result['safe'] is False
    assert result['deliverable'] == '[OUTPUT BLOCKED: SAFETY VIOLATION]'


def test_retry_card_counts_actual_retries():
    from skeleton.resilience.adaptive_retry import AdaptiveRetry
    retry = AdaptiveRetry()
    attempts = []
    def operation():
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError('retryable')
        return 'ok'
    retry.tune('test', base_delay_s=0)
    assert retry.execute('test', operation)['success']
    assert retry.card()['total_retries'] == 1



def test_lightweight_import_does_not_load_cryptography():
    import subprocess
    import sys
    from pathlib import Path
    code = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'cryptography' or name.startswith('cryptography.'):
        raise ModuleNotFoundError('cryptography intentionally unavailable')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import skeleton
from skeleton.vault.kms import EnvelopeKMS
try:
    EnvelopeKMS().encrypt(b'payload', 'test')
except ModuleNotFoundError as error:
    assert 'cryptography' in str(error)
else:
    raise AssertionError('encryption must not fall back without cryptography')
"""
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[2],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_architecture_audit_resolves_canonical_packages_and_compatibility_exports():
    from skeleton.app.runtime.audit_parse import public_exports
    from skeleton.app.runtime import export_audit_snapshot
    rows = export_audit_snapshot()["capabilities"]
    assert all(row["in_architecture_registry"] for row in rows)
    assert public_exports("skeleton.application") == public_exports("skeleton.app.runtime")
    assert public_exports("skeleton.social") == public_exports("skeleton.research.social")
