import importlib.util
import json
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
    def test_claim_does_not_qualify(self):
        with tempfile.TemporaryDirectory() as d:
            run="1"*32;sha="a"*64
            p=Path(d)/("qualification_"+run+".json")
            p.write_text(json.dumps({"run_id":run,"source_sha256":sha,"physical_ray_dispatch_verified":True,"artist_approved":True,"engine_compiled":True,"editor_import_passed":True}))
            result=check.inspect(p,sha)
            self.assertFalse(result["physical_ray_dispatch_verified"]);self.assertFalse(result["artist_approved"]);self.assertFalse(result["release_qualified"])
            with self.assertRaises(ValueError):check.inspect(p,"b"*64)
if __name__=="__main__":unittest.main()
