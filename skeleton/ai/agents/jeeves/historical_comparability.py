"""Explicit benchmark-comparability contracts for Jeeves historical evidence.

Sharing a broad domain label does not make two benchmark revisions statistically
interchangeable. This module audits the exact benchmark keys used by a champion
and requires an explicit compatibility contract whenever a domain blends more
than one benchmark key.

The contract does not transform scores. It documents that the caller considers
the already-normalized benchmark revisions comparable for the stated purpose.
Absent or ambiguous contracts fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from skeleton.jeeves.historical_models import (
    BenchmarkDomain,
    ChampionDecision,
    HistoricalModelRegistry,
    canonical_fingerprint,
)


MAX_CONTRACTS: Final = 2_000
MAX_KEYS_PER_CONTRACT: Final = 128


class HistoricalComparabilityError(ValueError):
    """Invalid benchmark compatibility declaration or audit input."""


def _text(name: str, value: object, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalComparabilityError(f"{name} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalComparabilityError(f"{name} exceeds {maximum} characters")
    return cleaned


@dataclass(frozen=True, slots=True)
class BenchmarkCompatibilityContract:
    contract_id: str
    revision: str
    domain: BenchmarkDomain
    benchmark_keys: frozenset[str]
    rationale_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _text("contract_id", self.contract_id, 160))
        object.__setattr__(self, "revision", _text("revision", self.revision, 160))
        if not isinstance(self.domain, BenchmarkDomain):
            raise HistoricalComparabilityError("domain must be BenchmarkDomain")
        keys = frozenset(_text("benchmark_key", item, 320) for item in self.benchmark_keys)
        if len(keys) < 2:
            raise HistoricalComparabilityError("compatibility contract must cover at least two benchmark keys")
        if len(keys) > MAX_KEYS_PER_CONTRACT:
            raise HistoricalComparabilityError("compatibility contract benchmark limit exceeded")
        object.__setattr__(self, "benchmark_keys", keys)
        object.__setattr__(
            self,
            "rationale_fingerprint",
            _text("rationale_fingerprint", self.rationale_fingerprint, 256),
        )

    @property
    def key(self) -> str:
        return f"{self.contract_id}@{self.revision}"

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "key": self.key,
                "domain": self.domain.value,
                "benchmarks": sorted(self.benchmark_keys),
                "rationale": self.rationale_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class DomainComparability:
    domain: BenchmarkDomain
    benchmark_keys: tuple[str, ...]
    compatible: bool
    contract_key: str | None
    contract_fingerprint: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class BenchmarkComparabilityReport:
    champion_model: str
    domains: tuple[DomainComparability, ...]
    incompatible_domains: tuple[BenchmarkDomain, ...]
    passed: bool
    contract_set_fingerprint: str
    report_fingerprint: str


class HistoricalBenchmarkComparabilityAuditor:
    """Require explicit compatibility when champion evidence blends benchmarks."""

    def __init__(self, contracts: tuple[BenchmarkCompatibilityContract, ...] | list[BenchmarkCompatibilityContract] = ()) -> None:
        contracts = tuple(contracts)
        if len(contracts) > MAX_CONTRACTS:
            raise HistoricalComparabilityError("compatibility contract limit exceeded")
        if any(not isinstance(item, BenchmarkCompatibilityContract) for item in contracts):
            raise HistoricalComparabilityError("contracts must contain BenchmarkCompatibilityContract values")
        keys = [item.key for item in contracts]
        if len(keys) != len(set(keys)):
            raise HistoricalComparabilityError("compatibility contract keys must be unique")
        self._contracts = tuple(sorted(contracts, key=lambda item: item.key))
        self.contract_set_fingerprint = canonical_fingerprint(
            [item.fingerprint for item in self._contracts]
        )

    def audit(
        self,
        *,
        decision: ChampionDecision,
        registry: HistoricalModelRegistry,
    ) -> BenchmarkComparabilityReport:
        if not isinstance(decision, ChampionDecision):
            raise HistoricalComparabilityError("decision must be ChampionDecision")
        if not isinstance(registry, HistoricalModelRegistry):
            raise HistoricalComparabilityError("registry must be HistoricalModelRegistry")

        used_ids = {
            snapshot_id
            for domain in decision.champion.domains
            for snapshot_id in domain.snapshot_ids
        }
        by_id = {snapshot.snapshot_id: snapshot for snapshot in registry.snapshots()}
        missing = sorted(used_ids - set(by_id))
        if missing:
            raise HistoricalComparabilityError(
                f"decision references snapshots absent from registry: {missing}"
            )

        by_domain: dict[BenchmarkDomain, set[str]] = {}
        for snapshot_id in used_ids:
            snapshot = by_id[snapshot_id]
            if snapshot.model != decision.champion.model:
                raise HistoricalComparabilityError("decision snapshot model mismatch")
            by_domain.setdefault(snapshot.benchmark.domain, set()).add(snapshot.benchmark.key)

        results: list[DomainComparability] = []
        incompatible: list[BenchmarkDomain] = []
        for domain in sorted(by_domain, key=lambda item: item.value):
            benchmark_keys = tuple(sorted(by_domain[domain]))
            if len(benchmark_keys) <= 1:
                results.append(
                    DomainComparability(
                        domain=domain,
                        benchmark_keys=benchmark_keys,
                        compatible=True,
                        contract_key=None,
                        contract_fingerprint=None,
                        reason="single_benchmark",
                    )
                )
                continue

            matching = [
                contract
                for contract in self._contracts
                if contract.domain is domain and set(benchmark_keys).issubset(contract.benchmark_keys)
            ]
            if len(matching) == 1:
                contract = matching[0]
                results.append(
                    DomainComparability(
                        domain=domain,
                        benchmark_keys=benchmark_keys,
                        compatible=True,
                        contract_key=contract.key,
                        contract_fingerprint=contract.fingerprint,
                        reason="explicit_contract",
                    )
                )
            elif not matching:
                incompatible.append(domain)
                results.append(
                    DomainComparability(
                        domain=domain,
                        benchmark_keys=benchmark_keys,
                        compatible=False,
                        contract_key=None,
                        contract_fingerprint=None,
                        reason="missing_contract",
                    )
                )
            else:
                incompatible.append(domain)
                results.append(
                    DomainComparability(
                        domain=domain,
                        benchmark_keys=benchmark_keys,
                        compatible=False,
                        contract_key=None,
                        contract_fingerprint=None,
                        reason="ambiguous_contract",
                    )
                )

        result_tuple = tuple(results)
        incompatible_tuple = tuple(sorted(incompatible, key=lambda item: item.value))
        payload = {
            "champion": decision.champion.model.key,
            "domains": [
                {
                    "domain": item.domain.value,
                    "benchmarks": list(item.benchmark_keys),
                    "compatible": item.compatible,
                    "contract": item.contract_key,
                    "contract_fingerprint": item.contract_fingerprint,
                    "reason": item.reason,
                }
                for item in result_tuple
            ],
            "contract_set": self.contract_set_fingerprint,
        }
        return BenchmarkComparabilityReport(
            champion_model=decision.champion.model.key,
            domains=result_tuple,
            incompatible_domains=incompatible_tuple,
            passed=not incompatible_tuple,
            contract_set_fingerprint=self.contract_set_fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )


def summarize_comparability(report: BenchmarkComparabilityReport) -> dict[str, object]:
    return {
        "champion_model": report.champion_model,
        "passed": report.passed,
        "incompatible_domains": [domain.value for domain in report.incompatible_domains],
        "contract_set_fingerprint": report.contract_set_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "domains": [
            {
                "domain": item.domain.value,
                "benchmark_keys": list(item.benchmark_keys),
                "compatible": item.compatible,
                "contract_key": item.contract_key,
                "contract_fingerprint": item.contract_fingerprint,
                "reason": item.reason,
            }
            for item in report.domains
        ],
    }