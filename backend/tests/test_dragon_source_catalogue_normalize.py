"""Reviewed export conversion preserves only explicit public candidate metadata."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.webcrawler.source_catalogue_normalize import normalize, CENSUS_PUBLISHER


class SourceNormalizationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.input=self.root/"input"
        self.output=self.root/"sources.jsonl"
        self.receipt=self.root/"receipt.json"

    def convert(self,raw,mode,*,publisher="https://example.org/published/",pin=None):
        self.input.write_bytes(raw)
        return normalize(self.input,self.output,self.receipt,mode=mode,publisher=publisher,
                         rights_reference="fixture metadata only",
                         input_sha256=pin or hashlib.sha256(raw).hexdigest())

    def output_rows(self):
        return [json.loads(line) for line in self.output.read_text().splitlines()]

    def test_explicit_csv_holds_private_queries_and_does_not_invent(self):
        result=self.convert(b"name,url\nOne,https://example.org/one\nBad,https://example.org/?token=secret\nMissing,appid123\n",
                            "explicit-csv")
        self.assertEqual(result["counts"],{"inputs":3,"written":1,"explicit_url":1,"held":2})
        self.assertEqual(self.output_rows()[0]["url"],"https://example.org/one")
        self.assertEqual(result["output_sha256"],hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertFalse(result["unique_source_count_claimed"])
        self.assertFalse(result["network_authorized"])

    def test_itch_requires_explicit_no_and_does_not_copy_descriptions(self):
        raw=json.dumps([
            {"name":"Game","url":"https://example.itch.io/game","nsfw":"No","description":"not imported"},
            {"name":"Unknown","url":"https://example.itch.io/unknown"},
            {"name":"Restricted","url":"https://example.itch.io/restricted","nsfw":"Yes"},
        ]).encode()
        result=self.convert(raw,"itch-catalogue")
        self.assertEqual(result["counts"]["held"],2)
        self.assertEqual(len(self.output_rows()),1)
        self.assertNotIn("description",self.output_rows()[0])

    def test_wikidata_only_actual_website(self):
        result=self.convert(b"gameLabel,website\nGame,https://example.org/game\nNo Website,\n",
                            "wikidata-csv")
        self.assertEqual(result["counts"]["written"],1)
        self.assertEqual(result["counts"]["held"],1)

    def test_crosswalk_refuses_unqualified_ids_and_counts_urls_not_games(self):
        raw=(b"GAME_TITLE,URL_IGDB,URL_STEAMID,URL_METACRITIC,URL_HLTB,URL_WIKIPEDIA\n"
             b"Game,123,https://store.steampowered.com/app/555,,https://howlongtobeat.com/game/1,\n")
        result=self.convert(raw,"crosswalk-csv")
        self.assertEqual(result["counts"]["written"],2)
        self.assertEqual(result["counts"]["held"],1)
        self.assertFalse(result["unique_source_count_claimed"])

    def test_documented_publisher_route_not_accepted_from_other_publisher(self):
        raw=(b"app_id,name,slug,release_date,is_free,total_positive,total_negative,health_tier\n"
             b"42,Fixture,fixture-42,2026-01-01,true,10,1,healthy\n")
        with self.assertRaises(ValueError):
            self.convert(raw,"game-census-csv")
        result=self.convert(raw,"game-census-csv",publisher=CENSUS_PUBLISHER)
        self.assertEqual(result["counts"]["publisher_documented_mapping"],1)
        self.assertEqual(self.output_rows()[0]["url"],"https://thegamecensus.com/game/fixture-42")
        self.assertFalse(result["access_verified"])

    def test_github_page_and_jsonl(self):
        raw=json.dumps({"items":[{"full_name":"owner/project","html_url":"https://github.com/owner/project",
                                  "private":False,"archived":False},
                                 {"full_name":"owner/private","html_url":"https://github.com/owner/private",
                                  "private":True,"archived":False}]}).encode()
        result=self.convert(raw,"github-page")
        self.assertEqual(result["counts"]["written"],1)
        self.output.unlink()
        self.receipt.unlink()
        result=self.convert(b'{"title":"Fixture","url":"https://example.org/browser-game"}\n',
                            "browser-census-jsonl")
        self.assertEqual(result["counts"]["explicit_url"],1)

    def test_input_digest_and_header_fail_before_publication(self):
        raw=b"name,url\nGame,https://example.org/game\n"
        with self.assertRaisesRegex(ValueError,"input digest"):
            self.convert(raw,"explicit-csv",pin="0"*64)
        self.assertFalse(self.output.exists())
        raw=b'"url","url"\nhttps://example.org/game,https://example.org/game\n'
        with self.assertRaisesRegex(ValueError,"CSV header"):
            self.convert(raw,"explicit-csv")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.receipt.exists())


if __name__=="__main__":
    unittest.main()
