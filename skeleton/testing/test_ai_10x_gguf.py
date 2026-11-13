"""Standalone GGUF identity, shard custody and fake-loader contract coverage.

A fake loader is used *only* here to verify the adapter contract. Passing this
suite is NOT evidence that llama.cpp or a trained model executed.
"""
from __future__ import annotations
import hashlib,os,struct,tempfile,unittest
from pathlib import Path
from skeleton.ai.runtime.operational_ai.model.gguf.manifest import (
    Shard,GGUFModelManifest,GGUFManifestError,load_manifest)
from skeleton.ai.runtime.operational_ai.model.gguf.assembly import assemble_model
from skeleton.ai.runtime.operational_ai.model.gguf.header import inspect_header
from skeleton.ai.runtime.operational_ai.model.gguf.runtime import GGUFBackend
from skeleton.ai.runtime.operational_ai.model.gguf.limits import reserve_context
from skeleton.ai.runtime.operational_ai.model.gguf.identity import deployment_identity
from skeleton.ai.runtime.operational_ai.model.gguf.memory import assess_memory
from skeleton.ai.runtime.operational_ai.model.gguf.selection import choose
from skeleton.ai.runtime.operational_ai.model.gguf.quantization import inspect_quantization


def blob()->bytes:
    return b'GGUF'+struct.pack('<IQQ',3,2,1)+b'original-unit-test-model-content\x00'


def model(shards:tuple[Shard,...],raw:bytes)->GGUFModelManifest:
    return GGUFModelManifest('fixture',shards,hashlib.sha256(raw).hexdigest(),len(raw),
        'test-only','generated:fixture',True,2048,0,256_000_000)

class FakeNativeLlama:
    def __init__(self,**kwargs):
        self.kwargs=kwargs
        assert kwargs['model_path'].startswith('/proc/self/fd/')
    def create_chat_completion(self,**kwargs):
        if kwargs.get('stream'):
            return iter([{'choices':[{'delta':{'content':'hello'},'finish_reason':None}]},
                         {'choices':[{'delta':{},'finish_reason':'stop'}]}])
        return {'choices':[{'message':{'content':'hello'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':7,'completion_tokens':1}}

class TestGGUF(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='.skeleton-gguf-',dir=Path.home())
        self.root=Path(self.tmp.name)
        self.root.chmod(0o700)
        self.raw=blob()
        pieces=[self.raw[:10],self.raw[10:25],self.raw[25:]]
        shards=[]
        for i,p in enumerate(pieces):
            name=f'part_{i}.gguf'
            (self.root/name).write_bytes(p)
            os.chmod(self.root/name,0o400)
            shards.append(Shard(name,len(p),hashlib.sha256(p).hexdigest()))
        self.manifest=model(tuple(shards),self.raw)

    def tearDown(self):
        for p in self.root.iterdir():p.chmod(0o600)
        self.tmp.cleanup()

    def test_header_and_multishard_sealed_image(self):
        with assemble_model(self.root,self.manifest) as assembly:
            self.assertEqual(assembly.sha256,self.manifest.model_sha256)
            self.assertEqual(assembly.bytes,len(self.raw))
            self.assertEqual(inspect_header(assembly.fd).version,3)
            self.assertEqual(os.pread(assembly.fd,len(self.raw),0),self.raw)
            with self.assertRaises(OSError):os.write(assembly.fd,b'overwrite')

    def test_runtime_interface_real_loader_contract(self):
        with assemble_model(self.root,self.manifest) as assembly:
            with GGUFBackend(self.manifest,assembly,n_ctx=256,loader=FakeNativeLlama) as backend:
                result=backend.generate([{'role':'user','content':'hello'}],max_output_tokens=4,seed=0,temperature=0.5)
                self.assertEqual(result.text,'hello')
                self.assertEqual(result.generated_tokens,1)
                self.assertEqual(result.model_digest,self.manifest.model_sha256)

    def test_hash_mismatch_blocks_assembly(self):
        p=self.root/self.manifest.shards[0].path
        p.chmod(0o600);p.write_bytes(b'X'*self.manifest.shards[0].bytes);p.chmod(0o400)
        with self.assertRaisesRegex(GGUFManifestError,'sha256'):
            assemble_model(self.root,self.manifest)

    def test_symlink_shard_blocks_assembly(self):
        p=self.root/self.manifest.shards[1].path
        p.unlink();p.symlink_to(self.root/self.manifest.shards[0].path)
        with self.assertRaises((OSError,GGUFManifestError)):
            assemble_model(self.root,self.manifest)

    def test_missing_rights_blocks_manifest(self):
        rec=self.manifest.to_record();rec['rights_approved']=False
        import json
        with self.assertRaisesRegex(GGUFManifestError,'rights'):
            load_manifest(json.dumps(rec).encode())

    def test_full_manifest_roundtrip(self):
        import json
        rec=self.manifest.to_record()
        self.assertEqual(load_manifest(json.dumps(rec).encode()),self.manifest)

    def test_duplicate_json_field_rejected(self):
        raw=b'{"schema_version":1,"schema_version":1}'
        with self.assertRaises(GGUFManifestError):load_manifest(raw)

    def test_model_chooser_and_memory_hold(self):
        self.assertEqual(choose((self.manifest,),context_minimum=1024),self.manifest)
        self.assertFalse(assess_memory(self.manifest,available_bytes=100).accepted)
        self.assertTrue(assess_memory(self.manifest,available_bytes=2_000_000_000).accepted)

    def test_invalid_token_budget(self):
        with self.assertRaises(GGUFManifestError):reserve_context(context=128,prompt_tokens=120,output_tokens=30)
        reservation=reserve_context(context=512,prompt_tokens=200,output_tokens=30)
        self.assertEqual(reservation.prompt_ceiling,450)

    def test_deployment_binding(self):
        identity=deployment_identity(self.manifest,n_ctx=512,n_threads=2,n_gpu_layers=0)
        self.assertEqual(identity.model_sha,self.manifest.model_sha256)
        self.assertEqual(len(identity.configuration_sha),64)

    def test_quant_policy(self):
        self.assertTrue(inspect_quantization('Q4_K_M').deployable)
        self.assertFalse(inspect_quantization('UNKNOWN_Q').deployable)

class TestGGUFAdversarialMatrix(unittest.TestCase):
    def test_malformed_shard_paths(self):
        for candidate in ('../escape','/root/key','a/../b','a\\b','a//b','a/./b','a\x00b',
                          'a\nb','a\tb','a\rb','a/../secret','.','..','',
                          'a\ud800','\\server','/etc/passwd'):
            with self.subTest(candidate=repr(candidate)),self.assertRaises(GGUFManifestError):
                Shard(candidate,100,'a'*64)

    def test_shard_bounds(self):
        for size in (-1,0,99_000_001,2**32,100_000_000,False,True,'2',None):
            with self.subTest(size=size),self.assertRaises(GGUFManifestError):
                Shard('ok',size,'a'*64)

    def test_digest_syntax(self):
        for value in ('a'*63,'a'*65,'A'*64,'z'*64,'\x00'*64,'','sha256:abc',None):
            with self.subTest(value=repr(value)),self.assertRaises(GGUFManifestError):
                Shard('file',10,value)

if __name__=='__main__':unittest.main()
