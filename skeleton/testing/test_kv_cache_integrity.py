from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from skeleton.kv_cache import CacheTier, KVCacheConfig, KVCacheManager, KVNamespace, KVPageInput


def _ns(domain: str = "tenant") -> KVNamespace:
    return KVNamespace(model_id="test/model", trust_domain=domain, cache_salt=domain)


def test_integrity_audit_stays_clean_across_eviction_and_invalidation():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4, max_bytes=192, max_entries=3))
    left = _ns("left")
    right = _ns("right")
    cache.commit_prefix(range(8), [KVPageInput("l0", 64), KVPageInput("l1", 64)], left)
    cache.commit_prefix(range(100, 108), [KVPageInput("r0", 64), KVPageInput("r1", 64)], right)

    assert cache.audit().valid
    cache.invalidate_namespace(left)
    report = cache.audit()
    assert report.valid
    assert report.resident_pages == cache.stats().resident_pages
    assert report.resident_bytes == cache.stats().resident_bytes


class RecordingStorage:
    def __init__(self, *, fail_release: bool = False) -> None:
        self.fail_release = fail_release
        self.released: list[tuple[object, CacheTier]] = []

    def move(self, handle, source, target):
        return handle

    def release(self, handle, tier):
        self.released.append((handle, tier))
        if self.fail_release:
            raise RuntimeError("backend cleanup failed")


def test_dedup_arbitration_releases_redundant_backend_page():
    storage = RecordingStorage()
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4), storage=storage)
    ns = _ns()
    cache.commit_prefix(range(4), [KVPageInput("canonical", 64)], ns)
    cache.commit_prefix(range(4), [KVPageInput("redundant", 64)], ns)

    assert storage.released == [("redundant", CacheTier.GPU)]
    assert cache.lookup(range(4), ns).handles == ("canonical",)
    assert cache.audit().valid


def test_backend_release_failure_is_contained_and_reported():
    storage = RecordingStorage(fail_release=True)
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4, max_bytes=64), storage=storage)
    ns = _ns()
    cache.commit_prefix(range(4), [KVPageInput("first", 64)], ns)
    cache.commit_prefix(range(100, 104), [KVPageInput("second", 64)], ns)

    stats = cache.stats()
    assert stats.storage_errors == 1
    assert stats.resident_bytes <= 64
    assert cache.audit().valid


def test_parallel_lookup_and_commit_preserve_graph_invariants():
    cache = KVCacheManager(KVCacheConfig(block_size_tokens=4, max_bytes=16_384, max_entries=256))
    ns = _ns()

    def worker(index: int) -> None:
        start = index * 100
        tokens = tuple(range(start, start + 8))
        cache.commit_prefix(
            tokens,
            [KVPageInput(f"{index}:0", 32), KVPageInput(f"{index}:1", 32)],
            ns,
        )
        assert cache.lookup(tokens, ns).full_hit

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(32)))

    report = cache.audit()
    assert report.valid
    assert report.resident_pages == 64
