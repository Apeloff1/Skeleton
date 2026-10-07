"""Immutable provenance attached to promoted frontier artifacts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Provenance:
    source: str
    revision: str
    derived_by: str

    def __post_init__(self) -> None:
        for value in (self.source, self.revision, self.derived_by):
            if not value.strip():
                raise ValueError("provenance fields must be non-empty")
