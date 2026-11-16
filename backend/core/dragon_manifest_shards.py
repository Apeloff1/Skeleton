"""Route complete owner manifest ledgers without splitting deduplication."""
from __future__ import annotations

from threading import RLock

from core.dragon_hoarder_bulk import StorageHeld
from core.dragon_hoarder_manifests import ManifestArchive
from core.dragon_owner_shards import owner_path,shard_paths,ShardHeld


class ShardedManifestArchive:
    """Every owner operation uses exactly one physical ledger.

    The original root is still exposed for legacy qualification receipts.
    Existing manifest/chunk/history/tombstone owner rows pin the root.
    New owners use independent SQLite files but share the physical payload
    volume pool. Never partition by manifest ID: cleanup would lose the
    global owner-reference proof for deduplicated chunks.
    """
    def __init__(self,path,bulk):
        root=ManifestArchive(path,bulk)
        self.path=root.path
        self.bulk=bulk
        self._archives={self.path:root}
        self._lock=RLock()

    def ledger_paths(self):
        try:return shard_paths(self.path,"manifest")
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

    def begin(self,scope,**kwargs):
        return self._owner(scope).begin(scope,**kwargs)

    def append(self,scope,identifier,ordinal,data):
        return self._owner(scope).append(scope,identifier,ordinal,data)

    def seal(self,scope,identifier):
        return self._owner(scope).seal(scope,identifier)

    def read_chunk(self,scope,identifier,ordinal):
        return self._owner(scope).read_chunk(scope,identifier,ordinal)

    def abort(self,scope,identifier):
        return self._owner(scope).abort(scope,identifier)

    def collect(self,scope,*,limit=32):
        return self._owner(scope).collect(scope,limit=limit)

    def history(self,scope,logical_key,*,limit=32,before=None):
        return self._owner(scope).history(scope,logical_key,limit=limit,before=before)

    def usage(self,scope):
        return self._owner(scope).usage(scope)

    def abort_intent(self,scope,**kwargs):
        return self._owner(scope).abort_intent(scope,**kwargs)

    def collect_manifest(self,scope,identifier,*,limit=32):
        return self._owner(scope).collect_manifest(scope,identifier,limit=limit)
