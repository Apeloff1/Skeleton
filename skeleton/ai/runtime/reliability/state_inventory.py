"""Fail-closed inventory of Skeleton durable-state stores.

Issue #969 Seed 25 (``reserve-S171-durable-state-inventory``) classifies the
existing vault, swarm-durable, quality-state, provenance-ledger, and sqlite-
collection surfaces. This module inventories formats, owners, persistence
locations, and corruption/recovery semantics. It does not rewrite those stores,
does not implement replication (#1027), and does not own swarm recovery or
physics.

Unknown stores, unknown families, and incomplete classification fail closed.
"""
from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TASK_ID = "reserve-S171-durable-state-inventory"
CONFLICT_DOMAIN = "reliability.readonly.state_inventory"
INVENTORY_VERSION = 1

FAMILIES = (
    "vault",
    "swarm_durable",
    "quality_state",
    "provenance_ledger",
    "sqlite_collection",
)
FAMILY_SET = frozenset(FAMILIES)
STATUSES = ("classified", "unknown")
STATUS_SET = frozenset(STATUSES)
CORRUPTION_POLICIES = (
    "fail_closed",
    "skip_corrupt",
    "verify_bool",
    "none",
)
CORRUPTION_POLICY_SET = frozenset(CORRUPTION_POLICIES)
RECOVERY_POLICIES = (
    "refuse",
    "skip",
    "restore_verified",
    "snapshot_ram",
    "none",
)
RECOVERY_POLICY_SET = frozenset(RECOVERY_POLICIES)

SKIP_PARTS = frozenset(
    {
        "testing",
        "tests",
        "test",
        "__pycache__",
        ".venv",
        "venv",
        "satellites",
        "branch-snapshots",
    }
)


class UnknownDurableStoreError(RuntimeError):
    """Raised when a store is missing from the inventory or still unclassified."""


@dataclass(frozen=True, slots=True)
class DurableStore:
    """One classified (or explicitly unknown) durable-state surface."""

    store_id: str
    family: str
    status: str
    format: str
    owner: str
    owner_path: str
    persistence: str
    restart_durable: bool
    corruption: str
    recovery: str
    corruption_policy: str
    recovery_policy: str
    discovery_name: str
    evidence: tuple[str, ...]
    notes: str = ""


# Explicit table. Discovery of an unlisted production store in a scanned family
# fails closed as unknown. Classification only — do not mutate the stores.
STORES: tuple[DurableStore, ...] = (
    DurableStore(
        store_id="vault.worm_audit",
        family="vault",
        status="classified",
        format="jsonl-hash-chain",
        owner="skeleton.vault.audit",
        owner_path="skeleton/vault/audit.py",
        persistence="data/vault/worm_audit.jsonl (SKELETON_WORM_AUDIT_PATH)",
        restart_durable=True,
        corruption="AuditChainBroken on broken, unreadable, or unrestored chain",
        recovery="restore-on-open then verify_chain_or_refuse; refuse boot, no silent repair",
        corruption_policy="fail_closed",
        recovery_policy="refuse",
        discovery_name="AuditLog",
        evidence=(
            "skeleton/vault/audit.py",
            "tests/test_vault.py",
            "tests/test_vault_audit_quality.py",
        ),
        notes="Canonical vault WORM ledger. Sibling of Gate WormAuditLog.",
    ),
    DurableStore(
        store_id="vault.sealed_store",
        family="vault",
        status="classified",
        format="in-memory envelope-encrypted slots",
        owner="skeleton.vault.store",
        owner_path="skeleton/vault/store.py",
        persistence="process memory (ciphertext + sha256 digest per slot)",
        restart_durable=False,
        corruption="IntegrityError when unwrap digest does not match stored hash",
        recovery="RecoveryManager snapshot/restore of plaintext slots in RAM only",
        corruption_policy="fail_closed",
        recovery_policy="snapshot_ram",
        discovery_name="SealedStore",
        evidence=(
            "skeleton/vault/store.py",
            "skeleton/vault/recovery.py",
        ),
        notes="Not restart-durable; recovery snapshots stay in RAM.",
    ),
    DurableStore(
        store_id="vault.secrets",
        family="vault",
        status="classified",
        format="versioned envelope-encrypted secret records",
        owner="skeleton.vault.secrets",
        owner_path="skeleton/vault/secrets.py",
        persistence="process memory; sealed until master-key unseal",
        restart_durable=False,
        corruption="VaultIntegrityError when ciphertext MAC fails",
        recovery="seal refuses payload ops; versions retained in RAM; master rotate rewraps keys",
        corruption_policy="fail_closed",
        recovery_policy="none",
        discovery_name="SecretsVault",
        evidence=("skeleton/vault/secrets.py",),
        notes="In-process vault. Restart loses secrets unless another layer persists them.",
    ),
    DurableStore(
        store_id="vault.secrets_audit",
        family="vault",
        status="classified",
        format="in-memory hash-chained AuditRecord list",
        owner="skeleton.vault.secrets",
        owner_path="skeleton/vault/secrets.py",
        persistence="process memory (SecretsVault.audit)",
        restart_durable=False,
        corruption="AuditLog.verify() returns False on prev-hash or digest mismatch",
        recovery="no disk restore; verify is boolean and does not refuse boot",
        corruption_policy="verify_bool",
        recovery_policy="none",
        discovery_name="AuditLog",
        evidence=("skeleton/vault/secrets.py",),
        notes="Distinct from vault.worm_audit. Nested in SecretsVault, not WORM JSONL.",
    ),
    DurableStore(
        store_id="swarm.durable",
        family="swarm_durable",
        status="classified",
        format="SwarmRecoveryManager archive v1 inside SQLiteRunStore checkpoint JSON",
        owner="skeleton.agents.swarm_durable",
        owner_path="skeleton/agents/swarm_durable.py",
        persistence="caller SQLiteRunStore path (docs: var/skeleton-runs.sqlite3)",
        restart_durable=True,
        corruption="DurableSwarmError on version mismatch, non-object payload, or invalid archive",
        recovery=(
            "load() verifies via SwarmRecoveryManager.from_archive; capture() discards "
            "the just-created in-memory checkpoint if durable persist fails"
        ),
        corruption_policy="fail_closed",
        recovery_policy="restore_verified",
        discovery_name="SwarmDurableBridge",
        evidence=(
            "skeleton/agents/swarm_durable.py",
            "skeleton/testing/test_swarm_durable.py",
            "docs/DURABLE_RUN_STATE.md",
        ),
        notes=(
            "Bridge only. Canonical swarm serializer remains SwarmRecoveryManager. "
            "This inventory does not rewrite swarm recovery."
        ),
    ),
    DurableStore(
        store_id="organism.quality_state",
        family="quality_state",
        status="classified",
        format="jsonl quality/repair rows",
        owner="skeleton.organism.quality_state",
        owner_path="skeleton/organism/quality_state.py",
        persistence=".skeleton/organism/quality.jsonl via quality_path()",
        restart_durable=True,
        corruption="JSONDecodeError lines are skipped on load; missing file is empty",
        recovery="skip corrupt lines; trim_quality keeps the last 256 rows",
        corruption_policy="skip_corrupt",
        recovery_policy="skip",
        discovery_name="quality_state",
        evidence=(
            "skeleton/organism/quality_state.py",
            "skeleton/organism/paths.py",
            "skeleton/testing/test_quality_state.py",
        ),
        notes="Honest skip-corrupt read path. Inventory does not change that policy.",
    ),
    DurableStore(
        store_id="retrieval.provenance",
        family="provenance_ledger",
        status="classified",
        format="in-memory ProvenanceEntry map with parent chains",
        owner="skeleton.retrieval.provenance",
        owner_path="skeleton/retrieval/provenance.py",
        persistence="process memory",
        restart_durable=False,
        corruption="verify() returns False when current data hash != recorded output_hash",
        recovery="no disk restore; missing entry_id is not a chain",
        corruption_policy="verify_bool",
        recovery_policy="none",
        discovery_name="ProvenanceLedger",
        evidence=(
            "skeleton/retrieval/provenance.py",
            "skeleton/retrieval/__init__.py",
        ),
        notes="Retrieval lineage ledger. In-process only.",
    ),
    DurableStore(
        store_id="cognition.provenance",
        family="provenance_ledger",
        status="classified",
        format="hash-chained LedgerEntry sequence",
        owner="skeleton.cognition.ledger",
        owner_path="skeleton/cognition/ledger.py",
        persistence="process memory; export()/from_entries() for interchange",
        restart_durable=False,
        corruption="verify() false on mutation/truncation/reorder; from_entries raises ValueError",
        recovery="from_entries refuses an invalid chain (fail-closed import)",
        corruption_policy="fail_closed",
        recovery_policy="restore_verified",
        discovery_name="ProvenanceLedger",
        evidence=(
            "skeleton/cognition/ledger.py",
            "skeleton/cognition/__init__.py",
        ),
        notes="Cognitive execution journal. Distinct from retrieval.provenance.",
    ),
    DurableStore(
        store_id="cortex.gaming_provenance",
        family="provenance_ledger",
        status="classified",
        format="jsonl pointer hashes (never page text)",
        owner="skeleton.cortex.refs",
        owner_path="skeleton/cortex/refs.py",
        persistence="acquired/gaming/provenance.jsonl via provenance_path()",
        restart_durable=True,
        corruption="write-time check(); reads do not hash-chain verify",
        recovery="append-only; missing file means empty history",
        corruption_policy="none",
        recovery_policy="none",
        discovery_name="record_provenance",
        evidence=(
            "skeleton/cortex/refs.py",
            "skeleton/acquired/gaming/provenance.jsonl",
        ),
        notes="Cortex gaming pointer log. Not a ProvenanceLedger class.",
    ),
    DurableStore(
        store_id="frontier.sqlite_collection",
        family="sqlite_collection",
        status="classified",
        format="sqlite table frontier_memory_items (namespace, item_id, document, metadata_json)",
        owner="skeleton.frontier.memory_adapters",
        owner_path="skeleton/frontier/memory_adapters.py",
        persistence="caller sqlite path; :memory: allowed (not restart-durable)",
        restart_durable=True,
        corruption="MemoryStoreCorruptionError on malformed identity, document, or metadata",
        recovery="fail-closed decode; corrupt rows never become memory hits or filtered mutations",
        corruption_policy="fail_closed",
        recovery_policy="refuse",
        discovery_name="SQLiteCollection",
        evidence=(
            "skeleton/frontier/memory_adapters.py",
            "skeleton/testing/test_frontier_memory_corruption.py",
            "skeleton/testing/test_frontier_memory_row_identity.py",
        ),
        notes="Backend for MemoryContract. :memory: is a valid non-durable path.",
    ),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _stores_by_id(inventory: Iterable[DurableStore]) -> dict[str, DurableStore]:
    return {store.store_id: store for store in inventory}


STORES_BY_ID = _stores_by_id(STORES)


def inventory_table(
    inventory: Iterable[DurableStore] = STORES,
) -> list[dict[str, object]]:
    """Stable operator-facing rows for the classified durable-state surface."""
    rows: list[dict[str, object]] = []
    for store in inventory:
        rows.append(
            {
                "id": store.store_id,
                "family": store.family,
                "status": store.status,
                "format": store.format,
                "owner": store.owner,
                "owner_path": store.owner_path,
                "persistence": store.persistence,
                "restart_durable": store.restart_durable,
                "corruption": store.corruption,
                "recovery": store.recovery,
                "corruption_policy": store.corruption_policy,
                "recovery_policy": store.recovery_policy,
                "evidence": list(store.evidence),
                "notes": store.notes,
            }
        )
    return rows


def require_store(
    store_id: str,
    inventory: Iterable[DurableStore] = STORES,
) -> DurableStore:
    """Return a classified store or fail closed on unknown/unclassified ids."""
    if not isinstance(store_id, str) or not store_id.strip() or store_id != store_id.strip():
        raise UnknownDurableStoreError("store_id must be a non-empty normalized string")
    mapping = _stores_by_id(inventory)
    store = mapping.get(store_id)
    if store is None:
        raise UnknownDurableStoreError(f"unknown durable store: {store_id}")
    if store.status != "classified":
        raise UnknownDurableStoreError(
            f"unclassified durable store fails closed: {store_id}"
        )
    return store


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_production_python(root: Path) -> Iterable[Path]:
    skeleton = root / "skeleton"
    if not skeleton.is_dir():
        return
    for path in skeleton.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        yield path


def _class_names(path: Path) -> tuple[str, ...]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ()
    return tuple(
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    )


def _function_names(path: Path) -> tuple[str, ...]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ()
    return tuple(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    )


def discover_stores(root: Path) -> tuple[tuple[str, str, str], ...]:
    """Return (relative_path, discovery_name, family) for scanned production stores."""
    found: list[tuple[str, str, str]] = []
    for path in _iter_production_python(root):
        relative = _relative(path, root)
        classes = _class_names(path)
        functions = _function_names(path)
        if relative.endswith("quality_state.py"):
            found.append((relative, "quality_state", "quality_state"))
        if "ProvenanceLedger" in classes:
            found.append((relative, "ProvenanceLedger", "provenance_ledger"))
        if "SQLiteCollection" in classes:
            found.append((relative, "SQLiteCollection", "sqlite_collection"))
        if "SwarmDurableBridge" in classes:
            found.append((relative, "SwarmDurableBridge", "swarm_durable"))
        if relative.startswith("skeleton/vault/"):
            if "SealedStore" in classes:
                found.append((relative, "SealedStore", "vault"))
            if "SecretsVault" in classes:
                found.append((relative, "SecretsVault", "vault"))
            if "AuditLog" in classes:
                found.append((relative, "AuditLog", "vault"))
        if relative == "skeleton/cortex/refs.py" and "record_provenance" in functions:
            found.append((relative, "record_provenance", "provenance_ledger"))
    return tuple(found)


def _catalog_index(
    inventory: Iterable[DurableStore],
) -> dict[tuple[str, str], DurableStore]:
    return {(store.owner_path, store.discovery_name): store for store in inventory}


def _row_violations(store: DurableStore, *, root: Path, require_paths: bool) -> list[str]:
    issues: list[str] = []
    prefix = f"{store.store_id}: "
    if not store.store_id.strip():
        issues.append("empty store_id")
    if store.family not in FAMILY_SET:
        issues.append(prefix + f"unknown family fails closed: {store.family}")
    if store.status not in STATUS_SET:
        issues.append(prefix + f"unknown status fails closed: {store.status}")
    if store.status == "unknown":
        issues.append(prefix + "unknown status fails closed")
    if store.corruption_policy not in CORRUPTION_POLICY_SET:
        issues.append(
            prefix + f"unknown corruption policy fails closed: {store.corruption_policy}"
        )
    if store.recovery_policy not in RECOVERY_POLICY_SET:
        issues.append(
            prefix + f"unknown recovery policy fails closed: {store.recovery_policy}"
        )
    for field_name in ("format", "owner", "owner_path", "persistence", "corruption", "recovery"):
        if not str(getattr(store, field_name) or "").strip():
            issues.append(prefix + f"incomplete classification: missing {field_name}")
    if not store.discovery_name.strip():
        issues.append(prefix + "incomplete classification: missing discovery_name")
    if not store.evidence:
        issues.append(prefix + "incomplete classification: missing evidence")
    if require_paths:
        owner = root / store.owner_path
        if not owner.is_file():
            issues.append(prefix + f"missing owner path: {store.owner_path}")
        for evidence in store.evidence:
            evidence_path = root / evidence
            if not evidence_path.exists():
                issues.append(prefix + f"missing evidence: {evidence}")
    return issues


def collect_violations(
    root: Path | None = None,
    *,
    inventory: Iterable[DurableStore] = STORES,
    require_paths: bool = True,
    require_families: bool = True,
) -> list[str]:
    """Return inventory defects. Empty means the catalog is closed."""
    repo = root or _repo_root()
    rows = tuple(inventory)
    issues: list[str] = []

    seen_ids: dict[str, int] = {}
    for store in rows:
        seen_ids[store.store_id] = seen_ids.get(store.store_id, 0) + 1
        issues.extend(_row_violations(store, root=repo, require_paths=require_paths))
    for store_id, count in seen_ids.items():
        if count > 1:
            issues.append(f"{store_id}: duplicate store_id fails closed")

    if require_families:
        present = {store.family for store in rows if store.status == "classified"}
        missing = [family for family in FAMILIES if family not in present]
        if missing:
            issues.append(
                "missing classified family fails closed: " + ", ".join(missing)
            )

    catalog = _catalog_index(rows)
    for relative, name, family in discover_stores(repo):
        store = catalog.get((relative, name))
        if store is None:
            issues.append(
                f"unknown durable store fails closed: {relative}::{name} (family={family})"
            )
            continue
        if store.family != family:
            issues.append(
                f"{store.store_id}: discovered family {family} disagrees with catalog {store.family}"
            )
        if store.status != "classified":
            issues.append(
                f"{store.store_id}: discovered store is unclassified and fails closed"
            )
    return issues


def assert_inventory_closed(root: Path | None = None) -> None:
    """Fail closed if the repository has unknown or incomplete durable stores."""
    issues = collect_violations(root)
    if issues:
        raise UnknownDurableStoreError("; ".join(issues))


def main() -> int:
    issues = collect_violations()
    for row in inventory_table():
        print(
            f"{row['id']}\t{row['family']}\t{row['status']}\t"
            f"{row['corruption_policy']}/{row['recovery_policy']}\t{row['owner_path']}"
        )
    if issues:
        print("VIOLATIONS:")
        for item in issues:
            print(f"- {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
