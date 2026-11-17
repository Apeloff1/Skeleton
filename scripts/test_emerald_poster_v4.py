"""Fail-closed synthetic and pinned-source custody checks; no device claims."""
import io,hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import publish_emerald_poster_v4 as p

class V4CustodyTests(unittest.TestCase):
    def test_exact_census(self):
        m,_=p.load()
        self.assertEqual(len(m["forms"]),5)
        self.assertEqual(sum(x["bytes"] for x in m["forms"]),562093868)
        self.assertEqual(sum(len(x["chunks"]) for x in m["forms"]),20)
        self.assertTrue(all(not x["stage"]=="hoarder" for x in m["forms"]))
        self.assertTrue(all(0<c["bytes"]<=32*1024**2 for x in m["forms"] for c in x["chunks"]))

    def test_pinned_hardware_boundary(self):
        pin=json.loads(p.PIN.read_bytes())
        self.assertEqual(pin["donorSha256"],"c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a")
        self.assertTrue(all(x["equipmentEnabled"] is False for x in pin["forms"].values()))
        self.assertEqual([x["growth"] for x in pin["forms"].values()],[
            "growth-hatchling-to-scout","growth-scout-to-scholar","growth-scholar-to-pathfinder",
            "growth-pathfinder-to-archivist","growth-archivist-to-hoarder"])

    def test_corrupt_manifest_fails(self):
        raw=json.loads(p.MANIFEST.read_bytes())
        raw["forms"][0]["sha256"]="0"*64
        original=Path.read_bytes
        with patch.object(Path,"read_bytes",autospec=True,side_effect=lambda self: json.dumps(raw).encode() if self==p.MANIFEST else original(self)):
            with self.assertRaisesRegex(ValueError,"model pin mismatch"):p.load()

    def test_truncated_stage_is_rejected(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as path:
            form=p.load()[0]["forms"][0]
            with self.assertRaisesRegex(ValueError,"required raw Git payload absent"):
                p.check_tree(Path(path),form)

    def test_unauthorized_push_url_is_denied(self):
        with patch.object(p,"git",side_effect=[b"https://github.com/Apeloff1/Skeleton.git\n",
                                               b"https://attacker.invalid/repo.git\n"]):
            with self.assertRaisesRegex(ValueError,"origin not authorized"):p.remote(Path("."))

    def test_bad_git_oid_is_denied(self):
        for raw in [b"",b"0"*39,b"f"*65,b"not-a-sha"]:
            with self.assertRaises(ValueError):p.oid(raw)

if __name__=="__main__":unittest.main()
