import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_emerald_delivery as delivery
from emerald_asset_preflight import ASSETS


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.input = self.root / "in"
        self.input.mkdir()
        self.target = self.root / "out"
        self.pin = {"assetSet": "fixture", "web": {}, "native": {}}
        for role, name, section, length, digest in ASSETS:
            data = role.encode()
            (self.input / name).write_bytes(data)
            self.pin[section].update({length: len(data), digest: hashlib.sha256(data).hexdigest()})
        self.model = self.input / delivery.MODEL

    def qualification(self, root, pin):
        states = {}
        for role, name, section, length, digest in ASSETS:
            data = (root / name).read_bytes()
            states[role] = len(data) == pin[section][length] and hashlib.sha256(data).hexdigest() == pin[section][digest]
        return {"all_exact_bytes_available": all(states.values()),
                "web_archive_qualified": states["web"], "native_source_archive_qualified": states["source"],
                "standalone_model_bytes_verified": states["model"]}

    def run_publish(self):
        with patch.object(delivery, "qualify", side_effect=self.qualification):
            return delivery.publish(self.input, None, self.target, self.pin, model=self.model)

    def test_publish_and_reverify(self):
        receipt = self.run_publish()
        with patch.object(delivery, "qualify", side_effect=self.qualification):
            self.assertEqual(delivery.verify(self.target, self.pin), receipt)
        self.assertFalse(receipt["release_qualified"])

    def test_model_corruption_rolls_back(self):
        self.model.write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            self.run_publish()
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob(".emerald-delivery-*")))

    def test_wrong_archive_rolls_back(self):
        (self.input / ASSETS[0][1]).write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            self.run_publish()
        self.assertFalse(self.target.exists())

    def test_no_overwrite(self):
        self.target.mkdir()
        old = self.target / "old"
        old.write_text("retain")
        with self.assertRaises(FileExistsError):
            self.run_publish()
        self.assertEqual(old.read_text(), "retain")

    def test_lock_collision(self):
        lock = self.root / ".out.emerald-delivery.lock"
        lock.mkdir()
        with self.assertRaises(FileExistsError):
            self.run_publish()
        self.assertTrue(lock.is_dir())

    def test_reject_tampered_receipt(self):
        self.run_publish()
        path = self.target / delivery.RECEIPT
        receipt = json.loads(path.read_text())
        receipt["physical_rtx_verified"] = True
        path.write_text(json.dumps(receipt))
        with patch.object(delivery, "qualify", side_effect=self.qualification), self.assertRaises(ValueError):
            delivery.verify(self.target, self.pin)

    def test_reject_extra_member(self):
        self.run_publish()
        (self.target / "extra").touch()
        with self.assertRaises(ValueError):
            delivery.verify(self.target, self.pin)

    def test_reject_corrupt_delivered_file(self):
        self.run_publish()
        (self.target / delivery.MODEL).write_bytes(b"corrupt")
        with patch.object(delivery, "qualify", side_effect=self.qualification), self.assertRaises(ValueError):
            delivery.verify(self.target, self.pin)


if __name__ == "__main__":
    unittest.main()
