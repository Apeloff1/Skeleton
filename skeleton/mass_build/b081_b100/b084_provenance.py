"""B084: SBOM + provenance evidence for deps, actions, toolchains and releases."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ._core import digest, require_keys, verdict

SHA_PIN = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sbom(components: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for c in components:
        require_keys(c, ("name", "version", "sha256"), "component")
    comps = sorted(({"name": c["name"], "version": c["version"], "sha256": c["sha256"]} for c in components),
                   key=lambda c: (c["name"], c["version"]))
    return {"format": "skeleton-sbom/1", "components": comps, "digest": digest(comps)}


def attest(artifact_sha256: str, builder: str, sbom_doc: Mapping[str, Any]) -> dict[str, Any]:
    body = {"subject": artifact_sha256, "builder": builder, "sbom": sbom_doc["digest"]}
    return {**body, "statement": digest(body)}


def verify_attestation(att: Mapping[str, Any], sbom_doc: Mapping[str, Any]) -> bool:
    body = {"subject": att.get("subject"), "builder": att.get("builder"), "sbom": att.get("sbom")}
    return att.get("statement") == digest(body) and att.get("sbom") == sbom_doc.get("digest") \
        and sbom_doc.get("digest") == digest(sbom_doc.get("components"))


def evaluate(components, actions: Sequence[str], att, sbom_doc):
    findings = []
    for c in components:
        if not HEX64.match(str(c.get("sha256", ""))):
            findings.append(f"unhashed:{c.get('name')}")
    for a in actions:
        ref = a.rsplit("@", 1)[-1] if "@" in a else ""
        if not SHA_PIN.match(ref):
            findings.append(f"unpinned_action:{a}")
    if not verify_attestation(att, sbom_doc):
        findings.append("attestation_invalid")
    return verdict("B084", findings, components=len(components), actions=len(actions))
