"""Route complete owner manifest ledgers without splitting deduplication."""
from __future__ import annotations

from threading import RLock

from core.dragon_hoarder_bulk import StorageHeld
from core.dragon_hoarder_manifests import ManifestArchive
from core.dragon_owner_shards import owner_path,shard_paths,ShardHeld
from core.dragon_manifest_write_lanes import OwnerWriteLanes


class ShardedManifestArchive:
    """Every owner operation uses exactly one physical ledger.

    The original root is still exposed for legacy qualification receipts.
    Existing manifest/chunk/history/tombstone owner rows pin the root.
    New owners use independent SQLite files and share the physical payload
    volume pool. Opted-in intra-owner write partitions use separate payload
    namespaces so no reference proof crosses independently writable ledgers.
    """
    def __init__(self,path,bulk):
        root=ManifestArchive(path,bulk)
        self.path=root.path
        self.bulk=bulk
        self._archives={self.path:root}
        self._lock=RLock()

    def ledger_paths(self):
        try:
            from core.dragon_ecosystem_custody import manifest_paths
            return tuple(manifest_paths(self.path))
        except (ShardHeld,OSError) as exc:raise StorageHeld("manifest topology held") from exc

    def _owner(self,scope):
        try:path=owner_path(self.path,"manifest",scope)
        except (ShardHeld,OSError) as exc:raise StorageHeld("manifest shard held") from exc
        with self._lock:
            archive=self._archives.get(path)
            if archive is None:
                archive=ManifestArchive(path,self.bulk)
                self._archives[path]=archive
            return archive

    def _lanes(self,scope):
        return OwnerWriteLanes(self._owner(scope),scope)

    def begin(self,scope,**kwargs):
        return self._lanes(scope).begin(**kwargs)

    def append(self,scope,identifier,ordinal,data):
        return self._lanes(scope).for_id(identifier).append(scope,identifier,ordinal,data)

    def seal(self,scope,identifier):
        return self._lanes(scope).for_id(identifier).seal(scope,identifier)

    def read_chunk(self,scope,identifier,ordinal):
        return self._lanes(scope).for_id(identifier).read_chunk(scope,identifier,ordinal)

    def migrate_content_defined(self,scope,identifier,raw,*,collect_limit=128):
        return self._lanes(scope).for_id(identifier).migrate_content_defined(scope,identifier,raw,collect_limit=collect_limit)

    def abort(self,scope,identifier):
        return self._lanes(scope).for_id(identifier).abort(scope,identifier)

    def collect(self,scope,*,limit=32):
        return self._lanes(scope).collect(limit=limit)

    def history(self,scope,logical_key,*,limit=32,before=None):
        return self._lanes(scope).history(logical_key,limit=limit,before=before)

    def usage(self,scope):
        return self._lanes(scope).usage()

    def abort_intent(self,scope,**kwargs):
        return self._lanes(scope).abort_intent(**kwargs)

    def collect_manifest(self,scope,identifier,*,limit=32):
        return self._lanes(scope).for_id(identifier).collect_manifest(scope,identifier,limit=limit)
