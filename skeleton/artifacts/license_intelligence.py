from dataclasses import dataclass


@dataclass(frozen=True)
class LicenseObligation:
    kind: str
    value: str

    def __post_init__(self) -> None:
        if not self.kind or not self.value:
            raise ValueError("license obligation identity required")


@dataclass(frozen=True)
class LicenseRecord:
    artifact: str
    version: str
    license_id: str | None
    obligations: tuple[LicenseObligation, ...]

    def __post_init__(self) -> None:
        if not self.artifact or not self.version:
            raise ValueError("artifact and version required")
        if self.license_id is not None and not self.license_id:
            raise ValueError("license_id cannot be empty")
        if any(not isinstance(item, LicenseObligation) for item in self.obligations):
            raise ValueError("license obligations required")
        keys = [(item.kind, item.value) for item in self.obligations]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate license obligation")


@dataclass(frozen=True)
class LicenseCompatibility:
    compatible: bool
    reason: str


def compatible(records, distribution: bool) -> LicenseCompatibility:
    items = tuple(records)
    if not isinstance(distribution, bool) or not items:
        return LicenseCompatibility(False, "invalid license query")
    if any(not isinstance(record, LicenseRecord) for record in items):
        return LicenseCompatibility(False, "invalid license record")

    by_artifact: dict[tuple[str, str], LicenseRecord] = {}
    for record in items:
        key = (record.artifact, record.version)
        previous = by_artifact.get(key)
        if previous is not None and previous != record:
            return LicenseCompatibility(False, "conflicting license records")
        by_artifact[key] = record

    if any(record.license_id is None for record in items):
        return LicenseCompatibility(False, "unknown license")
    if distribution and any(
        obligation.kind == "no-redistribution"
        for record in items
        for obligation in record.obligations
    ):
        return LicenseCompatibility(False, "redistribution forbidden")
    return LicenseCompatibility(True, "compatible")
