"""Pin parity and no-heavy-import regression for actual original V7 custody."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emerald_v7_model_pins as pins
import publish_emerald_v7_orbit02 as transport

ROOT=Path(__file__).resolve().parents[1]

class OriginalModelPinBoundaryTests(unittest.TestCase):
    def test_authoritative_immutable_donor_and_v6_v7_model_hashes(self):
        self.assertEqual(pins.DONOR,
            "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a")
        self.assertEqual(set(pins.SOURCES),{"pathfinder","archivist"})
        self.assertEqual(set(pins.OUTPUTS),{"pathfinder","archivist"})
        self.assertEqual(pins.SOURCES["pathfinder"][0],114693124)
        self.assertEqual(pins.SOURCES["archivist"][0],114815776)
        self.assertEqual(pins.OUTPUTS["pathfinder"][0],114696520)
        self.assertEqual(pins.OUTPUTS["archivist"][0],114819168)
        self.assertEqual((pins.ROOT_JOINT,pins.ANGLE,pins.TARGET_CLIP),
                         (34,.18,"orbit-02"))

    def test_transport_manifest_bytes_match_numerical_export_pins(self):
        forms,_bytes=transport.load()
        self.assertEqual([x["stage"] for x in forms],["pathfinder","archivist"])
        for form in forms:
            stage=form["stage"]
            self.assertEqual((form["bytes"],form["sha256"]),pins.OUTPUTS[stage])
            self.assertEqual(form["source_v6_sha256"],pins.SOURCES[stage][1])

    def test_complete_four_zip_record_matches_export_model_hashes(self):
        evidence=json.loads((ROOT/"assets/emerald/evolution-v7/independent-original-zip-custody-20261117.json").read_bytes())
        self.assertEqual(evidence["schema"],
                         "skeleton.emerald.v7.original-binary-custody-independent.v1")
        for row in evidence["models"]:
            stage=row["stage"]
            self.assertEqual((row["v6"]["bytes"],row["v6"]["sha256"]),pins.SOURCES[stage])
            self.assertEqual((row["v7"]["bytes"],row["v7"]["sha256"]),pins.OUTPUTS[stage])

    def test_remote_transport_imports_with_site_packages_disabled(self):
        script=(
            "import sys;"
            "sys.path.insert(0,'scripts');"
            "import emerald_v7_model_pins,publish_emerald_v7_orbit02,"
            "verify_emerald_v7_remote_original;"
            "assert 'numpy' not in sys.modules;"
            "assert 'scipy' not in sys.modules;"
        )
        result=subprocess.run([sys.executable,"-S","-c",script],
                              cwd=ROOT,capture_output=True,text=True,timeout=12)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=="__main__":
    unittest.main()
