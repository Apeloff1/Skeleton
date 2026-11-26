import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zlib
from contextlib import contextmanager
import emerald_browser_deposit as d


def item(name, payload):
    c=zlib.compress(payload)
    return {"name":name,"bytes":len(c),"raw_bytes":len(payload),"sha256":d.sha(c)},c


class DepositTests(unittest.TestCase):
    def test_pinned_manifest(self):
        m=d.load_manifest(d.MANIFEST.read_bytes())
        self.assertEqual(sum(len(a["shards"]) for a in m["assets"]),32)
        self.assertEqual(sum(s["bytes"] for a in m["assets"] for s in a["shards"]),539395530)
        self.assertEqual(sum(a["bytes"] for a in m["assets"]),706132984)
        p=json.loads((Path(__file__).resolve().parents[1]/"frontend/src/features/Jeeves/companion/emeraldAssetPin.json").read_text())
        self.assertEqual(d.PIN["model"][1:],(p["native"]["modelBytes"],p["native"]["modelSha256"]))
        self.assertEqual(d.PIN["source"][1:],(p["native"]["sourceBytes"],p["native"]["sourceSha256"]))
        self.assertEqual(d.PIN["web"][1:],(p["web"]["bytes"],p["web"]["sha256"]))

    def test_compressed_hash_truncation_expansion_and_trailer(self):
        s,data=item("one.bin",b"abcdef")
        self.assertEqual(d.inflate(io.BytesIO(data),s),b"abcdef")
        for blob in (data[:-1],data+b"x",b"x"*len(data)):
            with self.assertRaises(ValueError):d.inflate(io.BytesIO(blob),s)
        with self.assertRaises(ValueError):d.inflate(io.BytesIO(data),{**s,"raw_bytes":3})
        trailer=data+zlib.compress(b"more")
        with self.assertRaises(ValueError):d.inflate(io.BytesIO(trailer),{**s,"bytes":len(trailer),"sha256":d.sha(trailer)})

    def test_atomic_set_and_no_overwrite(self):
        a,c=item("model.bin",b"model")
        b,e=item("web.bin",b"web")
        manifest={"assets":[{"name":"model.glb","bytes":5,"sha256":d.sha(b"model"),"shards":[a]},
                            {"name":"web.zip","bytes":3,"sha256":d.sha(b"web"),"shards":[b]}]}
        @contextmanager
        def opener(s):
            yield io.BytesIO(c if s is a else e)
        @contextmanager
        def bad(s):
            yield io.BytesIO(c if s is a else b"bad")
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(ValueError):d.reconstruct(manifest,bad,root)
            self.assertEqual(list(root.iterdir()),[])
            d.reconstruct(manifest,opener,root)
            self.assertEqual((root/"model.glb").read_bytes(),b"model")
            self.assertEqual((root/"web.zip").read_bytes(),b"web")
            with self.assertRaises(FileExistsError):d.reconstruct(manifest,opener,root)

    def test_commit_must_be_immutable(self):
        with self.assertRaises(ValueError):
            with d.remote_file("main",{"name":"model-001.bin"}):pass


if __name__=="__main__":unittest.main()
