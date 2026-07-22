"""
routes/galaxy_studio_state.py — Shared state + lazy function proxies for
the Galaxy Studio sub-routers (Feb 2026 Phase-3 decomposition).

Why a separate module?
----------------------
The main ``routes/galaxy_studio.py`` mounts every sub-router via
``router.include_router(...)``. If a sub-router tried to ``from
routes.galaxy_studio import _builds, _load_build`` directly, Python's
import machinery would hit a circular import the moment the main module
re-imports the sub-router during its include.

This module breaks the cycle by:
  1. OWNING the in-memory state dicts (``_builds``, ``_active_runners``,
     ``TOTAL_BATCHES``) — galaxy_studio.py now imports them from here, so
     there's only ONE authoritative copy in process.
  2. LAZY-proxying the heavy helper functions (``load_build``,
     ``save_build``) — sub-routers import the proxy, but the actual
     import of ``routes.galaxy_studio`` is deferred until first call,
     which is always at REQUEST time (long after module-load).
"""
from __future__ import annotations
from typing import Any, Awaitable, Callable

# ───────────────────────────────────────────────────────────────────────
# Shared state — owned here, referenced by both galaxy_studio.py and the
# sub-routers. There is only ONE copy of each container per process.
# ───────────────────────────────────────────────────────────────────────

#: Number of batches in a Galaxy Studio cosmic build.
TOTAL_BATCHES: int = 10

#: In-memory build cache. Keyed by build_id → build dict. Persisted via
#: ``_save_build`` to Mongo; ``_load_build`` re-hydrates on cache miss.
_builds: dict[str, dict] = {}

#: Set of build_ids currently being driven by a background runner.
_active_runners: set[str] = set()


#: In-memory vault index. Keyed by vault_id → entry dict. Persisted in
#: ``galaxy_vault`` Mongo collection via ``_save_vault_entry``. The parent
#: module's ``_get_all_vault_entries()`` re-hydrates this dict on every
#: list/download call, so the SSOT is "Mongo + this cache".
_vault_entries: dict[str, dict] = {}


# ───────────────────────────────────────────────────────────────────────
# Lazy proxies — the actual implementations live in routes/galaxy_studio.py
# and stay there because they have ~20 internal dependencies that would
# be costly to also extract. The proxy lets sub-routers call them without
# importing galaxy_studio at module-load time.
# ───────────────────────────────────────────────────────────────────────

async def load_build(build_id: str) -> dict | None:
    """Forward to ``routes.galaxy_studio._load_build``."""
    from routes.galaxy_studio import _load_build  # lazy
    return await _load_build(build_id)


async def save_build(build: dict) -> Any:
    """Forward to ``routes.galaxy_studio._save_build``."""
    from routes.galaxy_studio import _save_build  # lazy
    return await _save_build(build)


async def advance_build(build_id: str) -> dict:
    """Forward to ``routes.galaxy_studio._advance_build``."""
    from routes.galaxy_studio import _advance_build  # lazy
    return await _advance_build(build_id)


def get_run_background_build() -> Callable[..., Awaitable[Any]]:
    """Return the bound ``_run_background_build`` coroutine (lazy)."""
    from routes.galaxy_studio import _run_background_build  # lazy
    return _run_background_build


async def get_all_vault_entries() -> dict:
    """Refresh the shared ``_vault_entries`` dict from Mongo's
    ``galaxy_vault`` collection. Phase-7 (Feb 2026): inlined here from the
    parent module after `routes.galaxy_studio._get_all_vault_entries` was
    removed during the LOC-reduction sweep."""
    try:
        from services.database import db as _db
        docs = await _db.galaxy_vault.find({}, {"_id": 0}).to_list(1000)
        for d in docs:
            _vault_entries[d["vault_id"]] = d
    except Exception as e:
        print(f"[GALAXY get_all_vault_entries] WARN: {e}")
    return _vault_entries


# ───────────────────────────────────────────────────────────────────────
# Phase-6 vault-write helpers (Feb 2026): proxies that let the vault
# sub-router create ZIPs without importing the entire parent module.
# Each one lazy-loads its target on first call, then the caller uses the
# returned reference at request time.
# ───────────────────────────────────────────────────────────────────────

def get_vault_dir() -> str:
    """Return the parent module's ``VAULT_DIR`` constant (lazy)."""
    from routes.galaxy_studio import VAULT_DIR  # lazy
    return VAULT_DIR


def get_zip_write_file() -> Callable[..., Any]:
    """Return the parent's ``_zip_write_file(zf, path, content)`` helper."""
    from routes.galaxy_studio import _zip_write_file  # lazy
    return _zip_write_file


def get_vault_save() -> Callable[..., dict]:
    """Return the parent's ``_vault_save(...)`` sync helper that creates
    the on-disk vault entry + dict-cache row."""
    from routes.galaxy_studio import _vault_save  # lazy
    return _vault_save


async def save_vault_entry(entry: dict) -> Any:
    """Persist a vault entry into Mongo's ``galaxy_vault`` collection.
    Phase-7 (Feb 2026): inlined here from the parent module after
    ``routes.galaxy_studio._save_vault_entry`` was removed during the
    LOC-reduction sweep."""
    try:
        from services.database import db as _db
        await _db.galaxy_vault.update_one(
            {"vault_id": entry["vault_id"]},
            {"$set": entry},
            upsert=True,
        )
    except Exception as e:
        print(f"[GALAXY save_vault_entry] WARN: {e}")


__all__ = [
    "TOTAL_BATCHES",
    "_builds",
    "_active_runners",
    "_vault_entries",
    "load_build",
    "save_build",
    "advance_build",
    "get_run_background_build",
    "get_all_vault_entries",
    "get_vault_dir",
    "get_zip_write_file",
    "get_vault_save",
    "save_vault_entry",
    # Phase-6 (Feb 2026) lazy proxies for pipeline / files / admin extractions
    "get_generate_batch_files",
    "get_total_file_count",
    "get_amplify",
    "get_package_build",
    "get_binary_prefix",
    "get_background_tasks",
    "get_worker_lock",
    "get_worker_stats",
    "get_worker_pool",
]


# ───────────────────────────────────────────────────────────────────────
# Phase-6 (Feb 2026) lazy proxies — pipeline / files / admin extractions.
# Each accessor lazy-loads the target attribute from the parent
# ``routes.galaxy_studio`` module on first use, then the caller uses the
# returned reference at request time.
# ───────────────────────────────────────────────────────────────────────

def get_generate_batch_files() -> Callable[..., dict]:
    """Return the parent's ``_generate_batch_files(build, batch, batch_size)`` helper."""
    from routes.galaxy_studio import _generate_batch_files  # lazy
    return _generate_batch_files


def get_total_file_count() -> Callable[[dict], int]:
    """Return the parent's ``_get_total_file_count(build)`` helper."""
    from routes.galaxy_studio import _get_total_file_count  # lazy
    return _get_total_file_count


def get_amplify() -> Callable[..., str]:
    """Return the parent's ``_amplify(content, fname, title, genre)`` helper."""
    from routes.galaxy_studio import _amplify  # lazy
    return _amplify


async def get_package_build(build_id: str) -> str:
    """Forward to ``routes.galaxy_studio._package_build`` — packages the
    build's files into a ZIP on disk and returns the path."""
    from routes.galaxy_studio import _package_build  # lazy
    return await _package_build(build_id)


def get_binary_prefix() -> str:
    """Return the parent's ``_BINARY_PREFIX`` constant."""
    from routes.galaxy_studio import _BINARY_PREFIX  # lazy
    return _BINARY_PREFIX


def get_background_tasks() -> dict:
    """Return the parent's ``_background_tasks`` dict (shared ref)."""
    from routes.galaxy_studio import _background_tasks  # lazy
    return _background_tasks


def get_worker_lock():
    """Return the parent's ``_worker_lock`` (threading.Lock)."""
    from routes.galaxy_studio import _worker_lock  # lazy
    return _worker_lock


def get_worker_stats() -> dict:
    """Return the parent's ``_worker_stats`` dict (shared ref)."""
    from routes.galaxy_studio import _worker_stats  # lazy
    return _worker_stats


def get_worker_pool():
    """Return the parent's ``_WORKER_POOL`` ThreadPoolExecutor."""
    from routes.galaxy_studio import _WORKER_POOL  # lazy
    return _WORKER_POOL
