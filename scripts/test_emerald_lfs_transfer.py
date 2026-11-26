import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import emerald_lfs_transfer as mod

def row(name, data):
    return name,len(data),hashlib.sha256(data).hexdigest()


class TransferTests(unittest.TestCase):
    def test_matches_repository_independent_pin(self):
        pin=json.loads((Path(__file__).resolve().parents[1]/'frontend/src/features/Jeeves/companion/emeraldAssetPin.json').read_text())
        self.assertEqual(mod.ASSETS[0][1:],(pin['native']['modelBytes'],pin['native']['modelSha256']))
        self.assertEqual(mod.ASSETS[1][1:],(pin['native']['sourceBytes'],pin['native']['sourceSha256']))
        self.assertEqual(mod.ASSETS[2][1:],(pin['web']['bytes'],pin['web']['sha256']))
        self.assertEqual(sum(x[1] for x in mod.PARTS),mod.ASSETS[0][1])

    def test_short_long_and_corrupt_are_rejected(self):
        name,n,sha=row('model',b'hello')
        for data in (b'hell',b'hello!',b'HELLO'):
            with self.subTest(data=data),self.assertRaises(ValueError):
                mod.consume(io.BytesIO(data),n,sha)

    def test_parts_stream_into_single_object_and_reject_wrong_full_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            whole=row('model.glb',b'abcxyz')
            parts=(row('a',b'abc'),row('b',b'xyz'))
            (root/'a').write_bytes(b'abc');(root/'b').write_bytes(b'xyz')
            with patch.object(mod,'ASSETS',(whole,)),patch.object(mod,'PARTS',parts):
                result=io.BytesIO()
                mod.verify_local(root,whole,result)
                self.assertEqual(result.getvalue(),b'abcxyz')
                (root/'model.glb').write_bytes(b'older!')
                with self.assertRaises(ValueError):mod.verify_local(root,whole)
                (root/'model.glb').unlink()
                (root/'b').write_bytes(b'xxx')
                with self.assertRaises(ValueError):mod.verify_local(root,whole)

    def test_upload_transfers_only_exact_oids_and_requires_independent_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            assets=(row('a',b'alpha'),row('b',b'beta'))
            for (name,_,_),payload in zip(assets,(b'alpha',b'beta')):(root/name).write_bytes(payload)
            calls=[];remote=[]
            def fake_git(checkout,*args):
                calls.append(args)
                if args[:3]==('lfs','push','--object-id'):
                    self.assertEqual(args[3:4],('origin',))
                    self.assertEqual(args[4:],tuple(r[2] for r in assets))
                    for r,b in zip(assets,(b'alpha',b'beta')):
                        sha=r[2]
                        self.assertEqual((checkout/'storage'/'objects'/sha[:2]/sha[2:4]/sha).read_bytes(),b)
            with patch.object(mod,'ASSETS',assets),patch.object(mod,'git_run',fake_git),patch.object(mod,'verify_remote',side_effect=lambda r:remote.append(r)):
                mod.upload(root)
                self.assertEqual(remote,list(assets))
                self.assertFalse(any(c[0]=='push' for c in calls))
            with patch.object(mod,'ASSETS',assets),patch.object(mod,'git_run',fake_git),patch.object(mod,'verify_remote',side_effect=ValueError('missing remote')):
                with self.assertRaisesRegex(ValueError,'missing remote'):mod.upload(root)

    def test_download_does_not_publish_partial_set_or_overwrite(self):
        assets=(row('a',b'alpha'),row('b',b'beta'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def fail_second(r,out):
                if r[0]=='b':raise ValueError('bad remote')
                out.write(b'alpha')
            with patch.object(mod,'ASSETS',assets),patch.object(mod,'verify_remote',fail_second):
                with self.assertRaises(ValueError):mod.publish_download(root)
                self.assertEqual(list(root.iterdir()),[])
            def download(r,out):
                payload={'a':b'alpha','b':b'beta'}[r[0]]
                mod.consume(io.BytesIO(payload),r[1],r[2],out)
            with patch.object(mod,'ASSETS',assets),patch.object(mod,'verify_remote',download):
                mod.publish_download(root)
                self.assertEqual((root/'b').read_bytes(),b'beta')
                with self.assertRaises(FileExistsError):mod.publish_download(root)

    def test_non_https_redirect_is_denied(self):
        with self.assertRaises(ValueError):mod.HttpsOnlyRedirect().redirect_request(None,None,302,'',{},'http://example.invalid')


if __name__=='__main__':unittest.main()
