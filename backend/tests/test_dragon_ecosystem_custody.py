"""Local ecosystem export on disposable private fixture stores."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import os
import sqlite3

from core import dragon_ecosystem_custody as eco
from core import dragon_graph_deployment as custody
from core.dragon_game_datasets import shard_path
from core.dragon_hoarder_bulk import Volume,BulkArchive,GIB
from core.dragon_hoarder_manifests import ManifestArchive
from core.dragon_manifest_write_lanes import provision
from core.dragon_manifest_shards import ShardedManifestArchive

SCOPE={"tenant_id":"custody","owner_id":"test"}

class EcosystemTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.knowledge=self.root/"knowledge.sqlite3"
        self.knowledge.touch(mode=0o600)
        with sqlite3.connect(self.knowledge) as db:
            db.execute("CREATE TABLE fixture(v TEXT)")
            db.execute("INSERT INTO fixture VALUES('preserved')")
        p=patch.dict(os.environ,{"SKL_DRAGON_KNOWLEDGE_DB_PATH":str(self.knowledge)},clear=True)
        p.start();self.addCleanup(p.stop)

    def manifest(self):
        root=self.root/"volume";root.mkdir(mode=0o700)
        path=self.root/"manifest.sqlite3"
        bulk=BulkArchive((Volume("fixture",root,GIB),))
        archive=ManifestArchive(path,bulk)
        provision(path,SCOPE,offline_acknowledged=True)
        os.environ["SKL_DRAGON_HOARDER_MANIFEST_DB_PATH"]=str(path)
        os.environ["SKL_DRAGON_HOARDER_VOLUMES_JSON"]=json.dumps([{"name":"fixture","root":str(root),"payload_budget":GIB}])
        return path,bulk

    def test_nested_manifest_lanes_bound_into_qualification(self):
        path,bulk=self.manifest()
        paths=tuple(eco.manifest_paths(path))
        self.assertEqual(len(paths),10)
        self.assertEqual(ShardedManifestArchive(path,bulk).ledger_paths(),paths)
        paths[-1].unlink()
        with self.assertRaises(OSError):tuple(eco.manifest_paths(path))

    def test_complete_export_and_exact_restore(self):
        path,bulk=self.manifest()
        dataset=self.root/"datasets";dataset.mkdir(mode=0o700)
        os.environ["SKL_DRAGON_DATASET_ROOT"]=str(dataset)
        legacy=shard_path(dataset,17)
        legacy.touch(mode=0o600)
        with sqlite3.connect(legacy) as db:db.execute("CREATE TABLE fixture(v INTEGER)")
        source=eco._enumerate()
        self.assertEqual(len(source),13)
        destination=self.root/"backup"
        result=eco.export(destination,offline_acknowledged=True)
        self.assertEqual(result["planes"]["primary_manifest"],10)
        self.assertEqual(result["planes"]["primary_payload"],1)
        self.assertFalse(result["mongo_included"])
        self.assertEqual(eco.verify(destination),result)
        saved=self.root/"saved";saved.mkdir(mode=0o700)
        for i,(_,file) in enumerate(source):file.rename(saved/str(i))
        restore=eco.restore_new(destination,offline_acknowledged=True)
        self.assertEqual(restore["new_files"],13)
        self.assertEqual(eco.restore_new(destination,offline_acknowledged=True)["new_files"],0)
        with sqlite3.connect(self.knowledge) as db:
            self.assertEqual(db.execute("SELECT v FROM fixture").fetchone()[0],"preserved")
            db.execute("INSERT INTO fixture VALUES('new')")
        with self.assertRaises(custody.DeploymentHeld):eco.restore_new(destination,offline_acknowledged=True)

    def test_missing_dataset_route_refuses_export(self):
        dataset=self.root/"datasets";dataset.mkdir(mode=0o700)
        os.environ["SKL_DRAGON_DATASET_ROOT"]=str(dataset)
        legacy=shard_path(dataset,0);legacy.touch(mode=0o600)
        with sqlite3.connect(legacy) as db:
            db.execute("CREATE TABLE dataset_game_routes(owner TEXT,game TEXT,lane INTEGER)")
            db.execute("INSERT INTO dataset_game_routes VALUES('a','b',7)")
        with self.assertRaises(OSError):eco.export(self.root/"backup",offline_acknowledged=True)
        self.assertFalse((self.root/"backup").exists())

    def test_alias_and_tamper_rejection(self):
        os.environ["SKL_DRAGON_PRACTICE_DB_PATH"]=str(self.knowledge)
        with self.assertRaises(custody.DeploymentHeld):eco._enumerate()
        del os.environ["SKL_DRAGON_PRACTICE_DB_PATH"]
        destination=self.root/"backup"
        with self.assertRaises(custody.DeploymentHeld):eco.export(destination)
        eco.export(destination,offline_acknowledged=True)
        with (destination/"pack-0"/"1.sqlite3").open("ab") as out:out.write(b"tamper")
        with self.assertRaises(custody.DeploymentHeld):eco.verify(destination)


    def test_sealed_payload_namespaced_readback(self):
        import hashlib
        path,bulk=self.manifest()
        archive=ShardedManifestArchive(path,bulk)
        raw=b"physical custody fixture"
        lanes=archive._lanes(SCOPE)
        operation=next(str(i) for i in range(100) if int(lanes.identifier("fixture",str(i))[:16],16)%10!=0)
        begun=archive.begin(SCOPE,logical_key="fixture",operation=operation,
                            expected_hash=hashlib.sha256(raw).hexdigest(),expected_bytes=len(raw))
        identifier=begun["manifest"]
        archive.append(SCOPE,identifier,0,raw);archive.seal(SCOPE,identifier)
        destination=self.root/"backup"
        eco.export(destination,offline_acknowledged=True)
        result=eco.audit_payloads(destination)
        self.assertEqual(result["sealed_manifests_verified"],1)
        self.assertEqual(result["decoded_bytes_verified"],len(raw))
        self.assertEqual(result["chunk_references_verified"],1)
