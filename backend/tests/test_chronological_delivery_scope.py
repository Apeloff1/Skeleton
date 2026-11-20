"""Scope and delivery authorization regressions with an atomic store double."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading

import pytest
from cryptography.fernet import Fernet

from gameforge.workflow.delivery_scope import DeliveryScope, current_scope, use_scope
from gameforge.workflow.jeeves_vault import JeevesVault


class Collection:
    def __init__(self):
        self.rows = {}
        self.lock = threading.Lock()

    @staticmethod
    def matches(doc, query):
        for key, value in query.items():
            actual = doc.get(key)
            if isinstance(value, dict):
                if "$gt" in value and (actual is None or not actual > value["$gt"]):
                    return False
                if "$lt" in value and (actual is None or not actual < value["$lt"]):
                    return False
                if "$gte" in value and (actual is None or not actual >= value["$gte"]):
                    return False
            elif actual != value:
                return False
        return True

    def insert_one(self, doc):
        with self.lock:
            assert doc["_id"] not in self.rows
            self.rows[doc["_id"]] = dict(doc)

    def find_one(self, query, projection=None):
        with self.lock:
            return next((dict(doc) for doc in self.rows.values() if self.matches(doc, query)), None)

    def update_one(self, query, update):
        with self.lock:
            for doc in self.rows.values():
                if self.matches(doc, query):
                    for key, value in update.get("$inc", {}).items():
                        doc[key] += value
                    doc.update(update.get("$set", {}))
                    return type("Result", (), {"modified_count": 1, "matched_count": 1})()
        return type("Result", (), {"modified_count": 0, "matched_count": 0})()


@pytest.fixture
def vault(monkeypatch):
    box = JeevesVault()
    box._fernet = Fernet(Fernet.generate_key())
    coll = Collection()
    monkeypatch.setattr(box, "_col", lambda: coll)
    return box, coll


def test_scope_is_nested_and_restored():
    previous = current_scope()
    with use_scope(DeliveryScope("one", "alice")):
        assert current_scope().owner == "alice"
        with use_scope(DeliveryScope("two", "bob")):
            assert current_scope().tenant == "two"
        assert current_scope().owner == "alice"
    assert current_scope() == previous


def test_owner_or_bearer_required_and_new_bytes_are_separate(vault):
    box, coll = vault
    alice = DeliveryScope("team", "alice")
    bob = DeliveryScope("team", "bob")
    with use_scope(alice):
        package = box.register("demo", "game.zip", b"bytes")
    pid, token = package["package_id"], package["download_token"]
    doc = coll.rows[pid]
    assert "download_token" not in doc and token not in repr(doc)
    assert doc["enc_content"] != b"bytes" and "vault_file_id" not in doc
    assert not box.get_download(pid)["ok"]
    assert not box.get_download(pid, scope=bob)["ok"]
    assert not box.get_download(pid, "x"*43, scope=alice)["ok"]
    assert base64.b64decode(box.get_download(pid, scope=alice)["content_base64"]) == b"bytes"
    assert box.get_download(pid, token)["sha256"] == hashlib.sha256(b"bytes").hexdigest()
    assert token not in box.delivery_link(package)["download_link"]


def test_atomic_download_quota_under_parallel_redeems(vault):
    box, coll = vault
    with use_scope(DeliveryScope("team", "alice")):
        package = box.register("demo", "game.zip", b"bytes", max_downloads=3)
    pid, token = package["package_id"], package["download_token"]
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: box.get_download(pid, token), range(24)))
    assert sum(result["ok"] for result in results) == 3
    assert coll.rows[pid]["download_count"] == 3


def test_bad_bytes_and_token_rotation(vault):
    box, coll = vault
    owner = DeliveryScope("team", "alice")
    with use_scope(owner):
        package = box.register("demo", "game.zip", b"bytes")
        new = box.rotate_token(package["package_id"])
    pid, old = package["package_id"], package["download_token"]
    assert new and not box.get_download(pid, old)["ok"]
    doc = coll.rows[pid]
    doc["enc_content"] = box._cipher().encrypt(b"other")
    assert box.get_download(pid, new)["error"] == "package_integrity_failed"
    assert doc["download_count"] == 0


def test_unowned_historical_documents_are_not_assigned(vault):
    box, coll = vault
    legacy = "1"*32
    coll.rows[legacy] = {"_id": legacy, "package_id": legacy, "download_token": "x"*43}
    assert not box.get_download(legacy, "x"*43)["ok"]


def test_wrong_scope_rotation_does_not_invalidate_owner_token(vault):
    box, _ = vault
    with use_scope(DeliveryScope("tenant", "owner")):
        package = box.register("demo", "game.zip", b"bytes")
    with use_scope(DeliveryScope("other", "owner")):
        assert box.rotate_token(package["package_id"]) is None
    assert box.get_download(package["package_id"], package["download_token"])["ok"]
