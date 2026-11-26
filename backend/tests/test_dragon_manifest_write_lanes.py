"""Physical intra-owner manifest transaction partition fixtures."""
from __future__ import annotations

from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from core.dragon_hoarder_bulk import BulkArchive,Volume,GIB,StorageHeld,owner_key,_storage_owner
from core.dragon_hoarder_manifests import ManifestArchive
from core.dragon_manifest_shards import ShardedManifestArchive
from core.dragon_manifest_write_lanes import OwnerWriteLanes,provision,_file,_namespace
from core.dragon_owner_migration import migrate
from core.dragon_owner_shards import provision as provision_owner,ShardHeld

SCOPE={"tenant_id":"fixture","owner_id":"owner"}
OTHER={"tenant_id":"fixture","owner_id":"other"}


class ManifestWriteLanesTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        disk=namedtuple("Disk","total used free")
        p=patch("core.dragon_hoarder_bulk.shutil.disk_usage",return_value=disk(10*GIB,0,10*GIB))
        p.start();self.addCleanup(p.stop)
        self.bulk=BulkArchive((Volume("volume",self.root,2*GIB),))
        self.path=self.root/"manifest.db"
        self.store=ShardedManifestArchive(self.path,self.bulk)
        self.raw=b"same bytes across independent write lanes"
        self.digest=hashlib.sha256(self.raw).hexdigest()

    def operation(self,lane,tag="op"):
        dispatcher=OwnerWriteLanes(self.store._owner(SCOPE),SCOPE)
        for i in range(10000):
            op=tag+str(i)
            identifier=dispatcher.identifier("fixture",op)
            if int(identifier[:16],16)%10==lane:return op
        raise AssertionError("fixture lane missing")

    def begin(self,op,scope=SCOPE):
        return self.store.begin(scope,logical_key="fixture",operation=op,expected_hash=self.digest,expected_bytes=len(self.raw))

    def put(self,op,scope=SCOPE):
        mid=self.begin(op,scope)["manifest"]
        self.store.append(scope,mid,0,self.raw)
        self.store.seal(scope,mid)
        return mid

    def provision(self):
        return provision(self.path,SCOPE,offline_acknowledged=True)

    def test_manifest_connection_reobserves_unlinked_sidecar(self):
        import os
        archive=ManifestArchive(self.path,self.bulk)
        original=Path.lstat
        side=Path(str(self.path)+"-wal")
        live=original(self.path)
        removed=list(live)
        removed[3]=0
        observations=[]
        def racing(candidate):
            if candidate==side:
                observations.append(candidate)
                if len(observations)==1:
                    return os.stat_result(removed)
                raise FileNotFoundError(str(candidate))
            return original(candidate)

        with patch.object(Path,"lstat",racing):
            with archive._db() as db:
                self.assertEqual(db.execute("SELECT 1").fetchone()[0],1)
        self.assertEqual(len(observations),2)

    def test_manifest_connection_rejects_live_sidecar_hardlink(self):
        import os
        archive=ManifestArchive(self.path,self.bulk)
        side=Path(str(self.path)+"-wal")
        self.assertFalse(side.exists())
        os.link(self.path,side)
        try:
            with self.assertRaises(StorageHeld):
                with archive._db():
                    self.fail("unsafe sidecar admitted")
        finally:
            side.unlink()

    def test_transient_sidecar_unlink_is_reobserved(self):
        import os
        from core.dragon_owner_shards import _private

        side=Path(str(self.path)+"-wal")
        original=Path.lstat
        live=original(self.path)
        removed=list(live)
        removed[3]=0
        observations=[]
        def transient(candidate):
            if candidate==side:
                observations.append(candidate)
                if len(observations)==1:
                    return os.stat_result(removed)
                raise FileNotFoundError(str(candidate))
            return original(candidate)

        with patch.object(Path,"lstat",transient):
            self.assertEqual(_private(self.path)[1],(live.st_dev,live.st_ino))
        self.assertEqual(len(observations),2)

    def test_sidecar_symlink_and_live_hardlink_remain_denied(self):
        import os
        from core.dragon_owner_shards import _private

        if os.name!="posix":
            self.skipTest("POSIX private inode custody")
        side=Path(str(self.path)+"-wal")
        self.assertFalse(side.exists())
        side.symlink_to(self.root/"nonexistent")
        try:
            with self.assertRaises(ShardHeld):
                _private(self.path)
        finally:
            side.unlink()
        os.link(self.path,side)
        try:
            with self.assertRaises(ShardHeld):
                _private(self.path)
        finally:
            side.unlink()
        side.touch(mode=0o600)
        side.chmod(0o644)
        try:
            with self.assertRaises(ShardHeld):
                _private(self.path)
        finally:
            side.unlink()
        self.assertEqual(_private(self.path)[0],self.path)

    def test_legacy_id_and_tombstone_keep_legacy_lane(self):
        op=self.operation(7,"legacy")
        mid=self.put(op)
        self.store.abort(SCOPE,mid)
        self.provision()
        self.assertEqual(self.begin(op)["state"],"aborted")
        self.assertEqual(self.store._lanes(SCOPE)._lane(mid),0)
        self.store.collect_manifest(SCOPE,mid)
        self.assertEqual(self.begin(op)["manifest"],mid)

    def test_cross_partition_gc_cannot_delete_identical_payload(self):
        legacy=self.put(self.operation(8,"legacy"))
        receipt=self.provision()
        first=self.put(self.operation(1));second=self.put(self.operation(2))
        self.assertEqual(self.store.usage(SCOPE)["unique_chunks"],3)
        self.assertEqual(self.bulk.lookup("volume",SCOPE,self.digest).scope_key,owner_key(SCOPE))
        a=self.bulk.lookup("volume",SCOPE,self.digest,namespace=_namespace(receipt["epoch"],1))
        b=self.bulk.lookup("volume",SCOPE,self.digest,namespace=_namespace(receipt["epoch"],2))
        self.assertNotEqual(a.scope_key,b.scope_key)
        with self.assertRaises(StorageHeld):self.bulk.read(SCOPE,a)
        self.store.abort(SCOPE,first)
        self.store.collect_manifest(SCOPE,first)
        self.assertIsNone(self.bulk.lookup("volume",SCOPE,self.digest,namespace=_namespace(receipt["epoch"],1)))
        self.assertEqual(self.store.read_chunk(SCOPE,second,0),self.raw)
        self.assertEqual(self.store.read_chunk(SCOPE,legacy,0),self.raw)

    def test_same_lane_dedup_keeps_live_reference(self):
        self.provision()
        a=self.put(self.operation(4,"a"));b=self.put(self.operation(4,"b"))
        self.assertEqual(self.store.usage(SCOPE)["unique_chunks"],1)
        self.store.abort(SCOPE,a)
        self.store.collect_manifest(SCOPE,a)
        self.assertEqual(self.store.read_chunk(SCOPE,b,0),self.raw)
        self.assertEqual(self.store.usage(SCOPE)["unique_chunks"],1)

    def test_concurrent_writes_and_cross_lane_history(self):
        self.provision()
        # Independent ledgers but same underlying device fixture. No speed claim.
        ops=[self.operation(i) for i in range(10)]
        with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(self.put,ops))
        self.assertEqual(len(set(ids)),10)
        self.assertEqual(self.store.usage(SCOPE)["manifests"]["sealed"],10)
        seen=[];cursor=None
        while True:
            page=self.store.history(SCOPE,"fixture",limit=3,before=cursor)
            seen.extend(r["id"] for r in page["manifests"]);cursor=page["next_cursor"]
            if cursor is None:break
        self.assertEqual(set(seen),set(ids))
        self.assertEqual(len(seen),10)
        reopened=ShardedManifestArchive(self.path,self.bulk)
        for mid in ids:self.assertEqual(reopened.read_chunk(SCOPE,mid,0),self.raw)

    def test_missing_partition_holds_no_recreation_or_legacy_fallback(self):
        receipt=self.provision()
        op=self.operation(3)
        mid=self.put(op)
        path=_file(self.path,owner_key(SCOPE),receipt["epoch"],3)
        path.unlink()
        with self.assertRaises(StorageHeld):self.store.read_chunk(SCOPE,mid,0)
        with self.assertRaises(StorageHeld):self.begin(op)
        with self.assertRaises(StorageHeld):self.store.history(SCOPE,"fixture")
        self.assertFalse(path.exists())

    def test_other_owner_cannot_read_or_erase_partition(self):
        self.provision()
        mid=self.put(self.operation(2))
        with self.assertRaises(StorageHeld):self.store.read_chunk(OTHER,mid,0)
        with self.assertRaises(StorageHeld):self.store.abort(OTHER,mid)
        self.assertEqual(self.store.read_chunk(SCOPE,mid,0),self.raw)

    def test_provision_requires_offline_and_existing_owner_migration_holds(self):
        with self.assertRaises(StorageHeld):provision(self.path,SCOPE)
        self.provision()
        with self.assertRaises(StorageHeld):self.provision()
        paths=[self.path]+[self.root/("owner-"+str(i)+".sqlite") for i in range(1,10)]
        provision_owner(self.path,"manifest",paths,offline_acknowledged=True)
        with self.assertRaises(ShardHeld):migrate(self.path,"manifest",SCOPE,3,offline_acknowledged=True)
