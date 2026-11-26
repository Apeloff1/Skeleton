import hashlib, io, unittest
import publish_emerald_weighted_forms as p
class CustodyTests(unittest.TestCase):
    def test_pins(self):
        m,_=p.load()
        self.assertEqual(sum(f["bytes"] for f in m["forms"]),562092744)
        self.assertEqual(sum(len(f["chunks"]) for f in m["forms"]),20)
    def test_chunk_and_whole(self):
        x=b"abc"; y=b"def"
        f={"sha256":hashlib.sha256(x+y).hexdigest(),"chunks":[{"bytes":3,"sha256":p.digest(x),"path":"x"},{"bytes":3,"sha256":p.digest(y),"path":"y"}]}
        self.assertEqual(len(list(p.chunks(io.BytesIO(x+y),f))),2)
        for bad in [b"abxdef",x+y+b"x",x]:
            with self.assertRaises(ValueError):list(p.chunks(io.BytesIO(bad),f))
        with self.assertRaises(ValueError):list(p.chunks(io.BytesIO(x+y),{**f,"sha256":"0"*64}))
if __name__=="__main__":unittest.main()
