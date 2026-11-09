"""OpenVEX bounded vulnerability *claim* projection, never a verification result.

A supplier's 'not_affected' assertion is not a security clearance. All claims
remain external unreviewed text without package download, exploit execution,
CVE resolution or source-rights changes.
"""
from __future__ import annotations

from .research_projection import ResearchFormatError, ResearchProjection, project_lines
from .sbom_parsing import load, label, count_rows

OPENVEX_MEDIA_TYPES=frozenset({"application/vnd.openvex+json"})
_STATES=frozenset(("not_affected","affected","fixed","under_investigation"))
_REASON=frozenset((
    "component_not_present","vulnerable_code_not_present",
    "vulnerable_code_not_in_execute_path","vulnerable_code_cannot_be_controlled_by_adversary",
    "inline_mitigations_already_exist",
))


def extract_openvex(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    doc=load(raw,max_chars=max_chars)
    if not isinstance(doc.get("@context"),str) or (
        "openvex.dev" not in doc["@context"] and "openvex" not in doc["@context"].lower()
    ):
        raise ResearchFormatError("OpenVEX source context missing")
    rows=count_rows(doc.get("statements",[]),"OpenVEX statements",256)
    if not rows:
        raise ResearchFormatError("empty OpenVEX statements")
    lines=[
        "Unreviewed supplier vulnerability claims (NOT a verified security verdict)",
        f"Claim statements: {len(rows)}",
    ]
    for index,row in enumerate(rows,1):
        if not isinstance(row,dict):
            raise ResearchFormatError("invalid VEX statement")
        status=row.get("status")
        if status not in _STATES:
            raise ResearchFormatError("unsupported VEX statement status")
        vuln=row.get("vulnerability")
        if not isinstance(vuln,dict):
            raise ResearchFormatError("VEX vulnerability object missing")
        vid=label(vuln.get("name","[unidentified]"),maxlen=160)
        products=count_rows(row.get("products",[]),"OpenVEX products",64)
        if not products:
            raise ResearchFormatError("VEX statement has no subject")
        # Product URIs and identifiers can embed credentials/privileged
        # repository addresses; represent only subject counts, not URI values.
        reason=row.get("status_justification")
        if reason not in _REASON:
            reason="unsubstantiated"
        lines.append(
            f"Claim {index}: vulnerability_label: {vid}; "
            f"supplier_claim: {status}; product_count: {len(products)}; "
            f"claimed_justification: {reason}; independently_verified: False"
        )
    return project_lines(lines,title="OpenVEX unreviewed statements",max_chars=max_chars)
