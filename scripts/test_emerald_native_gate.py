import importlib.util
import json
import hashlib
import struct
import zipfile
from pathlib import Path
import tempfile
import unittest

def load(name):
    s=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parent/(name+".py"))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
stage=load("stage_emerald_native")
check=load("inspect_emerald_native_receipt")
class NativeTests(unittest.TestCase):
    def test_members(self):
        self.assertEqual(stage.member("emerald-atelier-fold/Unreal/Tools/qualify.ps1").as_posix(),"Unreal/Tools/qualify.ps1")
        for name in ["../x","emerald-atelier-fold/../x","emerald-atelier-fold/C:/x","emerald-atelier-fold//x","emerald-atelier-fold/a\\b"]:
            with self.assertRaises(ValueError):stage.member(name)
    def test_windows_aliases_are_denied(self):
        for name in ("CON.txt", "aux", "file.", "COM1.json", "LPT9"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                stage.member("emerald-atelier-fold/Art/"+name)

    def make_bundle(self, root, extra=None):
        doc={"asset":{"version":"2.0"},"buffers":[{"byteLength":4}],"nodes":[{} for _ in range(108)],
             "skins":[{"joints":list(range(108))}],"animations":[{"name":f"clip_{i}","channels":[{}],"samplers":[{}]} for i in range(380)],
             "meshes":[{}],"scenes":[{}]}
        data=json.dumps(doc).encode();data+=b" "*((-len(data))%4)
        model=root/"emerald_continuum.glb"
        model.write_bytes(struct.pack("<4sIIII",b"glTF",2,32+len(data),len(data),0x4e4f534a)+data+
                          struct.pack("<II",4,0x004e4942)+bytes(4))
        sha=hashlib.sha256(model.read_bytes()).hexdigest()
        source=root/"source.zip"
        with zipfile.ZipFile(source,"w") as archive:
            archive.writestr(stage.PREFIX,b"")
            archive.writestr(stage.PREFIX+"Models/",b"")
            archive.writestr(stage.PREFIX+"Models/manifest.json",json.dumps({"sha256":sha}))
            for name in ("Unreal/EmeraldCrawler.uproject","Unreal/Tools/qualify.ps1","Unreal/Tools/build_unreal.ps1",
                         "Unreal/Tools/import_reference_volume.py","Art/basecolor.png","Art/normal.png","Art/orm.png"):
                archive.writestr(stage.PREFIX+name,b"source fixture")
            if extra:archive.writestr(stage.PREFIX+extra,b"unexpected")
        pin={"modelBytes":model.stat().st_size,"modelSha256":sha,"sourceBytes":source.stat().st_size,
             "sourceSha256":hashlib.sha256(source.read_bytes()).hexdigest()}
        return source,model,pin

    def test_native_stage_actual_snapshot_synthetic(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,model,pin=self.make_bundle(root)
            target=root/"native"
            stage.stage(source,model,target,pin)
            receipt=json.loads((target/"skeleton_stage_receipt.json").read_text())
            self.assertFalse(receipt["engine_compiled"])
            self.assertFalse(receipt["physical_rtx_verified"])
            self.assertEqual((target/"Models/emerald_continuum.glb").read_bytes(),model.read_bytes())
            self.assertFalse((target/".source-custody.zip").exists())
            self.assertEqual(len(receipt["files"]),9)
            with self.assertRaises(ValueError):stage.stage(source,model,target,pin)

    def test_native_stage_denies_mutation_and_case_collision(self):
        for extra in (None,"art/BaseColor.png"):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as d:
                root=Path(d);source,model,pin=self.make_bundle(root,extra)
                if not extra:source.write_bytes(b"x"*source.stat().st_size)
                target=root/"native"
                with self.assertRaises(ValueError):stage.stage(source,model,target,pin)
                self.assertFalse(target.exists())

    def test_claim_does_not_qualify(self):
        with tempfile.TemporaryDirectory() as d:
            run="1"*32;sha="a"*64
            p=Path(d)/("qualification_"+run+".json")
            p.write_text(json.dumps({"run_id":run,"source_sha256":sha,"physical_ray_dispatch_verified":True,"artist_approved":True,"engine_compiled":True,"editor_import_passed":True}))
            result=check.inspect(p,sha)
            self.assertFalse(result["physical_ray_dispatch_verified"]);self.assertFalse(result["artist_approved"]);self.assertFalse(result["release_qualified"])
            with self.assertRaises(ValueError):check.inspect(p,"b"*64)
if __name__=="__main__":unittest.main()
