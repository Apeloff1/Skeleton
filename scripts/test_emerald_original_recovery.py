import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from join_emerald_original import join, PARTS
from dragon_atelier_admit import PIN, bind_families, verify_peak_receipt

def sha(data): return hashlib.sha256(data).hexdigest()


class OriginalRecoveryTests(unittest.TestCase):
    def test_original_catalogue_and_receipts_match_independent_pin(self):
        root = PARTS.parent
        receipt = json.loads((root/"emeraldOriginalAdmission.json").read_text())
        pin = json.loads(PIN.read_text())
        recovery = json.loads((root/"emeraldOriginalRecovery.json").read_text())
        self.assertEqual(verify_peak_receipt(receipt, pin["native"]), receipt)
        self.assertEqual(bind_families(receipt, receipt["families"]), receipt)
        self.assertEqual({k:len(v) for k,v in receipt["families"].items()},
                         {"ground":320,"takeoff":20,"flight":20,"landing":20})
        self.assertEqual(recovery["assets"]["source"]["sha256"],pin["native"]["sourceSha256"])
        self.assertEqual(recovery["assets"]["web"]["sha256"],pin["web"]["sha256"])
        self.assertFalse(recovery["repository_binary_uploaded"])
        self.assertFalse(recovery["physical_rtx_verified"])

    def test_join_checks_every_part_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); data=[b"first",b"second"]
            rows=[]
            for i, part in enumerate(data,1):
                name=f"emerald_continuum.glb.part{i:02d}"
                (root/name).write_bytes(part)
                rows.append({"name":name,"size":len(part),"sha256":sha(part)})
            pin={"modelBytes":len(b"".join(data)),"modelSha256":sha(b"".join(data))}
            manifest={"model_sha256":pin["modelSha256"],"parts":rows}
            out=root/"emerald_continuum.glb"
            join(root,out,manifest,pin)
            self.assertEqual(out.read_bytes(),b"firstsecond")
            with self.assertRaises(FileExistsError):join(root,out,manifest,pin)
            out.unlink()
            (root/rows[1]["name"]).write_bytes(b"xxxxxx")
            with self.assertRaises(ValueError):join(root,out,manifest,pin)
            self.assertFalse(out.exists())


if __name__=="__main__": unittest.main()
