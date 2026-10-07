"""Artifact-bound software bill of materials contracts for VOL-178."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


class SBOMError(ValueError):
    """An SBOM identity, component, or vulnerability invariant failed."""


_SCOPES=frozenset({"direct","transitive","native","container"})
_SEVERITIES=frozenset({"unknown","low","medium","high","critical"})
_STATUSES=frozenset({"open","accepted-risk","fixed","not-affected"})


def _token(name: str, value: object) -> str:
    if not isinstance(value,str) or not value or value != value.strip() or len(value)>512:
        raise SBOMError(f"{name} must be non-empty normalized text")
    return value


def _sha(name: str, value: object) -> str:
    if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
        raise SBOMError(f"{name} must be a lowercase sha256 digest")
    return value


def _digest(value: object) -> str:
    try:
        encoded=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError) as exc:
        raise SBOMError("SBOM evidence must be canonical JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SoftwareComponent:
    component_id: str
    name: str
    version: str
    scope: str
    artifact_digest: str
    license_id: str
    package_url: str | None = None

    def __post_init__(self) -> None:
        for name in ("component_id","name","version","license_id"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))
        if self.scope not in _SCOPES:
            raise SBOMError("scope must be direct, transitive, native, or container")
        object.__setattr__(self,"artifact_digest",_sha("artifact_digest",self.artifact_digest))
        if self.package_url is not None:
            object.__setattr__(self,"package_url",_token("package_url",self.package_url))

    @property
    def digest(self) -> str:
        return _digest({
            "component_id":self.component_id,
            "name":self.name,
            "version":self.version,
            "scope":self.scope,
            "artifact_digest":self.artifact_digest,
            "license_id":self.license_id,
            "package_url":self.package_url,
        })


@dataclass(frozen=True, slots=True)
class VulnerabilityFinding:
    finding_id: str
    component_digest: str
    advisory_id: str
    severity: str
    status: str

    def __post_init__(self) -> None:
        for name in ("finding_id","advisory_id"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))
        object.__setattr__(self,"component_digest",_sha("component_digest",self.component_digest))
        if self.severity not in _SEVERITIES:
            raise SBOMError("unsupported vulnerability severity")
        if self.status not in _STATUSES:
            raise SBOMError("unsupported vulnerability status")

    @property
    def digest(self) -> str:
        return _digest({
            "finding_id":self.finding_id,
            "component_digest":self.component_digest,
            "advisory_id":self.advisory_id,
            "severity":self.severity,
            "status":self.status,
        })


@dataclass(frozen=True, slots=True)
class SBOM:
    sbom_id: str
    format: str
    build_artifact_digest: str
    build_revision: str
    components: tuple[SoftwareComponent, ...]
    findings: tuple[VulnerabilityFinding, ...] = ()
    generated_by: str = "skeleton"

    def __post_init__(self) -> None:
        object.__setattr__(self,"sbom_id",_token("sbom_id",self.sbom_id))
        if self.format != "cyclonedx-json":
            raise SBOMError("SBOM format must be cyclonedx-json")
        object.__setattr__(self,"build_artifact_digest",_sha("build_artifact_digest",self.build_artifact_digest))
        revision=_token("build_revision",self.build_revision).lower()
        if len(revision)!=40 or any(ch not in "0123456789abcdef" for ch in revision):
            raise SBOMError("build_revision must be a 40-character lowercase Git SHA")
        object.__setattr__(self,"build_revision",revision)
        object.__setattr__(self,"generated_by",_token("generated_by",self.generated_by))

        components=tuple(sorted(self.components,key=lambda item:item.component_id))
        if not components:
            raise SBOMError("SBOM requires at least one component")
        ids=[item.component_id for item in components]
        if len(ids)!=len(set(ids)):
            raise SBOMError("component ids must be unique")
        digests={item.digest for item in components}
        object.__setattr__(self,"components",components)

        findings=tuple(sorted(self.findings,key=lambda item:item.finding_id))
        finding_ids=[item.finding_id for item in findings]
        if len(finding_ids)!=len(set(finding_ids)):
            raise SBOMError("finding ids must be unique")
        if any(item.component_digest not in digests for item in findings):
            raise SBOMError("vulnerability finding references unknown component")
        object.__setattr__(self,"findings",findings)

    @property
    def scopes(self) -> tuple[str, ...]:
        return tuple(sorted({item.scope for item in self.components}))

    @property
    def digest(self) -> str:
        return _digest({
            "sbom_id":self.sbom_id,
            "format":self.format,
            "build_artifact_digest":self.build_artifact_digest,
            "build_revision":self.build_revision,
            "components":[item.digest for item in self.components],
            "findings":[item.digest for item in self.findings],
            "generated_by":self.generated_by,
        })

    def require_scope_coverage(self, required: Iterable[str] = _SCOPES) -> None:
        required_set=set(required)
        unknown=required_set-_SCOPES
        if unknown:
            raise SBOMError("unknown required component scope")
        missing=required_set-set(self.scopes)
        if missing:
            raise SBOMError("SBOM missing component scopes: "+",".join(sorted(missing)))
