"""Filesystem and manifest custody must serialize competing local processes."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from core import compressed_vault as storage


class SlowCodec:
    def __init__(self):
        self.guard = threading.Lock()
        self.active = 0
        self.peak = 0

    @contextmanager
    def stream_writer(self, handle):
        with self.guard:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.04)
            yield handle
        finally:
            with self.guard:
                self.active -= 1

    @contextmanager
    def stream_reader(self, handle):
        yield handle


def test_same_process_writes_are_serialized(monkeypatch, tmp_path: Path):
    codec = SlowCodec()
    for name, value in [
        ("VAULT_ROOT", tmp_path / "vault"),
        ("SCRATCH_ROOT", tmp_path / "scratch"),
        ("_MANIFEST_FILE", tmp_path / "vault" / "_manifest.json"),
        ("_STORAGE_READY", False),
        ("_STORAGE_IDENTITY", {}),
        ("_MANIFEST", {}),
        ("_CACHE", {}),
        ("_CACHE_SIZE_EST", {}),
        ("_COMPRESSOR", codec),
        ("_DECOMPRESSOR", codec),
    ]:
        monkeypatch.setattr(storage, name, value)
    errors: list[BaseException] = []

    def work(number: int):
        try:
            storage.write_shard("same", [{"worker": number}], domain="testing")
        except BaseException as exc:
            errors.append(exc)

    workers = [threading.Thread(target=work, args=(number,)) for number in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(6)
    assert all(not worker.is_alive() for worker in workers)
    assert not errors, errors
    assert codec.peak == 1
    assert len(storage.list_shards()) == 1


def test_cross_process_mutation_lock_preserves_manifest_and_data(tmp_path: Path):
    backend = Path(__file__).resolve().parents[1]
    vault = tmp_path / "vault"
    ready = tmp_path / "ready"
    ready.mkdir()
    events = tmp_path / "events.log"
    child_code = r'''
import os
from pathlib import Path
import time
from contextlib import contextmanager
from core import compressed_vault as vault

class SlowCodec:
    @contextmanager
    def stream_writer(self, handle):
        def write_event(phase):
            with open(os.environ["EVENTS"], "a", encoding="utf-8") as output:
                output.write(phase + "-" + os.environ["WORKER"] + "\n")
                output.flush()
        write_event("enter")
        try:
            time.sleep(0.08)
            yield handle
        finally:
            write_event("exit")

vault._COMPRESSOR = SlowCodec()
ready = Path(os.environ["READY_DIR"])
(ready / ("ready-" + os.environ["WORKER"])).write_text("1")
deadline = time.monotonic() + 5
while len(list(ready.glob("ready-*"))) < 2:
    if time.monotonic() > deadline:
        raise TimeoutError("second writer did not start")
    time.sleep(0.005)
vault.write_shard("same", [{"worker": os.environ["WORKER"]}], domain="testing")
'''
    processes = []
    for worker_id in ("A", "B"):
        env = os.environ.copy()
        env.update({
            "WORKER": worker_id,
            "EVENTS": str(events),
            "READY_DIR": str(ready),
            "HYPERSCALE_VAULT_DIR": str(vault),
            "HYPERSCALE_SCRATCH_DIR": str(tmp_path / "scratch"),
        })
        processes.append(subprocess.Popen(
            [sys.executable, "-c", child_code], cwd=backend, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ))
    for process in processes:
        try:
            _stdout, stderr = process.communicate(timeout=20)
        finally:
            if process.poll() is None:
                process.kill()
        assert process.returncode == 0, stderr

    order = events.read_text().splitlines()
    assert len(order) == 4, order
    assert order[0].startswith("enter-")
    assert order[1] == order[0].replace("enter-", "exit-", 1)
    assert order[2].startswith("enter-")
    assert order[3] == order[2].replace("enter-", "exit-", 1)
    manifest = json.loads((vault / "_manifest.json").read_text())
    raw = (vault / "same.jsonl.zst").read_bytes()
    assert manifest["same"]["sha1"] == hashlib.sha1(raw).hexdigest()



def test_long_lived_reader_observes_other_process_commit(monkeypatch, tmp_path: Path):
    """A process initialized before another process writes must refresh on read."""
    vault = tmp_path / "vault"
    scratch = tmp_path / "scratch"
    for name, value in [
        ("VAULT_ROOT", vault),
        ("SCRATCH_ROOT", scratch),
        ("_MANIFEST_FILE", vault / "_manifest.json"),
        ("_STORAGE_READY", False),
        ("_STORAGE_IDENTITY", {}),
        ("_MANIFEST", {}),
        ("_CACHE", {}),
        ("_CACHE_SIZE_EST", {}),
        ("_COMPRESSOR", SlowCodec()),
        ("_DECOMPRESSOR", SlowCodec()),
    ]:
        monkeypatch.setattr(storage, name, value)
    assert storage.list_shards() == []
    child_code = r'''
from contextlib import contextmanager
from core import compressed_vault as storage
class Codec:
    @contextmanager
    def stream_writer(self, handle):
        yield handle
storage._COMPRESSOR = Codec()
storage.write_shard("external", [{"worker": "second"}], domain="testing")
'''
    env = os.environ.copy()
    env["HYPERSCALE_VAULT_DIR"] = str(vault)
    env["HYPERSCALE_SCRATCH_DIR"] = str(scratch)
    result = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=Path(__file__).resolve().parents[1], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert [entry["name"] for entry in storage.list_shards()] == ["external"]
    assert storage.get_shard_entry("external")["rows"] == 1
    assert storage.vault_stats()["shard_count"] == 1
    assert storage.read_shard("external") == [{"worker": "second"}]
