"""Fail-closed inventory of subsystem invariants versus property-test evidence.

SHIFT-PROMOTION-SEED #969 Seed 17
task_id: ``reserve-S081-property-test-inventory``
conflict_domain: ``quality.readonly.property_inventory``

This module inventories invariants; it does not author a property-test suite
for every subsystem. Coverage is never inferred. An example-based test, a
parametrize list, or a neighbouring file is not property coverage. Missing
evidence is ``missing``, never ``probably covered``.

Out of scope (owned elsewhere, omitted from gaps):

- replay quality evidence harness (#1030)
- concept-to-release benchmark (#1039)
- mechanics replay contract (#1149)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence

SCHEMA = "quality.property_inventory.v1"
SCHEMA_VERSION = 1
TASK_ID = "reserve-S081-property-test-inventory"
CONFLICT_DOMAIN = "quality.readonly.property_inventory"
ISSUE = "#969"
SEED = 17

EXCLUDED_OWNERS = {
    "#1030": "replay quality evidence harness",
    "#1039": "concept-to-release benchmark",
    "#1149": "mechanics replay contract",
}

TEST_ROOTS = (
    Path("skeleton") / "testing",
    Path("backend") / "tests",
    Path("tests"),
)
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        "satellites",
        "venv",
    }
)
EXCLUDED_EVIDENCE_NAMES = frozenset(
    {
        "property_inventory.py",
        "test_property_inventory.py",
    }
)

_HYPOTHESIS_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+hypothesis(?:\.[A-Za-z0-9_]+)?[ \t]+import|import[ \t]+hypothesis)\b",
    re.M,
)
_GIVEN = re.compile(r"^[ \t]*@given\b", re.M)
_COVERS_ASSIGN = re.compile(
    r"(?:PROPERTY_INVARIANTS|PROPERTY_TEST_INVARIANTS)[ \t]*=[ \t]*(\([^)]*\)|\[[^\]]*\]|\{[^}]*\})",
    re.S,
)
_COVERS_COMMENT = re.compile(r"^[ \t]*#[ \t]*property-coverage:[ \t]*(.+)$", re.M)
_STRING_LITERAL = re.compile(r"['\"]([^'\"]+)['\"]")
_PROPERTY_FILENAME = re.compile(
    r"^(?:test_.*_properties\.py|test_.*_property\.py|test_properties_.*\.py)$"
)

_COVERED_LABELS = frozenset({"covered"})
_MISSING_LABELS = frozenset({"missing"})
_EXCLUDED_LABELS = frozenset({"excluded"})


class PropertyInventoryError(ValueError):
    """Fail-closed contract violation for the property-test inventory."""


class CoverageStatus(str, Enum):
    COVERED = "covered"
    MISSING = "missing"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class SubsystemInvariant:
    """A named subsystem invariant that may or may not have property tests."""

    invariant_id: str
    subsystem: str
    statement: str
    source_path: str
    evidence_tokens: tuple[str, ...]
    owner_issue: str | None = None

    def __post_init__(self) -> None:
        invariant_id = self.invariant_id.strip() if isinstance(self.invariant_id, str) else ""
        subsystem = self.subsystem.strip() if isinstance(self.subsystem, str) else ""
        statement = self.statement.strip() if isinstance(self.statement, str) else ""
        source_path = self.source_path.strip() if isinstance(self.source_path, str) else ""
        if not invariant_id:
            raise PropertyInventoryError("invariant_id is required")
        if not subsystem:
            raise PropertyInventoryError(f"{invariant_id}: subsystem is required")
        if not statement:
            raise PropertyInventoryError(f"{invariant_id}: statement is required")
        if not source_path:
            raise PropertyInventoryError(f"{invariant_id}: source_path is required")
        if not self.evidence_tokens:
            raise PropertyInventoryError(
                f"{invariant_id}: evidence_tokens are required; empty tokens cannot prove coverage"
            )
        if any(not isinstance(token, str) or not token.strip() for token in self.evidence_tokens):
            raise PropertyInventoryError(f"{invariant_id}: evidence_tokens must be non-empty strings")
        object.__setattr__(self, "invariant_id", invariant_id)
        object.__setattr__(self, "subsystem", subsystem)
        object.__setattr__(self, "statement", statement)
        object.__setattr__(self, "source_path", source_path)


@dataclass(frozen=True, slots=True)
class PropertyEvidence:
    """A test file that is property-test evidence, not an example suite."""

    path: str
    detector: str
    bound_invariant_ids: tuple[str, ...]
    haystack: str


@dataclass(frozen=True, slots=True)
class CoverageRow:
    invariant: SubsystemInvariant
    status: CoverageStatus
    evidence_paths: tuple[str, ...]
    reason: str

    def to_payload(self) -> dict[str, object]:
        return {
            "invariant_id": self.invariant.invariant_id,
            "subsystem": self.invariant.subsystem,
            "statement": self.invariant.statement,
            "source_path": self.invariant.source_path,
            "owner_issue": self.invariant.owner_issue,
            "status": self.status.value,
            "evidence_paths": list(self.evidence_paths),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class InventoryReport:
    schema: str
    schema_version: int
    task_id: str
    conflict_domain: str
    rows: tuple[CoverageRow, ...]
    evidence: tuple[PropertyEvidence, ...]

    def to_payload(self) -> dict[str, object]:
        missing = tuple(row.invariant.invariant_id for row in gaps(self))
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "conflict_domain": self.conflict_domain,
            "issue": ISSUE,
            "seed": SEED,
            "row_count": len(self.rows),
            "covered_count": sum(row.status is CoverageStatus.COVERED for row in self.rows),
            "missing_count": len(missing),
            "excluded_count": sum(row.status is CoverageStatus.EXCLUDED for row in self.rows),
            "missing_invariant_ids": list(missing),
            "rows": [row.to_payload() for row in self.rows],
            "evidence_paths": [item.path for item in self.evidence],
        }


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_catalog() -> tuple[SubsystemInvariant, ...]:
    """Curated subsystem invariants. Exhaustive auto-discovery is not coverage."""

    return _freeze_catalog(
        (
            SubsystemInvariant(
                invariant_id="security.request_id.bounded_header_safe",
                subsystem="security",
                statement="Generated request IDs stay bounded and header-safe for arbitrary inputs.",
                source_path="backend/tests/test_security_middleware_properties.py",
                evidence_tokens=("test_generated_request_id_corpus_is_always_bounded_and_header_safe",),
            ),
            SubsystemInvariant(
                invariant_id="security.request_id.duplicate_rejected",
                subsystem="security",
                statement="Duplicate request-id headers never select an attacker-supplied value.",
                source_path="backend/tests/test_security_middleware_properties.py",
                evidence_tokens=("test_duplicate_request_ids_never_select_an_attacker_value",),
            ),
            SubsystemInvariant(
                invariant_id="security.forwarded_for.parser_fail_safe",
                subsystem="security",
                statement="Forwarded-for chains fail safely without parser crashes.",
                source_path="backend/tests/test_security_middleware_properties.py",
                evidence_tokens=("test_generated_forwarded_chains_fail_safely_without_parser_crashes",),
            ),
            SubsystemInvariant(
                invariant_id="security.content_length.bounded_telemetry",
                subsystem="security",
                statement="Declared content-length values are bounded telemetry or rejected.",
                source_path="backend/tests/test_security_middleware_properties.py",
                evidence_tokens=("test_generated_content_lengths_are_bounded_telemetry_only",),
            ),
            SubsystemInvariant(
                invariant_id="security.route_prefix.exact_or_child",
                subsystem="security",
                statement="Route lookalikes match only exact or child API paths.",
                source_path="backend/tests/test_security_middleware_properties.py",
                evidence_tokens=("test_generated_route_lookalikes_match_only_exact_or_child_api_paths",),
            ),
            SubsystemInvariant(
                invariant_id="security.size_limit.content_length_match",
                subsystem="security",
                statement="Size-limit middleware accepts exact content-length matches and rejects mismatches.",
                source_path="backend/tests/test_security_middleware_properties.py",
                evidence_tokens=("test_content_length_exact_match_and_mismatch_property",),
            ),
            SubsystemInvariant(
                invariant_id="swarm.lease_ownership_consistent",
                subsystem="swarm",
                statement="Leased tasks and worker active sets name the same owners.",
                source_path="skeleton/agents/swarm_invariants.py",
                evidence_tokens=("leased task absent from worker active set",),
            ),
            SubsystemInvariant(
                invariant_id="swarm.snapshot_counts_match_tasks",
                subsystem="swarm",
                statement="Runtime snapshot counts equal enumerated task states.",
                source_path="skeleton/agents/swarm_invariants.py",
                evidence_tokens=("state count mismatch",),
            ),
            SubsystemInvariant(
                invariant_id="learning.evidence.contradiction_fail_closed",
                subsystem="learning",
                statement="Contradictory hypotheses are rejected rather than averaged.",
                source_path="skeleton/learning/evidence.py",
                evidence_tokens=("test_contradictory_hypotheses_fail_closed",),
            ),
            SubsystemInvariant(
                invariant_id="learning.evidence.provenance_required",
                subsystem="learning",
                statement="Missing provenance is rejected; it is not synthesized.",
                source_path="skeleton/learning/evidence.py",
                evidence_tokens=("missing_parent", "record_hypothesis"),
            ),
            SubsystemInvariant(
                invariant_id="kernel.lattice.mag_index_consistent",
                subsystem="kernel",
                statement="MAG tag index never refers to episodes that do not exist.",
                source_path="skeleton/genesis.py",
                evidence_tokens=("mag_index_consistent",),
            ),
            SubsystemInvariant(
                invariant_id="vault.shamir.threshold_secrecy",
                subsystem="vault",
                statement="Any k-1 Shamir shares reveal nothing about the seal.",
                source_path="skeleton/vault/shamir.py",
                evidence_tokens=("ShamirSeal", "k-1"),
            ),
            SubsystemInvariant(
                invariant_id="kv.cache.namespace_isolation",
                subsystem="kv",
                statement="KV cache lookups never cross trust-domain namespaces.",
                source_path="skeleton/kv_cache.py",
                evidence_tokens=("invalidate_namespace", "trust_domain"),
            ),
            SubsystemInvariant(
                invariant_id="hmac.seal.expiry_rejected",
                subsystem="api",
                statement="Expired HMAC seals fail closed instead of verifying.",
                source_path="skeleton/api/hmac_seal.py",
                evidence_tokens=("test_verify_expired",),
            ),
            SubsystemInvariant(
                invariant_id="game.mechanics.resource_bounds_finite",
                subsystem="game",
                statement="Resource bounds and non-finite AI levels fail closed.",
                source_path="skeleton/game/mechanics.py",
                evidence_tokens=("test_resource_bounds_and_non_finite_ai_levels_fail_closed",),
            ),
            SubsystemInvariant(
                invariant_id="application.command.require_bool_rejects_truthy",
                subsystem="application",
                statement="Command contracts reject truthy stand-ins for booleans.",
                source_path="skeleton/application/command_contracts.py",
                evidence_tokens=("require_bool", "must be a boolean"),
            ),
            SubsystemInvariant(
                invariant_id="frontier.digest.canonical_mapping_stable",
                subsystem="frontier",
                statement="Canonical JSON mappings hash independently of insertion order.",
                source_path="skeleton/frontier/contracts.py",
                evidence_tokens=("stable_content_digest", "sort_keys"),
            ),
            SubsystemInvariant(
                invariant_id="quality.replay.tape_integrity",
                subsystem="quality.replay",
                statement="Replay tape digests detect divergence without a second replay core.",
                source_path="skeleton/cognition/replay.py",
                evidence_tokens=("ReplayTape", "divergence"),
                owner_issue="#1030",
            ),
            SubsystemInvariant(
                invariant_id="eval.concept_to_release.missing_unscored",
                subsystem="eval",
                statement="Missing concept-to-release evidence stays missing rather than scoring as zero.",
                source_path="skeleton/eval/concept_to_release.py",
                evidence_tokens=("missing", "concept_to_release"),
                owner_issue="#1039",
            ),
            SubsystemInvariant(
                invariant_id="game.mechanics.replay.deterministic_digests",
                subsystem="game.replay",
                statement="Mechanics replay digests are seed/tick determined, not process-clock determined.",
                source_path="skeleton/game/replay.py",
                evidence_tokens=("spec_digest", "state_digest"),
                owner_issue="#1149",
            ),
        )
    )


def _freeze_catalog(rows: Sequence[SubsystemInvariant]) -> tuple[SubsystemInvariant, ...]:
    seen: dict[str, SubsystemInvariant] = {}
    for row in rows:
        if row.invariant_id in seen:
            raise PropertyInventoryError(f"duplicate invariant_id: {row.invariant_id}")
        seen[row.invariant_id] = row
    return tuple(seen[key] for key in sorted(seen))


def normalize_status(value: object) -> CoverageStatus:
    """Map labels fail-closed. Unknown and 'probably covered' are missing."""

    if isinstance(value, CoverageStatus):
        return value
    if isinstance(value, str):
        label = value.strip().lower().replace("-", "_").replace(" ", "_")
        if label in _COVERED_LABELS:
            return CoverageStatus.COVERED
        if label in _EXCLUDED_LABELS:
            return CoverageStatus.EXCLUDED
        if label in _MISSING_LABELS:
            return CoverageStatus.MISSING
    return CoverageStatus.MISSING


def filename_is_property_suite(path: Path | str) -> bool:
    name = Path(path).name.lower()
    if name in EXCLUDED_EVIDENCE_NAMES:
        return False
    return _PROPERTY_FILENAME.fullmatch(name) is not None


def extract_explicit_covers(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _COVERS_ASSIGN.finditer(text):
        found.extend(_STRING_LITERAL.findall(match.group(1)))
    for match in _COVERS_COMMENT.finditer(text):
        for part in match.group(1).split(","):
            item = part.strip()
            if item:
                found.append(item)
    unique = {item.strip() for item in found if item.strip()}
    return tuple(sorted(unique))


def detect_property_evidence(path: Path | str, text: str | None) -> PropertyEvidence | None:
    """Return evidence only when a property-test detector fires.

    Unreadable or empty files are not evidence. Example-based tests are not
    evidence even when they mention the same tokens.
    """

    file_path = Path(path)
    if file_path.name in EXCLUDED_EVIDENCE_NAMES:
        return None
    if text is None:
        return None
    if not isinstance(text, str):
        return None

    detectors: list[str] = []
    if filename_is_property_suite(file_path):
        detectors.append("properties_filename")
    if _HYPOTHESIS_IMPORT.search(text) or _GIVEN.search(text):
        detectors.append("hypothesis")
    covers = extract_explicit_covers(text)
    if covers:
        detectors.append("explicit_marker")
    if not detectors:
        return None
    return PropertyEvidence(
        path=_posix_relative(file_path),
        detector="+".join(detectors),
        bound_invariant_ids=covers,
        haystack=text,
    )


def evidence_covers(invariant: SubsystemInvariant, evidence: PropertyEvidence) -> bool:
    if evidence.bound_invariant_ids:
        return invariant.invariant_id in evidence.bound_invariant_ids
    return all(token in evidence.haystack for token in invariant.evidence_tokens)


def classify_coverage(
    invariant: SubsystemInvariant,
    evidence: Sequence[PropertyEvidence],
) -> CoverageRow:
    if invariant.owner_issue in EXCLUDED_OWNERS:
        return CoverageRow(
            invariant=invariant,
            status=CoverageStatus.EXCLUDED,
            evidence_paths=(),
            reason=f"owned by {invariant.owner_issue} {EXCLUDED_OWNERS[invariant.owner_issue]}",
        )
    matches = [item.path for item in evidence if evidence_covers(invariant, item)]
    unique_paths = tuple(sorted(dict.fromkeys(matches)))
    if unique_paths:
        return CoverageRow(
            invariant=invariant,
            status=CoverageStatus.COVERED,
            evidence_paths=unique_paths,
            reason="property-test evidence binds this invariant",
        )
    return CoverageRow(
        invariant=invariant,
        status=CoverageStatus.MISSING,
        evidence_paths=(),
        reason="missing property-test evidence",
    )


def gaps(report: InventoryReport) -> tuple[CoverageRow, ...]:
    return tuple(row for row in report.rows if row.status is CoverageStatus.MISSING)


def scan_property_evidence(repo_root: Path) -> tuple[PropertyEvidence, ...]:
    if not repo_root.is_dir():
        raise PropertyInventoryError(f"repo root is not a directory: {repo_root}")
    found: dict[str, PropertyEvidence] = {}
    for relative_root in TEST_ROOTS:
        root = repo_root / relative_root
        if not root.is_dir():
            continue
        for path in _iter_python_tests(root):
            evidence = detect_property_evidence(path.relative_to(repo_root), _read_text(path))
            if evidence is None:
                continue
            found[evidence.path] = evidence
    return tuple(found[key] for key in sorted(found))


def inventory_property_coverage(
    repo_root: Path | str | None = None,
    catalog: Sequence[SubsystemInvariant] | None = None,
    evidence: Sequence[PropertyEvidence] | None = None,
) -> InventoryReport:
    root = Path(repo_root) if repo_root is not None else default_repo_root()
    invariants = _freeze_catalog(catalog if catalog is not None else default_catalog())
    scanned = tuple(evidence) if evidence is not None else scan_property_evidence(root)
    rows = tuple(classify_coverage(item, scanned) for item in invariants)
    return InventoryReport(
        schema=SCHEMA,
        schema_version=SCHEMA_VERSION,
        task_id=TASK_ID,
        conflict_domain=CONFLICT_DOMAIN,
        rows=rows,
        evidence=scanned,
    )


def _iter_python_tests(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name in EXCLUDED_EVIDENCE_NAMES:
            continue
        yield path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _posix_relative(path: Path) -> str:
    as_posix = path.as_posix()
    return as_posix[2:] if as_posix.startswith("./") else as_posix


def catalog_by_id(
    catalog: Sequence[SubsystemInvariant] | None = None,
) -> Mapping[str, SubsystemInvariant]:
    rows = catalog if catalog is not None else default_catalog()
    return {row.invariant_id: row for row in _freeze_catalog(rows)}
