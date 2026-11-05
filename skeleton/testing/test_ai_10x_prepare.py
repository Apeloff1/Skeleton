"""No-padding operator GGUF split/manifest and no-replace publication tests."""
from __future__ import annotations
from pathlib import Path
import tempfile,unittest,os,struct,json
from skeleton.ai.runtime.operational_ai.model.gguf.prepare import prepare_gguf
from skeleton.ai.runtime.operational_ai.model.gguf.manifest import load_manifest,GGUFManifestError
from skeleton.ai.runtime.operational_ai.model.gguf.assembly import assemble_model

class TestPrepare(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='.ai-gguf-prepare-',dir=Path.home())
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.source=self.root/'sample.gguf'
        self.body=b'GGUF'+struct.pack('<IQQ',3,1,1)+b'original fixture bytes; not trained\x00'
        self.source.write_bytes(self.body);self.source.chmod(0o400)
        self.out=self.root/'ready'
    def tearDown(self):
        self.source.chmod(0o600)
        self.tmp.cleanup()

    def build(self,**kwargs):
        return prepare_gguf(self.source,self.out,model_id='fixture',license='original',
                            source='operator:local',rights_approved=True,
                            shard_bytes=1_000_000,context_ceiling=2048,
                            memory_bytes=256_000_000,**kwargs)

    def test_no_padding_real_byte_manifest(self):
        receipt=self.build()
        manifest=load_manifest((self.out/'model.manifest.json').read_bytes())
        self.assertEqual(receipt.total_bytes,len(self.body))
        self.assertEqual(manifest.total_bytes,len(self.body))
        self.assertEqual(len(manifest.shards),1)
        self.assertEqual(json.loads((self.out/'approved_artifacts.json').read_text())['artifacts'][0]['wave'],'MBW-02')
        with assemble_model(self.out,manifest) as assembled:
            self.assertEqual(os.pread(assembled.fd,len(self.body),0),self.body)

    def test_existing_destination_never_overwritten(self):
        self.out.mkdir()
        keep=self.out/'important.txt';keep.write_text('untouched')
        with self.assertRaises(GGUFManifestError):self.build()
        self.assertEqual(keep.read_text(),'untouched')

    def test_rights_missing_no_publish(self):
        with self.assertRaises(GGUFManifestError):
            prepare_gguf(self.source,self.out,model_id='fixture',license='original',
                source='operator:local',rights_approved=False,shard_bytes=1_000_000,
                context_ceiling=2048,memory_bytes=256_000_000)
        self.assertFalse(self.out.exists())

    def test_bad_magic_no_publish(self):
        self.source.chmod(0o600);self.source.write_bytes(b'BAD!'+self.body[4:]);self.source.chmod(0o400)
        with self.assertRaises(GGUFManifestError):self.build()
        self.assertFalse(self.out.exists())

if __name__=='__main__':unittest.main()
