import unittest
from skeleton.ai.runtime.production_fabric.persistence.journal import Journal
from skeleton.ai.runtime.production_fabric.persistence.outbox import Outbox
from skeleton.ai.runtime.production_fabric.persistence.inbox import Inbox
from skeleton.ai.runtime.production_fabric.persistence.leases import LeaseStore
from skeleton.ai.runtime.production_fabric.persistence.revisions import Revisions
from skeleton.ai.runtime.production_fabric.persistence.export import export_stream, validate_export
from skeleton.ai.runtime.production_fabric.persistence.snapshots import capture, validate
from skeleton.ai.runtime.production_fabric.persistence.game_store import GameStore
from skeleton.ai.runtime.production_fabric.contracts.spec import parse_world
from skeleton.ai.runtime.production_fabric.contracts.state import initial
from skeleton.ai.runtime.production_fabric.contracts.errors import ConflictError, IntegrityError
from skeleton.ai.runtime.production_fabric.product.content.worlds.cloudbreak_signal import WORLD

class PersistenceTests(unittest.TestCase):

    def setUp(self):
        self.j = Journal()

    def tearDown(self):
        self.j.close()

    def test_idempotent_append(self):
        receipt = self.j.append('session', 'token', 'event', {'x': 1}, expected_revision=0)
        self.assertFalse(receipt['duplicate'])
        self.assertTrue(self.j.append('session', 'token', 'event', {'x': 1}, expected_revision=0)['duplicate'])
        self.assertEqual(len(self.j.replay('session')), 1)

    def test_idempotency_collision_denied(self):
        self.j.append('session', 'token', 'event', {'x': 1}, expected_revision=0)
        with self.assertRaises(ConflictError):
            self.j.append('session', 'token', 'event', {'x': 2}, expected_revision=1)

    def test_stale_revision_denied(self):
        self.j.append('session', 'token', 'event', {'x': 1}, expected_revision=0)
        with self.assertRaises(ConflictError):
            self.j.append('session', 'next', 'event', {'x': 1}, expected_revision=0)

    def test_corruption_denied(self):
        self.j.append('session', 'token', 'event', {'x': 1}, expected_revision=0)
        self.j.db.execute("UPDATE events SET body=? WHERE stream='session'", (b'{"x":2}\n',))
        with self.assertRaises(IntegrityError):
            self.j.replay('session')

    def test_outbox_ack_and_dedupe(self):
        out = Outbox(self.j.db)
        self.assertTrue(out.enqueue('id', 'preview', {'x': 1}))
        self.assertFalse(out.enqueue('id', 'preview', {'x': 1}))
        pending = out.pending()
        self.assertEqual(len(pending), 1)
        self.assertFalse(out.acknowledge('id', 'bad'))
        self.assertTrue(out.acknowledge('id', pending[0]['sha256']))
        self.assertFalse(out.pending())

    def test_inbox_conflict(self):
        inbox = Inbox(self.j.db)
        self.assertTrue(inbox.accept('event', {'ok': 1}))
        self.assertFalse(inbox.accept('event', {'ok': 1}))
        with self.assertRaises(ConflictError):
            inbox.accept('event', {'ok': 2})

    def test_lease_fencing(self):
        leases = LeaseStore(self.j.db)
        t1 = leases.acquire('node', 'alice', 10, 5)
        with self.assertRaises(ConflictError):
            leases.acquire('node', 'bob', 12, 5)
        t2 = leases.acquire('node', 'bob', 16, 5)
        self.assertGreater(t2, t1)
        with self.assertRaises(ConflictError):
            leases.require('node', 'alice', t1, 16)
        self.assertTrue(leases.require('node', 'bob', t2, 17))

    def test_metadata_cas(self):
        row = Revisions(self.j.db)
        self.assertEqual(row.write('checkpoint', 0, {'x': 1}), 1)
        with self.assertRaises(ConflictError):
            row.write('checkpoint', 0, {'x': 2})
        self.assertEqual(row.read('checkpoint'), (1, {'x': 1}))

    def test_stream_export_integrity(self):
        self.j.append('session', 'token', 'event', {'x': 1}, expected_revision=0)
        record = validate_export(export_stream(self.j, 'session'))
        self.assertEqual(record['head'][0], 1)

    def test_snapshot_not_source_of_truth(self):
        state = initial(parse_world(WORLD))
        snap = capture(state, '0' * 64)
        self.assertTrue(validate(snap, state, '0' * 64))
        with self.assertRaises(IntegrityError):
            validate(snap, state, '1' * 64)

    def test_game_store_replay(self):
        store = GameStore(self.j, parse_world(WORLD))
        state, receipt = store.choose('play', 'step', 'visit_commons', expected_revision=0)
        self.assertEqual(state.scene, 'commons')
        self.assertEqual(store.load('play').revision, 1)

class IdempotentGameRetryTests(unittest.TestCase):

    def test_exact_retry_reuses_prior_receipt(self):
        from skeleton.ai.runtime.production_fabric.persistence.journal import Journal
        from skeleton.ai.runtime.production_fabric.persistence.game_store import GameStore
        from skeleton.ai.runtime.production_fabric.contracts.spec import parse_world
        from skeleton.ai.runtime.production_fabric.product.content.worlds.cloudbreak_signal import WORLD
        j = Journal()
        try:
            store = GameStore(j, parse_world(WORLD))
            store.choose('session', 'token', 'visit_commons', expected_revision=0)
            state, receipt = store.choose('session', 'token', 'visit_commons', expected_revision=0)
            self.assertEqual(state.revision, 1)
            self.assertTrue(receipt['duplicate'])
        finally:
            j.close()
