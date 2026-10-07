from dataclasses import dataclass


@dataclass(frozen=True)
class KVCacheKey:
    tenant: str
    session: str
    model: str
    config: str
    prefix_digest: str
    privacy_scope: str = "private"

    @property
    def complete(self) -> bool:
        return all(
            (
                self.tenant,
                self.session,
                self.model,
                self.config,
                self.prefix_digest,
                self.privacy_scope,
            )
        )

    @property
    def namespace(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.tenant,
            self.session,
            self.model,
            self.config,
            self.prefix_digest,
            self.privacy_scope,
        )


@dataclass(frozen=True)
class KVCacheEntry:
    key: KVCacheKey
    allocation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, KVCacheKey) or not self.allocation_id:
            raise ValueError("valid KV cache entry required")


@dataclass(frozen=True)
class KVCacheLease:
    entry: KVCacheEntry
    holder: str
    issued_at: int
    expires_at: int

    def __post_init__(self) -> None:
        if not isinstance(self.entry, KVCacheEntry) or not self.holder:
            raise ValueError("valid KV cache lease required")
        for value in (self.issued_at, self.expires_at):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("integer KV cache lease time required")


def reuse(
    entry: KVCacheEntry,
    key: KVCacheKey,
    now: int,
    lease: KVCacheLease,
    holder: str | None = None,
) -> KVCacheEntry:
    if not isinstance(entry, KVCacheEntry) or not isinstance(key, KVCacheKey):
        raise ValueError("KV cache entry and key required")
    if isinstance(now, bool) or not isinstance(now, int):
        raise ValueError("integer cache time required")
    if not key.complete or not entry.key.complete:
        raise ValueError("complete KV cache identity required")
    if entry.key != key:
        raise PermissionError("incompatible KV cache boundary")
    if lease.entry != entry:
        raise PermissionError("lease does not bind requested KV cache entry")
    if not lease.holder or (holder is not None and holder != lease.holder):
        raise PermissionError("invalid KV cache lease holder")
    if lease.expires_at <= lease.issued_at:
        raise PermissionError("invalid KV cache lease interval")
    if now < lease.issued_at or now >= lease.expires_at:
        raise PermissionError("invalid KV cache lease time")
    return entry
