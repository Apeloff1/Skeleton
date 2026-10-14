"""Deterministic regional privacy-policy mapping."""
from dataclasses import dataclass
from .data_lifecycle import LifecycleError
@dataclass(frozen=True,slots=True)
class RegionalPrivacyPolicy:
 region:str;framework:str;requires_erasure:bool;requires_export:bool;transfer_restricted:bool
_POLICIES={
 "EEA":RegionalPrivacyPolicy("EEA","GDPR",True,True,True),
 "UK":RegionalPrivacyPolicy("UK","UK-GDPR",True,True,True),
 "US-CA":RegionalPrivacyPolicy("US-CA","CCPA-CPRA",True,True,True),
 "GLOBAL":RegionalPrivacyPolicy("GLOBAL","baseline",True,True,True),
}
def policy_for_region(region:str)->RegionalPrivacyPolicy:
 if not isinstance(region,str) or not region.strip():raise LifecycleError("region required")
 key=region.strip().upper()
 try:return _POLICIES[key]
 except KeyError:raise LifecycleError("unmapped privacy region")
def registered_regions()->tuple[str,...]:return tuple(sorted(_POLICIES))
