"""Encrypted local AI memory: real AESGCM, tamper refusal, scope, restart and deletion."""
from __future__ import annotations
import hashlib,os,tempfile,unittest
from pathlib import Path
from skeleton.ai.runtime.operational_ai.context.sealed_memory.keys import KeyMaterial,load_key_file,MemoryKeyError
from skeleton.ai.runtime.operational_ai.context.sealed_memory.store import SealedMemoryStore
from skeleton.ai.runtime.operational_ai.authority.identity import Actor
from skeleton.ai.runtime.operational_ai.context.sources import Source

class TestSealedMemory(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ai-sealed-memory-')
        self.db=Path(self.tmp.name)/'memory.sqlite'
        self.key=KeyMaterial(b'A'*32,1)
        self.actor=Actor('tenant','user','1'*64,'2'*64)
        self.source=Source.create('doc','tenant','user','user','A secret about atlas retrieval',
                                  rights='original',trust='user-supplied')
    def tearDown(self):self.tmp.cleanup()

    def test_encrypt_roundtrip_no_plaintext_on_disk(self):
        with SealedMemoryStore(self.db,self.key) as store:
            store.admit(self.actor,self.source,approved=True)
            self.assertEqual(store.sources(self.actor),(self.source,))
            self.assertTrue(store.search(self.actor,'atlas'))
        assert b'Atlas' not in self.db.read_bytes()
        self.assertNotIn(b'A secret about atlas retrieval',self.db.read_bytes())
        with SealedMemoryStore(self.db,self.key) as reopened:
            self.assertEqual(reopened.sources(self.actor),(self.source,))

    def test_wrong_key_fails_closed(self):
        with SealedMemoryStore(self.db,self.key) as store:
            store.admit(self.actor,self.source,approved=True)
        with SealedMemoryStore(self.db,KeyMaterial(b'B'*32,1)) as store:
            with self.assertRaises(MemoryKeyError):store.sources(self.actor)

    def test_independent_approval_required(self):
        with SealedMemoryStore(':memory:',self.key) as store:
            with self.assertRaises(MemoryKeyError):store.admit(self.actor,self.source)

    def test_no_cross_user_or_model_source_access(self):
        with SealedMemoryStore(':memory:',self.key) as store:
            store.admit(self.actor,self.source,approved=True)
            self.assertEqual(store.sources(Actor('tenant','other','1'*64,'2'*64)),())
            self.assertEqual(store.sources(Actor('tenant','user','3'*64,'2'*64)),())

    def test_revision_and_forget(self):
        with SealedMemoryStore(':memory:',self.key) as store:
            store.admit(self.actor,self.source,approved=True)
            with self.assertRaises(MemoryKeyError):store.admit(self.actor,self.source,approved=True)
            self.assertTrue(store.forget(self.actor,'doc'))
            self.assertEqual(store.sources(self.actor),())

    def test_ciphertext_mutation_refused(self):
        with SealedMemoryStore(':memory:',self.key) as store:
            store.admit(self.actor,self.source,approved=True)
            store._db.execute("UPDATE sealed_ai_memory SET ciphertext=x'00'")
            with self.assertRaises(MemoryKeyError):store.sources(self.actor)

    def test_key_file_mode(self):
        p=Path(self.tmp.name)/'private.key'
        p.write_bytes(b'K'*32);p.chmod(0o600)
        self.assertEqual(load_key_file(p).master,b'K'*32)
        p.chmod(0o644)
        with self.assertRaises(MemoryKeyError):load_key_file(p)

if __name__=='__main__':unittest.main()
