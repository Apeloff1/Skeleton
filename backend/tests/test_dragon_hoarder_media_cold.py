"""Physical-byte semantics in an isolated fixture; not production qualification."""
from __future__ import annotations

from collections import namedtuple
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from core.dragon_game_corpus import GameCorpus
from core.dragon_hoarder_bulk import BulkArchive,Volume,GIB,StorageHeld
from core.dragon_hoarder_manifests import ManifestArchive,BLOCK
from core.dragon_media_archive import MediaArchive
from core.dragon_cold_primary import _mid,_stage_one,_read_one
from core.dragon_hoarder_qualification import independent

SCOPE={"tenant_id":"tenant","owner_id":"owner"}
OTHER={"tenant_id":"tenant","owner_id":"other"}


class PhysicalFixtureTests(TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve()
        disk=namedtuple("Disk","total used free")
        guard=patch("core.dragon_hoarder_bulk.shutil.disk_usage",return_value=disk(10*GIB,0,10*GIB))
        guard.start();self.addCleanup(guard.stop)
        self.vol=Volume("primary",self.root,2*GIB)
        self.store=ManifestArchive(self.root/"manifests.db",BulkArchive((self.vol,)))
        self.path=self.root/"corpus.db"
        self.corpus=GameCorpus(self.path)
        seed=self.corpus.observe(SCOPE,namespace="developer",external_id="game",title="Game",
            source="https://example.org/media",stage="released",kind="gameplay_video",language="en",
            event_key="first",version="1",released_on=None)
        self.game=seed["game_id"];self.source=seed["source_id"];self.observation=seed["observation_digest"]

    def test_media_exact_chunks_reopen_revoke_and_cleanup(self):
        raw=b"\x00\x00\x00\x18ftypisom"+b"x"*(BLOCK+48)
        full=hashlib.sha256(raw).hexdigest()
        a=MediaArchive(self.path,self.store)
        receipt=a.begin(SCOPE,game=self.game,source=self.source,observation_digest=self.observation,
            operation="import",mime="video/mp4",total_bytes=len(raw),sha256=full,
            rights_acknowledged=True,grant_seconds=900)
        mid=receipt["media_id"]
        with self.assertRaises(LookupError):a.metadata(SCOPE,mid)
        with self.assertRaises(ValueError):a.append(SCOPE,mid,0,b"<html>"+b"x"*(BLOCK-6))
        with self.assertRaises(StorageHeld):a.seal(SCOPE,mid)
        a.append(SCOPE,mid,0,raw[:BLOCK])
        a.append(SCOPE,mid,1,raw[BLOCK:])
        self.assertEqual(a.seal(SCOPE,mid)["sha256"],full)
        restarted=MediaArchive(self.path,ManifestArchive(self.root/"manifests.db",BulkArchive((self.vol,))))
        self.assertEqual(restarted.part(SCOPE,mid,0)+restarted.part(SCOPE,mid,1),raw)
        with self.assertRaises(LookupError):restarted.metadata(OTHER,mid)
        self.assertTrue(restarted.revoke(SCOPE,mid)["revoked"])
        with self.assertRaises(LookupError):restarted.part(SCOPE,mid,0)
        self.assertEqual(restarted.cleanup()["removed"],1)
        self.assertEqual(restarted.list(SCOPE,self.game,self.source)["media"],[])

    def test_cold_manifest_exact_stage_and_owner_isolation(self):
        session=str(uuid4());operation="a"*64
        raw=b'{"snapshot":"test witness"}'
        mark={"operation":operation,"manifest":_mid(SCOPE,session,operation),
              "sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
        _stage_one(self.store,SCOPE,session,mark,raw)
        self.assertEqual(_read_one(self.store,SCOPE,mark),raw)
        with self.assertRaises(StorageHeld):_read_one(self.store,OTHER,mark)
        with self.assertRaises(StorageHeld):_read_one(self.store,SCOPE,{**mark,"sha256":"b"*64})
        # A copy on the same mounted filesystem is not an independent backup.
        with self.assertRaises(StorageHeld):independent(self.store,self.store)
