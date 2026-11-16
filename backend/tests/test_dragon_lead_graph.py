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


class OfflineExportInspectionTests(TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/"input.csv"

    def fixture(self):
        raw=b"AppID,Name\n10000001,Alpha\n10000002,Beta\n"
        self.path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def test_inspect_is_graph_free_and_exact_hash_bound(self):
        from core.dragon_lead_ingest import inspect_export
        expected=self.fixture()
        with patch("core.dragon_lead_ingest.LeadGraph",side_effect=AssertionError("graph must stay closed")):
            result=inspect_export(self.path,"steam-csv","steam",expected_sha=expected)
        self.assertEqual(result["input_sha256"],expected)
        self.assertTrue(result["expected_sha_matched"])
        self.assertEqual(result["rows"],2)
        self.assertEqual(result["pages"],1)
        for field in ("network_executed","graph_written","license_verified","source_rights_verified"):
            self.assertIs(result[field],False)

    def test_hash_mismatch_precedes_any_projection(self):
        from core.dragon_lead_ingest import qualify
        self.fixture()
        with patch("core.dragon_lead_ingest.pages",side_effect=AssertionError("must not parse")):
            with self.assertRaisesRegex(ValueError,"SHA-256 differs"):
                qualify(self.path,"steam-csv","steam",expected_sha="0"*64)

    def test_unsupported_and_cross_projection_modes_fail_before_io(self):
        from core.dragon_lead_ingest import inspect_export
        for format,projection in (("unknown","steam"),("steam-csv","locator"),
                                  ("normalized-jsonl","unknown")):
            with self.subTest(format=format,projection=projection):
                with self.assertRaises(ValueError):
                    inspect_export(self.path,format,projection)

    def test_raw_byte_drift_blocks_graph_begin(self):
        from core.dragon_lead_ingest import ingest
        from unittest.mock import Mock
        expected=self.fixture()
        graph=Mock()
        # Model mutation despite an unchanged filesystem witness.
        with patch("core.dragon_lead_ingest._source_hash",side_effect=[expected,"0"*64]):
            with self.assertRaisesRegex(ValueError,"changed during qualification"):
                ingest(graph,OWNER,path=self.path,format="steam-csv",projection="steam",
                       target="steam-fronkon",rights_reference="fixture",grant_seconds=86400)
        graph.begin.assert_not_called()

    def test_normalized_page_revalidation_precedes_writes(self):
        from core.dragon_lead_ingest import qualify
        self.fixture()
        with patch("core.dragon_lead_ingest.steam_csv",return_value=iter([{"appid":"garbage","title":"Bad"}])):
            with self.assertRaises(ValueError):
                qualify(self.path,"steam-csv","steam")

    def test_modrinth_export_rejects_duplicate_keys_and_nonfinite_numbers(self):
        from core.dragon_lead_ingest import modrinth_json
        from io import BytesIO
        for raw in (b'{"hits":[],"hits":[]}',b'{"hits":[],"score":NaN}'):
            with self.assertRaises(ValueError):
                list(modrinth_json(BytesIO(raw)))

    def test_cli_inspection_does_not_require_or_open_owner_storage(self):
        from core.dragon_lead_ingest import main
        from contextlib import redirect_stdout
        from io import StringIO
        self.fixture()
        output=StringIO()
        with patch("core.dragon_lead_ingest.LeadGraph",side_effect=AssertionError("storage opened")):
            with redirect_stdout(output):
                status=main(["--inspect-only","--input",str(self.path),"--format","steam-csv"])
        self.assertEqual(status,0)
        self.assertFalse(json.loads(output.getvalue())["graph_written"])


class StrictLocalTabularExportTests(TestCase):
    def test_steam_tsv_matches_csv_projection(self):
        from io import BytesIO
        from core.dragon_lead_ingest import steam_csv
        csv_rows=list(steam_csv(BytesIO(b'AppID,Name,Notes\r\n1001,"Alpha, Beta","one\ntwo"\r\n')))
        tsv_rows=list(steam_csv(BytesIO(b'AppID\tName\tNotes\r\n1001\t"Alpha, Beta"\t"one\ntwo"\r\n'),delimiter="\t"))
        self.assertEqual(csv_rows,tsv_rows)
        self.assertEqual(tsv_rows,[{"appid":"1001","title":"Alpha, Beta"}])

    def test_wikidata_tsv_and_locator_tsv_match_canonical_schema(self):
        from io import BytesIO
        from core.dragon_lead_ingest import wikidata_csv,locator_csv
        rows=list(wikidata_csv(BytesIO(b"item\titemLabel\nhttps://www.wikidata.org/entity/Q1234\tA game\n"),delimiter="\t"))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["subject"],"wikidata:Q1234")
        link=list(locator_csv(BytesIO(b"url\ttitle\tkind\tsubject\nhttps://www.wikidata.org/wiki/Q1234\tA game\tcross_database_identifiers\twikidata:Q1234\n"),delimiter="\t"))
        self.assertEqual(link,rows)

    def test_malformed_rows_and_ambiguous_headers_rejected(self):
        from io import BytesIO
        from core.dragon_lead_ingest import steam_csv
        for raw in (b"AppID,Name,Other\n1001,A\n",b"AppID,Name\n1001,A,B\n",
                    b"AppID,Name,name\n1001,A,A\n",b"AppID,Name\n1001,\"unterminated\n",
                    b"AppID,Name,\n1001,A,B\n"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    list(steam_csv(BytesIO(raw)))

    def test_logical_multiline_record_cap_and_limit_restoration(self):
        import csv
        from io import BytesIO
        from core.dragon_lead_ingest import steam_csv
        before=csv.field_size_limit()
        raw=BytesIO(b'AppID,Name,Note\n1001,A,"123456789\n123456789\n123456789"\n')
        with patch("core.dragon_lead_ingest.MAX_RECORD_CHARS",30):
            with self.assertRaisesRegex(ValueError,"logical record"):
                list(steam_csv(raw))
        self.assertEqual(csv.field_size_limit(),before)
        self.assertFalse(raw.closed)

    def test_tsv_qualification_preserves_projection_page_chain(self):
        from core.dragon_lead_ingest import inspect_export
        with TemporaryDirectory() as directory:
            csv_path=Path(directory)/"games.csv"
            tsv_path=Path(directory)/"games.tsv"
            csv_path.write_bytes(b"AppID,Name\n1001,Alpha\n1002,Beta\n")
            tsv_path.write_bytes(b"AppID\tName\n1001\tAlpha\n1002\tBeta\n")
            a=inspect_export(csv_path,"steam-csv","steam")
            b=inspect_export(tsv_path,"steam-tsv","steam")
            self.assertEqual(a["page_chain"],b["page_chain"])
            self.assertNotEqual(a["input_sha256"],b["input_sha256"])


class LocalVersionedDatasetIntegrityTests(TestCase):
    def test_jsonl_plan_witnesses_entire_file(self):
        from core.dragon_dataset_ingest import plan
        with TemporaryDirectory() as directory:
            path=Path(directory)/"records.jsonl"
            raw=b'{"_key":1,"name":"Fixture"}\n'
            path.write_bytes(raw)
            expected=hashlib.sha256(raw).hexdigest()
            receipt=plan(path,expected_sha=expected)
            self.assertEqual(receipt["input_sha256"],expected)
            self.assertTrue(receipt["expected_sha_matched"])
            self.assertEqual(receipt["expected_rows"],1)
            with self.assertRaisesRegex(ValueError,"SHA-256 differs"):
                plan(path,expected_sha="0"*64)

    def test_zip_container_identity_is_distinct_from_member_chain(self):
        import zipfile
        from core.dragon_dataset_ingest import plan
        with TemporaryDirectory() as directory:
            path=Path(directory)/"data.zip"
            with zipfile.ZipFile(path,"w") as archive:
                archive.writestr("rows.jsonl",b'{"_key":1,"name":"Fixture"}\n')
                archive.writestr("notes.txt",b"version one")
            a=plan(path,"rows.jsonl")
            with zipfile.ZipFile(path,"w") as archive:
                archive.writestr("rows.jsonl",b'{"_key":1,"name":"Fixture"}\n')
                archive.writestr("notes.txt",b"version two")
            b=plan(path,"rows.jsonl")
            self.assertEqual(a["expected_chain"],b["expected_chain"])
            self.assertNotEqual(a["input_sha256"],b["input_sha256"])

    def test_mutated_container_fails_before_version_reservation(self):
        from core.dragon_dataset_ingest import ingest
        from unittest.mock import Mock
        with TemporaryDirectory() as directory:
            path=Path(directory)/"records.jsonl"
            path.write_bytes(b'{"_key":1,"name":"Fixture"}\n')
            shard=Mock()
            with patch("core.dragon_dataset_ingest.raw_sha256",side_effect=["a"*64,"b"*64]):
                with self.assertRaisesRegex(ValueError,"changed during projection"):
                    ingest(shard,path,dataset="fixture",source="fixture",observation_digest="c"*64,
                           label="fixture",rights_acknowledged=True)
            shard.begin.assert_not_called()


class OfflineInspectionBindingTests(TestCase):
    def test_lead_inspection_mismatch_precedes_storage_factory(self):
        from core.dragon_lead_ingest import ingest,inspect_export
        from unittest.mock import Mock
        with TemporaryDirectory() as directory:
            path=Path(directory)/"games.csv"
            path.write_bytes(b"AppID,Name\n1001,Alpha\n")
            before=inspect_export(path,"steam-csv","steam")
            path.write_bytes(b"AppID,Name\n1001,Beta\n")
            factory=Mock()
            with self.assertRaisesRegex(ValueError,"inspection digest differs"):
                ingest(None,OWNER,path=path,format="steam-csv",projection="steam",
                       target="steam-fronkon",rights_reference="fixture",grant_seconds=86400,
                       expected_inspection=before["inspection_digest"],graph_factory=factory)
            factory.assert_not_called()

    def test_inspection_token_binds_format_even_for_identical_projection(self):
        from core.dragon_lead_ingest import _inspection_identity
        a=_inspection_identity("steam-csv","steam","a"*64,1,"b"*64,1)
        for values in (
            ("steam-tsv","steam","a"*64,1,"b"*64,1),
            ("steam-csv","steam","c"*64,1,"b"*64,1),
            ("steam-csv","steam","a"*64,2,"b"*64,1),
            ("steam-csv","steam","a"*64,1,"d"*64,1),
            ("steam-csv","steam","a"*64,1,"b"*64,2),
        ):
            self.assertNotEqual(a,_inspection_identity(*values))

    def test_versioned_inspection_is_graph_free_and_binds_selected_member(self):
        from core.dragon_dataset_ingest import inspect_dataset
        import zipfile
        with TemporaryDirectory() as directory:
            path=Path(directory)/"records.zip"
            with zipfile.ZipFile(path,"w") as archive:
                for name in ("a.jsonl","b.jsonl"):
                    archive.writestr(name,b'{"_key":1,"name":"Fixture"}\n')
            with patch("core.dragon_dataset_ingest.DatasetShard",side_effect=AssertionError("storage opened")):
                a=inspect_dataset(path,"a.jsonl")
                b=inspect_dataset(path,"b.jsonl")
            self.assertEqual(a["input_sha256"],b["input_sha256"])
            self.assertEqual(a["expected_chain"],b["expected_chain"])
            self.assertNotEqual(a["inspection_digest"],b["inspection_digest"])
            self.assertFalse(a["storage_written"])

    def test_versioned_inspection_mismatch_precedes_shard_factory(self):
        from core.dragon_dataset_ingest import ingest,inspect_dataset
        from unittest.mock import Mock
        with TemporaryDirectory() as directory:
            path=Path(directory)/"records.jsonl"
            path.write_bytes(b'{"_key":1,"name":"Before"}\n')
            before=inspect_dataset(path)
            path.write_bytes(b'{"_key":1,"name":"After"}\n')
            factory=Mock()
            with self.assertRaisesRegex(ValueError,"inspection digest differs"):
                ingest(None,path,dataset="fixture",source="fixture",observation_digest="c"*64,
                       label="fixture",rights_acknowledged=True,
                       expected_inspection=before["inspection_digest"],shard_factory=factory)
            factory.assert_not_called()

    def test_versioned_cli_inspection_never_initializes_storage(self):
        from core.dragon_dataset_ingest import main
        from contextlib import redirect_stdout
        from io import StringIO
        with TemporaryDirectory() as directory:
            path=Path(directory)/"data.jsonl"
            path.write_bytes(b'{"_key":1,"name":"Fixture"}\n')
            out=StringIO()
            with patch("core.dragon_dataset_ingest.DatasetShard",side_effect=AssertionError("storage opened")):
                with redirect_stdout(out):
                    self.assertEqual(main(["--inspect-only","--path",str(path)]),0)
            self.assertFalse(json.loads(out.getvalue())["storage_written"])


class OfflineSparqlExportTests(TestCase):
    def fixture(self):
        return {"head":{"vars":["item","itemLabel"]},"results":{"bindings":[
            {"item":{"type":"uri","value":"http://www.wikidata.org/entity/Q1234"},
             "itemLabel":{"type":"literal","xml:lang":"en","value":"Game fixture"}}]}}

    def test_sparql_export_matches_existing_filtered_locator_projection(self):
        from core.dragon_lead_ingest import wikidata_sparql_json,wikidata_csv
        from io import BytesIO
        raw=json.dumps(self.fixture()).encode()
        result=list(wikidata_sparql_json(BytesIO(raw)))
        csv_result=list(wikidata_csv(BytesIO(b"item,itemLabel\nQ1234,Game fixture\n")))
        self.assertEqual(result,csv_result)

    def test_sparql_export_rejects_foreign_entity_and_nonliteral_label(self):
        from core.dragon_lead_ingest import wikidata_sparql_json
        from io import BytesIO
        for field,value in (("item",{"type":"uri","value":"https://example.com/Q1234"}),
                            ("itemLabel",{"type":"uri","value":"https://example.com/"}),
                            ("item",{"type":"bnode","value":"Q1234"})):
            payload=self.fixture()
            payload["results"]["bindings"][0][field]=value
            with self.assertRaises(ValueError):
                list(wikidata_sparql_json(BytesIO(json.dumps(payload).encode())))

    def test_sparql_export_rejects_duplicate_fields_and_missing_required_binding(self):
        from core.dragon_lead_ingest import wikidata_sparql_json
        from io import BytesIO
        payload=self.fixture()
        del payload["results"]["bindings"][0]["itemLabel"]
        for raw in (json.dumps(payload).encode(),b'{"head":{},"head":{},"results":{}}'):
            with self.assertRaises(ValueError):
                list(wikidata_sparql_json(BytesIO(raw)))

