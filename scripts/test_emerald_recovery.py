import hashlib
import tempfile
from pathlib import Path
import unittest

from recover_emerald_assets import discover, recover, copy_exact

DATA = {"web": b"web123", "source": b"source123", "model": b"model123456"}
def sha(data): return hashlib.sha256(data).hexdigest()
PIN = {"assetSet":"test",
       "web":{"bytes":len(DATA["web"]),"sha256":sha(DATA["web"])},
       "native":{"sourceBytes":len(DATA["source"]),"sourceSha256":sha(DATA["source"]),
                 "modelBytes":len(DATA["model"]),"modelSha256":sha(DATA["model"])}}


class RecoverTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.src=self.root/"src";self.src.mkdir()
        self.dest=self.root/"out";self.dest.mkdir()

    def setup_assets(self):
        for role,data in DATA.items():
            (self.src/(role+".renamed")).write_bytes(data)

    def test_discovery_uses_bytes_not_filename(self):
        self.setup_assets()
        (self.src/"emerald_continuum.glb").write_bytes(b"x"*len(DATA["model"]))
        result=discover([self.src],PIN)
        self.assertTrue(result["all_exact_assets_located"])
        self.assertEqual(len(result["matches"]["model"]),1)
        self.assertEqual(list(self.dest.iterdir()),[])
        paths=recover(result,PIN,self.dest)
        for role,path in paths.items():
            self.assertEqual(Path(path).read_bytes(),DATA[role])
        with self.assertRaises(FileExistsError):recover(result,PIN,self.dest)

    def test_bounds_and_missing_set(self):
        self.setup_assets()
        result=discover([self.src],PIN,max_entries=2)
        self.assertTrue(result["search_truncated"])
        self.assertFalse(result["all_exact_assets_located"])
        with self.assertRaises(ValueError):recover(result,PIN,self.dest)
        self.assertFalse(list(self.dest.iterdir()))

    def test_stale_candidate_rolls_back_owned_publications(self):
        self.setup_assets()
        result=discover([self.src],PIN)
        (self.src/"source.renamed").write_bytes(b"x"*len(DATA["source"]))
        with self.assertRaises(ValueError):recover(result,PIN,self.dest)
        self.assertFalse(list(self.dest.iterdir()))

    def test_never_overwrites_destination(self):
        source=self.src/"file";source.write_bytes(DATA["model"])
        dest=self.dest/"existing";dest.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            copy_exact(source,dest,len(DATA["model"]),sha(DATA["model"]))
        self.assertEqual(dest.read_bytes(),b"keep")
        self.assertEqual(list(self.dest.iterdir()),[dest])

    def test_symlink_directory_not_followed(self):
        outside=self.root/"outside";outside.mkdir()
        (outside/"model").write_bytes(DATA["model"])
        try: (self.src/"link").symlink_to(outside,target_is_directory=True)
        except OSError: self.skipTest("symlink unavailable")
        self.assertFalse(discover([self.src],PIN)["matches"]["model"])


if __name__=="__main__":unittest.main()
