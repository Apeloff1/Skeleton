"""Focused acceptance for the retained audiovisual transcript authority."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import hashlib
import json
import sqlite3

from core.dragon_game_corpus import GameCorpus
from core.dragon_hoarder_bulk import owner_key
from core.dragon_media_archive import MediaArchive,SCHEMA as MEDIA
from core.dragon_media_captions import MediaCaptions,parse_captions,SCHEMA as CAPTIONS

SCOPE={"tenant_id":"tenant","owner_id":"owner"}
OTHER={"tenant_id":"tenant","owner_id":"other"}
MID="a"*64
VTT=b"WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nMining crystals\n\n00:00:04.000 --> 00:00:07.000\nRegional market order\n"
SRT=b"1\r\n00:00:01,000 --> 00:00:02,000\r\nOre & minerals\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,200\r\nShip fitting\r\n"


class CaptionParserTests(TestCase):
    def test_exact_milliseconds_and_plain_text(self):
        self.assertEqual(parse_captions(VTT,"vtt"),[(1000,3500,"Mining crystals"),(4000,7000,"Regional market order")])
        self.assertEqual(parse_captions(SRT,"srt")[1],(3000,4200,"Ship fitting"))
        self.assertEqual(parse_captions(b"WEBVTT\n\n00:01.000 --> 00:02.000\n<script>literal</script>","vtt")[0][2],"<script>literal</script>")

    def test_invalid_bounds_and_unsupported_layout(self):
        for raw in (
            b"WEBVTT\n\nSTYLE\n::cue {color:red;}",
            b"WEBVTT\n\n00:02.000 --> 00:01.000\nbad",
            b"WEBVTT\n\n00:60.000 --> 01:01.000\nbad",
            b"WEBVTT\n\n00:01.000 --> 00:02.000\nbad\x00",
            b"WEBVTT\n\n00:03.000 --> 00:04.000\nfirst\n\n00:01.000 --> 00:02.000\nsecond",
        ):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                parse_captions(raw,"vtt")


class CaptionCustodyTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"catalogue.sqlite3"
        # Only the catalogue and media row authority are needed for caption
        # indexing. The production media block store is never bypassed by reads.
        self.media=MediaArchive(self.path,store=object())
        self.captions=MediaCaptions(self.media)
        self.expiry=4_000_000_000
        with self.media._db() as db:
            db.executescript(MEDIA)
            for scope in (SCOPE,OTHER):
                db.execute("""INSERT INTO media_objects
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'sealed')""",
                    (owner_key(scope),MID,"b"*64,"c"*64,"d"*64,json.dumps(scope,sort_keys=True),
                     "op","video/mp4",12,"e"*64,"f"*64,1,self.expiry))

    def upload(self,scope=SCOPE,raw=VTT):
        return self.captions.import_track(scope,MID,language="en",format="vtt",raw=raw,rights_acknowledged=True)

    def test_replay_search_and_no_cross_owner_lookup(self):
        a=self.upload()
        self.assertFalse(a["replayed"])
        self.assertTrue(self.upload()["replayed"])
        self.assertEqual(a["sha256"],hashlib.sha256(VTT).hexdigest())
        self.assertEqual(self.captions.tracks(SCOPE,MID)["tracks"][0]["cues"],2)
        first=self.captions.query(SCOPE,MID,a["track_id"],limit=1)
        self.assertEqual(first["next_cursor"],0)
        self.assertEqual(self.captions.query(SCOPE,MID,a["track_id"],after=0)["cues"][0]["ordinal"],1)
        self.assertEqual(self.captions.query(SCOPE,MID,a["track_id"],q="market order")["cues"][0]["start_ms"],4000)
        self.assertEqual(self.captions.query(SCOPE,MID,a["track_id"],q="nonexistent")["cues"],[])
        self.assertFalse(self.captions.query(SCOPE,MID,a["track_id"])["training_allowed"])
        with self.assertRaises(LookupError):
            self.captions.query(OTHER,MID,a["track_id"])
        self.assertNotEqual(a["track_id"],self.upload(OTHER)["track_id"])

    def test_revocation_atomically_removes_derived_postings(self):
        a=self.upload();b=self.upload(OTHER)
        self.assertTrue(self.media.revoke(SCOPE,MID)["revoked"])
        with self.assertRaises(LookupError):self.captions.query(SCOPE,MID,a["track_id"])
        with self.media._db() as db:
            for table in ("media_tracks","media_cues","media_cue_fts"):
                self.assertEqual(db.execute("SELECT COUNT(*) FROM "+table+" WHERE owner=?",(owner_key(SCOPE),)).fetchone()[0],0)
        self.assertEqual(len(self.captions.query(OTHER,MID,b["track_id"])["cues"]),2)

    def test_expiry_and_caption_only_withdrawal(self):
        a=self.upload()
        with patch("core.dragon_media_archive.time.time",return_value=self.expiry+1):
            with self.assertRaises(LookupError):self.captions.tracks(SCOPE,MID)
        self.assertTrue(self.captions.revoke_track(SCOPE,MID,a["track_id"])["revoked"])
        self.assertEqual(self.captions.tracks(SCOPE,MID)["tracks"],[])
        self.assertEqual(self.media.metadata(SCOPE,MID)["state"],"sealed")

    def test_media_hash_binding(self):
        a=self.upload()
        with self.media._db() as db:
            db.execute("UPDATE media_objects SET sha256=? WHERE owner=? AND id=?",("1"*64,owner_key(SCOPE),MID))
        self.assertEqual(self.captions.tracks(SCOPE,MID)["tracks"],[])
        with self.assertRaises(LookupError):self.captions.query(SCOPE,MID,a["track_id"])
