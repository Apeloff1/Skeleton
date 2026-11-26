"""No-network regression and optional industrial workload qualification."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,skipUnless
from unittest.mock import patch

from core.dragon_dataset_library import census,library,target
from core.dragon_game_corpus import CatalogueHeld,digest
from core.dragon_lead_graph import (
    LeadGraph,MAX_PAGE_ROWS,MAX_NODES,MAX_EDGES,ZERO,bootstrap_inventory,lead_id,
    parse_page,project,
)
from core.dragon_lead_ingest import ingest
from core.dragon_release_queue import ReleaseQueue

OWNER={"tenant_id":"tenant","owner_id":"owner"}
OTHER={"tenant_id":"tenant","owner_id":"other"}

def encode(rows):
    return b"".join(json.dumps(x,sort_keys=True,separators=(",",":")).encode()+b"\n" for x in rows)

class DatasetLibraryTests(TestCase):
    def test_registry_and_revision_cursors(self):
        stats=census()
        self.assertGreaterEqual(stats["targets"],109)
        self.assertGreaterEqual(len(stats["domains"]),8)
        self.assertFalse(stats["network_authorized"])
        result=library(domain="mods",limit=2)
        self.assertTrue(result["next_cursor"])
        with self.assertRaises(ValueError):
            library(domain="games",after=result["next_cursor"])
        seen=[];after=None
        while True:
            result=library(after=after,limit=13)
            seen.extend(x["id"] for x in result["targets"])
            for x in result["targets"]:
                self.assertFalse(x["network_authorized"])
                self.assertFalse(x["license_verified"])
            after=result["next_cursor"]
            if after is None:break
        self.assertEqual(seen,sorted(set(seen)))
        self.assertEqual(len(seen),stats["targets"])
        self.assertEqual(target("speedrun-archive")["access"],"noncommercial_only")

    def test_exact_bundle_inventory(self):
        from core.dragon_bundled_steam_leads import inventory, summary, _shard
        revision,_,total,_,shards=inventory()
        self.assertEqual(total,200704)
        seen=0;previous=0
        for i in range(len(shards)):
            _,rows=_shard(revision,i)
            for appid,title in rows:
                self.assertGreater(int(appid),previous)
                self.assertTrue(title)
                previous=int(appid);seen+=1
        self.assertEqual(seen,200704)
        self.assertEqual(summary()["store_locator_floor"],seen)

    def test_projection_cannot_invent_ids_or_fetch(self):
        rows=parse_page(encode([{"appid":"10000001","title":"Synthetic qualification game"}]),"steam")
        routes=list(project(rows[0],"steam"))
        self.assertEqual(len(routes),17)
        self.assertEqual(len({lead_id(x[0]) for x in routes}),17)
        self.assertTrue(all("10000001" in x[0] for x in routes))
        for bad in ({"appid":"0","title":"bad"},{"appid":"https://example.org","title":"bad"},
                    {"appid":"12345","title":"bad","url":"https://example.org"}):
            with self.assertRaises(ValueError):parse_page(encode([bad]),"steam")
        with self.assertRaises(ValueError):
            parse_page(encode([{"url":"https://127.0.0.1/","title":"No","kind":"public_csv_dataset","subject":"source"}]),"locator")

class LeadGraphTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        reserve=patch("core.dragon_lead_graph.MIN_RESERVE",0)
        reserve.start();self.addCleanup(reserve.stop)
        self.path=Path(tmp.name).resolve()/"corpus.sqlite3"
        self.graph=LeadGraph(self.path)
        self.graph.configure(OWNER,enabled=True,acknowledged=True)

    def begin(self,count=1,source="a"*64,projection="steam",target_id="steam-fronkon"):
        return self.graph.begin(OWNER,target_id=target_id,projection=projection,source_sha=source,
            expected_rows=count,rights_ref="fixture-metadata-rights",grant_seconds=86400,acknowledged=True)

    def append(self,snap,rows,ordinal=0,previous=ZERO):
        raw=encode(rows)
        return self.graph.append(OWNER,snap["snapshot_id"],ordinal=ordinal,raw=raw,
            sha256=hashlib.sha256(raw).hexdigest(),previous_chain=previous)

    def test_bundled_page_pulse_and_rights(self):
        with self.assertRaises(ValueError):
            self.graph.enable_bundle(OWNER,rights_ref="fixture",grant_seconds=86400,acknowledged=False)
        started=self.graph.enable_bundle(OWNER,rights_ref="fixture",grant_seconds=86400,acknowledged=True)
        self.assertEqual(started["snapshot_identity_candidates_ingested"],0)
        self.assertEqual(started["title_identity_candidates"],200704)
        sid=started["snapshot"]["id"]
        bad=encode([{"appid":"10000001","title":"wrong pinned identity"}])
        with self.assertRaises(CatalogueHeld):
            self.graph.append(OWNER,sid,ordinal=0,raw=bad,sha256=hashlib.sha256(bad).hexdigest(),previous_chain=ZERO)
        self.graph.bundle_pulse()
        self.graph=LeadGraph(self.path)
        self.assertEqual(self.graph.bundle_status(OWNER)["snapshot_identity_candidates_ingested"],512)
        self.assertEqual(self.graph.bundle_status(OTHER)["snapshot_identity_candidates_ingested"],0)
        self.graph.expansion_pulse()
        self.graph.revoke(OWNER,sid)
        self.graph.bundle_pulse()
        self.assertEqual(self.graph.bundle_status(OWNER)["snapshot_identity_candidates_ingested"],512)

    def test_snapshot_replay_restart_and_owner_scope(self):
        snap=self.begin(2)
        page=[{"appid":"10000001","title":"Fixture One"}]
        one=self.append(snap,page)
        self.graph=LeadGraph(self.path)
        same=self.append(snap,page)
        self.assertTrue(same["replayed"])
        self.assertEqual(same["chain"],one["chain"])
        with self.assertRaises(CatalogueHeld):
            self.append(snap,[{"appid":"10000002","title":"Wrong replay"}])
        with self.assertRaises(CatalogueHeld):self.graph.seal(OWNER,snap["id"],one["chain"])
        two=self.append(snap,[{"appid":"10000002","title":"Fixture Two"}],1,one["chain"])
        sealed=self.graph.seal(OWNER,snap["id"],two["chain"])
        self.assertEqual(sealed["state"],"sealed")
        status=self.graph.status(OWNER)
        self.assertEqual(status["nodes"],35)
        self.assertFalse(status["growth_floor_met"])
        self.assertEqual(self.graph.status(OTHER)["nodes"],0)
        with self.assertRaises(LookupError):self.graph.snapshot(OTHER,snap["id"])
        edges=self.graph.edges(OWNER,snap["root"],limit=100)["edges"]
        self.assertEqual(len(edges),34)
        self.assertTrue(all(e["snapshot"]==snap["id"] and e["snapshot_state"]=="sealed" for e in edges))
        self.graph.revoke(OWNER,snap["id"])
        self.assertEqual(self.graph.edges(OWNER,snap["root"],limit=1)["edges"][0]["snapshot_state"],"revoked")
        self.assertEqual(self.graph.status(OWNER)["nodes"],35)

    def test_duplicate_provider_identity_creates_history_not_nodes(self):
        row={"appid":"10000001","title":"Fixture"}
        a=self.begin(source="a"*64);b=self.begin(source="b"*64)
        self.graph.seal(OWNER,a["id"],self.append(a,[row])["chain"])
        before=self.graph.status(OWNER)
        self.graph.seal(OWNER,b["id"],self.append(b,[row])["chain"])
        after=self.graph.status(OWNER)
        self.assertEqual(before["nodes"],after["nodes"])
        self.assertEqual(after["edges"]-before["edges"],17)
        self.assertTrue(self.graph.page(OWNER,q="Fixture")["leads"])
        self.assertFalse(self.graph.page(OTHER,q="Fixture")["leads"])

    def test_dataset_library_grows_from_feed_and_registration(self):
        raw=json.dumps({"schema":"dragon.game-feed.v1","provider":"independent","entries":[
            {"id":"g","title":"Fixture","links":[{"url":"https://example.org/new-dataset.csv","kind":"public_csv_dataset","language":"und"}]}]}).encode()
        self.graph.feed_page(OWNER,url="https://example.org/feed.xml",raw=raw,adapter="manifest",options={},subscription_id="c"*64)
        candidates=self.graph.dataset_candidates(OWNER)["candidates"]
        data=next(r for r in candidates if r["url"]=="https://example.org/new-dataset.csv")
        register=self.graph.register_target(OWNER,data["id"],projection="locator",rights_ref="fixture",
            grant_seconds=86400,enabled=True,acknowledged=True)
        snap=self.graph.begin(OWNER,target_id=register["target_id"],projection="locator",
            source_sha="d"*64,expected_rows=1,rights_ref="fixture",grant_seconds=7200,acknowledged=True)
        result=self.append(snap,[{"url":"https://example.org/tool","kind":"mod_documentation","title":"Tool","subject":"mod:fixture"}])
        self.assertEqual(result["rows"],1)
        self.graph.register_target(OWNER,data["id"],projection="locator",rights_ref="fixture",
            grant_seconds=86400,enabled=False,acknowledged=True)
        self.assertEqual(self.graph.snapshot(OWNER,snap["id"])["state"],"revoked")

    def test_canonical_import_outbox_continuously_expands(self):
        raw=json.dumps({"applist":{"apps":[{"appid":10000001,"name":"Fixture from feed"}]}}).encode()
        queue=ReleaseQueue(self.path)
        queue.enqueue(OWNER,raw=raw,adapter="steam",operation="fixture")
        queue.pulse(limit=4)
        self.assertEqual(self.graph.catalogue_pulse()["processed"],1)
        self.assertEqual(self.graph.catalogue_pulse()["processed"],0)
        self.assertEqual(self.graph.expansion_pulse()["processed"],1)
        self.assertEqual(self.graph.expansion_pulse()["processed"],0)
        self.assertEqual(self.graph.status(OWNER)["nodes"],17)

    def test_seed_bootstrap_checkpoint(self):
        revision,inventory=bootstrap_inventory()
        self.assertGreaterEqual(len(inventory),14780)
        a=self.graph.bootstrap_pulse()
        self.assertEqual(a["processed"],256)
        b=self.graph.status(OWNER)
        self.assertEqual(b["bootstrap_cursor"],256)
        self.assertEqual(b["bootstrap_revision"],revision)
        self.graph=LeadGraph(self.path)
        self.graph.configure(OWNER,enabled=False,acknowledged=True)
        self.assertEqual(self.graph.bootstrap_pulse()["processed"],0)
        self.graph.configure(OWNER,enabled=True,acknowledged=True)
        self.assertEqual(self.graph.bootstrap_pulse()["processed"],256)
        self.assertEqual(self.graph.status(OWNER)["bootstrap_cursor"],512)

    def test_csv_streaming_integration(self):
        path=self.path.parent/"games.csv"
        path.write_text('AppID,Name,Description\n10000001,"Alpha, Beta","A line\nAnother line"\n10000002,Second,ignored\n',encoding="utf-8")
        result=ingest(self.graph,OWNER,path=path,format="steam-csv",projection="steam",
            target="steam-fronkon",rights_reference="fixture",grant_seconds=86400)
        self.assertEqual(result["state"],"sealed")
        self.assertEqual(result["rows"],2)
        self.assertEqual(self.graph.status(OWNER)["nodes"],35)
        again=ingest(self.graph,OWNER,path=path,format="steam-csv",projection="steam",
            target="steam-fronkon",rights_reference="fixture",grant_seconds=86400)
        self.assertTrue(again["already_sealed"])

    @skipUnless(os.getenv("SKL_DRAGON_LEAD_STRESS")=="1","explicit industrial fixture workload")
    def test_tenfold_projection_fixture(self):
        # Synthetic IDs are for load qualification ONLY; never ship as real
        # public game seeds or treat this as provider coverage.
        count=9000;snap=self.begin(count)
        chain=ZERO
        for ordinal,start in enumerate(range(0,count,MAX_PAGE_ROWS)):
            rows=[{"appid":str(100000000+n),"title":"Synthetic fixture "+str(n)}
                  for n in range(start,min(count,start+MAX_PAGE_ROWS))]
            receipt=self.append(snap,rows,ordinal,chain)
            chain=receipt["chain"]
        self.graph.seal(OWNER,snap["id"],chain)
        result=self.graph.status(OWNER)
        self.assertEqual(result["nodes"],1+count*17)
        self.assertTrue(result["growth_floor_met"])
        self.assertLess(result["nodes"],MAX_NODES)
        self.assertLess(result["edges"],MAX_EDGES)


class TenfoldLeadQuotaTests(TestCase):
    def test_lane_ranges_partition_the_entire_prefix_space(self):
        from core.dragon_lead_graph import lead_lane,lane_bounds,LEAD_LANES,MAX_NODES,MAX_EDGES
        self.assertEqual((LEAD_LANES,MAX_NODES,MAX_EDGES),(10,200_000_000,1_000_000_000))
        for n in range(65536):
            prefix=format(n,"04x")
            lane=lead_lane(prefix+"0"*60)
            low,high=lane_bounds(lane)
            self.assertTrue(low<=prefix<high)

    def test_partition_counts_replay_lazy_migration_and_isolation(self):
        from core.dragon_lead_graph import lead_lane,_schema_row
        from core.dragon_hoarder_bulk import owner_key
        with TemporaryDirectory() as d,patch("core.dragon_lead_graph.MIN_RESERVE",0):
            graph=LeadGraph(Path(d).resolve()/"corpus.sqlite")
            graph.configure(OWNER,enabled=True,acknowledged=True)
            graph.configure(OTHER,enabled=True,acknowledged=True)
            owner=owner_key(OWNER);other=owner_key(OTHER)
            row=_schema_row("https://example.org/game","fixture","storefront","fixture")
            lane=lead_lane(lead_id(row[0]))
            def add(db,witness,scope_owner=owner):
                return graph._add(db,scope_owner,row,parent=ZERO,relation="seed",witness=witness,now=1)
            with graph._db() as db:
                db.execute("BEGIN IMMEDIATE")
                add(db,"a"*64)
                add(db,"a"*64)
                add(db,"a"*64,other)
                db.execute("DELETE FROM lead_lane_counts WHERE owner=?",(owner,))
                add(db,"a"*64)
                counts=lambda who:tuple(db.execute("SELECT nodes,edges FROM lead_lane_counts WHERE owner=? AND lane=?",(who,lane)).fetchone())
                self.assertEqual(counts(owner),(1,1))
                self.assertEqual(counts(other),(1,1))
                with patch("core.dragon_lead_graph.EDGES_PER_LANE",1):
                    with self.assertRaises(CatalogueHeld):add(db,"b"*64)
                self.assertEqual(counts(owner),(1,1))
                db.execute("COMMIT")
            self.assertEqual(graph.status(OWNER)["nodes"],1)
            self.assertEqual(graph.status(OWNER)["edges"],1)
            self.assertFalse(graph.status(OWNER)["physical_graph_sharding"])
