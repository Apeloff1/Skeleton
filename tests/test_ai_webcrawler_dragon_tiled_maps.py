"""Tiled TMX, TSX and JSON maps: tile caps, chunks, no asset loading, replay."""
from __future__ import annotations
import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.tiled_map_contracts import TiledAccumulator
from skeleton.ai.webcrawler.tiled_xml_documents import extract_tmx,extract_tsx
from skeleton.ai.webcrawler.tiled_json_documents import extract_tiled_json
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import CrawlPolicy,FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRun,CrawlRequest

TMX='''<?xml version="1.0" encoding="UTF-8"?>
<map version="1.10" orientation="orthogonal" renderorder="right-down"
width="4" height="3" tilewidth="16" tileheight="16" infinite="0">
<tileset firstgid="1" source="https://outside.example.net/PRIVATE_TILESET.tsx"/>
<layer id="1" name="Ground" width="4" height="3">
<data encoding="csv">1,0,2,0,0,0,0,0,3,0,4,0</data></layer>
<objectgroup id="2" name="Objects"><object id="1" name="SecretPortal"
x="12" y="24"><properties><property name="token" value="SECRET_OBJECT"/></properties></object>
</objectgroup>
<imagelayer id="3" name="Backdrop"><image source="https://outside.example.net/SECRET_BG.png"/></imagelayer>
</map>
'''
TSX='''<?xml version="1.0" encoding="UTF-8"?>
<tileset version="1.10" name="SecretAtlas" tilewidth="16" tileheight="16"
tilecount="24" columns="6">
<image source="https://outside.example.net/SECRET_TILE.png" width="96" height="64"/>
<tile id="0"><animation><frame tileid="1" duration="100"/>
<frame tileid="2" duration="100"/></animation></tile>
</tileset>
'''
JSON_MAP=json.dumps({
    "type":"map","orientation":"orthogonal","infinite":False,
    "width":4,"height":3,"tilewidth":16,"tileheight":16,
    "tilesets":[{"firstgid":1,"source":"https://outside.example.net/SECRET_TILESET"}],
    "properties":[{"name":"api_key","value":"SECRET_PROPERTY"}],
    "layers":[
        {"type":"tilelayer","width":4,"height":3,
         "data":[1,0,2,0,0,0,0,0,3,0,4,0]},
        {"type":"group","layers":[
            {"type":"objectgroup","objects":[
                {"id":1,"name":"SECRET_ACTOR","properties":[{"token":"SECRET"}]}
            ]},
        ]},
        {"type":"imagelayer","image":"https://outside.example.net/SECRET_BG"},
    ],
})
INFINITE=json.dumps({
    "type":"map","orientation":"orthogonal","infinite":True,
    "width":0,"height":0,"tilewidth":16,"tileheight":16,
    "layers":[{"type":"tilelayer","chunks":[
        {"x":-16,"y":0,"width":2,"height":2,"data":[1,0,0,2]},
        {"x":16,"y":0,"width":2,"height":2,"data":[0,3,0,4]},
    ]}],
    "tilesets":[],
})

class TiledMapKernelTests(unittest.TestCase):
    def test_gids_flip_bits_and_finite_matrix(self):
        acc=TiledAccumulator(tile_width=16,tile_height=16,
                             width=2,height=2,infinite=False)
        acc.layer()
        acc.tile_data([1,0,0x80000005,4],width=2,height=2)
        result=acc.result()
        self.assertEqual(result.cells,4)
        self.assertEqual(result.occupied_cells,3)
        self.assertEqual(result.flipped_cells,1)
        self.assertEqual(result.max_gid,5)
        self.assertFalse(result.game_engine_executed)
        self.assertFalse(result.source_references_opened)

    def test_wrong_size_and_uint32_value_denied(self):
        acc=TiledAccumulator(tile_width=16,tile_height=16,
                             width=2,height=2,infinite=False)
        acc.layer()
        with self.assertRaises(ResearchFormatError):
            acc.tile_data([1,2,3],width=2,height=2)
        with self.assertRaises(ResearchFormatError):
            acc.tile_data([1,2,3,0x1FFFFFFFF],width=2,height=2)

    def test_excessive_layers_and_objects_denied(self):
        acc=TiledAccumulator(tile_width=16,tile_height=16,
                             width=1,height=1,infinite=False)
        for _ in range(256):
            acc.layer()
        with self.assertRaises(ResearchFormatError):
            acc.layer()
        with self.assertRaises(ResearchFormatError):
            acc.objects_add(2049)

class TMXTests(unittest.TestCase):
    def test_finite_tmx_cells_objects_and_media_refs_omitted(self):
        row=extract_tmx(TMX)
        self.assertIn("Finite tile IDs: 12; occupied cells: 4",row.text)
        self.assertIn("Objects declared: 1",row.text)
        self.assertIn("image layers: 1",row.text)
        self.assertIn("external tileset declarations: 1",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertNotIn("SECRET_OBJECT",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_entity_and_external_xml_reference_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_tmx('<!DOCTYPE map [<!ENTITY x SYSTEM "file:///etc/passwd">]>'+TMX)

    def test_tmx_csv_cell_count_fail_closed(self):
        bad=TMX.replace("1,0,2,0,0,0,0,0,3,0,4,0",
                        "1,0,2,0,0,0,0,0,3,0,4")
        with self.assertRaises(ResearchFormatError):
            extract_tmx(bad)

    def test_compression_not_executed(self):
        bad=TMX.replace('encoding="csv"','encoding="base64" compression="zlib"')
        with self.assertRaises(ResearchFormatError):
            extract_tmx(bad)

    def test_infinite_tmx_chunks_with_inert_coordinates(self):
        raw='''<map orientation="orthogonal" width="0" height="0"
        tilewidth="16" tileheight="16" infinite="1">
        <layer width="0" height="0"><data encoding="csv">
        <chunk x="-8" y="0" width="2" height="2">1,0,0,2</chunk>
        <chunk x="8" y="0" width="2" height="2">0,3,0,4</chunk>
        </data></layer></map>'''
        row=extract_tmx(raw)
        self.assertIn("infinite: True",row.text)
        self.assertIn("chunks declared: 2",row.text)
        self.assertIn("occupied cells: 4",row.text)

    def test_tmx_xml_tile_entries_without_csv(self):
        raw='''<map orientation="orthogonal" width="2" height="1"
        tilewidth="16" tileheight="16" infinite="0">
        <layer width="2" height="1"><data>
        <tile gid="1"/><tile gid="2"/></data></layer></map>'''
        self.assertIn("occupied cells: 2",extract_tmx(raw).text)

class TSXTests(unittest.TestCase):
    def test_tilecount_and_animation_without_fetching_image(self):
        row=extract_tsx(TSX)
        self.assertIn("Tiles declared: 24",row.text)
        self.assertIn("Animation frame declarations: 2",row.text)
        self.assertIn("image references: 1",row.text)
        self.assertNotIn("SECRET_TILE",row.text)
        self.assertEqual(row.links,())

    def test_invalid_animation_tile_id_denied(self):
        bad=TSX.replace('<tile id="0">','<tile id="-1">')
        with self.assertRaises(ResearchFormatError):
            extract_tsx(bad)

class JSONMapTests(unittest.TestCase):
    def test_finite_json_layers_and_private_attrs_omitted(self):
        row=extract_tiled_json(JSON_MAP)
        self.assertIn("Layers: 3; image layers: 1",row.text)
        self.assertIn("Objects declared: 1",row.text)
        self.assertIn("occupied cells: 4",row.text)
        self.assertNotIn("SECRET_BG",row.text)
        self.assertNotIn("SECRET_PROPERTY",row.text)
        self.assertEqual(row.links,())

    def test_infinite_chunk_bounds(self):
        row=extract_tiled_json(INFINITE)
        self.assertIn("infinite: True",row.text)
        self.assertIn("chunks declared: 2",row.text)
        self.assertIn("occupied cells: 4",row.text)

    def test_duplicate_json_field_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_tiled_json('{"type":"map","type":"map"}')

    def test_wrong_matrix_and_nonfinite_denied(self):
        wrong=json.loads(JSON_MAP)
        wrong["layers"][0]["data"]=[1,2,3]
        with self.assertRaises(ResearchFormatError):
            extract_tiled_json(json.dumps(wrong))
        with self.assertRaises(ResearchFormatError):
            extract_tiled_json('{"type":"map","tilewidth":NaN}')

    def test_unsupported_layer_class_fails_closed(self):
        wrong=json.loads(JSON_MAP)
        wrong["layers"].append({"type":"injected-script","url":"https://outside.example.net"})
        with self.assertRaises(ResearchFormatError):
            extract_tiled_json(json.dumps(wrong))

class SourceTransport:
    timeout_seconds=4
    transport_mode="scripted_tiled_game_map"
    def __init__(self,mime,raw):
        self.mime,self.body,self.calls=mime,raw.encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/map":
            raise AssertionError("Tiled source requested external tileset/image/script")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())

class CanonicalTiledTests(unittest.TestCase):
    def test_maps_and_tilesets_are_captured_by_same_worker(self):
        for mime,raw,expected in (
            ("application/x-tiled-tmx+xml",TMX,"occupied cells: 4"),
            ("application/x-tiled-tsx+xml",TSX,"Tiles declared: 24"),
            ("application/x-tiled-map+json",JSON_MAP,"occupied cells: 4"),
            ("application/vnd.tiled.map+json",INFINITE,"chunks declared: 2"),
        ):
            with self.subTest(mime=mime):
                now=time.time()
                fetcher=SourceTransport(mime,raw)
                run=CrawlRun.create(
                    CrawlRequest(seed_urls=("https://example.com/map",),
                        allowed_hosts=("example.com",),max_depth=1,
                        max_requests=4,max_documents=2,
                        max_response_bytes=65536,max_total_bytes=131072),
                    scope={"tenant_id":"t","owner_id":"o"},
                    consent={"consent_id":"map-source-rights",
                             "capture_acknowledged":True,
                             "source_rights_acknowledged":True,
                             "expires_at":now+3600},
                    now=now,fetcher=fetcher)
                for offset in (1,3):
                    with patch("skeleton.ai.webcrawler.operations.time.time",
                               return_value=now+offset):
                        run.run_slice(max_steps=1,max_seconds=1,
                            authorize=lambda:None,cancelled=lambda:False,
                            on_checkpoint=lambda snap,event:None)
                state=run.snapshot()
                self.assertEqual(len(fetcher.calls),2)
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(state["frontier"],[])
                record=run.sources()[0]
                self.assertIn(expected,record["text"])
                self.assertEqual(record["review_state"],"unreviewed")
                self.assertFalse(record["provenance"]["training_permission"])
                self.assertEqual(CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state)

    def test_mime_allowlist_closed(self):
        values=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("application/x-tiled-tmx+xml",
                     "application/x-tiled-tsx+xml",
                     "application/x-tiled-map+json"):
            self.assertIn(mime,values)
        self.assertNotIn("application/x-msdownload",values)

if __name__=="__main__":
    unittest.main()
