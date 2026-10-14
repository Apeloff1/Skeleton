"""Missingness diagnostics for experiment/report fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class MissingnessRecord:
    record_id: str
    fields: tuple[tuple[str, bool], ...]

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ReverseEngineeringError("missingness record requires identity")
        names = [name for name, _ in self.fields]
        if not names or len(names) != len(set(names)):
            raise ReverseEngineeringError("missingness fields must be non-empty and unique")
        if any(not name for name in names):
            raise ReverseEngineeringError("missingness field names must be non-empty")


@dataclass(frozen=True)
class MissingnessReport:
    record_count: int
    field_count: int
    missing_rate_by_field: tuple[tuple[str, float], ...]
    complete_record_ratio: float
    maximum_field_missing_rate: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_count": self.record_count,
            "field_count": self.field_count,
            "missing_rate_by_field": [list(item) for item in self.missing_rate_by_field],
            "complete_record_ratio": self.complete_record_ratio,
            "maximum_field_missing_rate": self.maximum_field_missing_rate,
            "digest": self.digest,
        }


def analyze_missingness(
    records: Sequence[MissingnessRecord],
) -> MissingnessReport:
    if not records:
        raise ReverseEngineeringError("missingness analysis requires records")
    ids = [record.record_id for record in records]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("missingness record ids must be unique")
    names = tuple(sorted(name for name, _ in records[0].fields))
    mappings: list[Mapping[str, bool]] = []
    for record in records:
        mapping = dict(record.fields)
        if tuple(sorted(mapping)) != names:
            raise ReverseEngineeringError("missingness records must share field sets")
        mappings.append(mapping)

    rates = tuple(
        (name, sum(mapping[name] for mapping in mappings) / len(mappings))
        for name in names
    )
    complete = sum(not any(mapping.values()) for mapping in mappings) / len(mappings)
    payload = {
        "records": [
            {
                "record_id": record.record_id,
                "fields": [[name, value] for name, value in sorted(record.fields)],
            }
            for record in sorted(records, key=lambda value: value.record_id)
        ]
    }
    return MissingnessReport(
        record_count=len(records),
        field_count=len(names),
        missing_rate_by_field=rates,
        complete_record_ratio=complete,
        maximum_field_missing_rate=max(value for _, value in rates),
        digest=stable_digest(payload),
    )
