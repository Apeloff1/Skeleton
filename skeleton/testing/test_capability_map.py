from __future__ import annotations
import pytest
from skeleton.ai.capability_map import *
def d(i,m=Maturity.PRODUCTION,deps=()):return CapabilityDescriptor(i,"OWNER.AI",m,deps,("deterministic",))
def test_planned_intent_is_not_advertised_as_live():
 m=CapabilityMap((d("CAP.A",Maturity.PLANNED),),(CapabilityAvailability("CAP.A",Availability.AVAILABLE,""),));assert m.resolve("CAP.A").state is Availability.UNAVAILABLE
def test_missing_live_evidence_is_unavailable():assert CapabilityMap((d("CAP.A"),),()).resolve("CAP.A").state is Availability.UNAVAILABLE
def test_dependency_failure_degrades_parent_without_silent_fallback():
 m=CapabilityMap((d("CAP.A"),d("CAP.B",deps=("CAP.A",))),(CapabilityAvailability("CAP.A",Availability.UNAVAILABLE,"offline"),CapabilityAvailability("CAP.B",Availability.AVAILABLE,"")));assert m.resolve("CAP.B").state is Availability.DEGRADED
 with pytest.raises(CapabilityError,match="guarantee unavailable"):m.require("CAP.B")
def test_all_live_dependencies_allow_capability():
 m=CapabilityMap((d("CAP.A"),d("CAP.B",deps=("CAP.A",))),(CapabilityAvailability("CAP.A",Availability.AVAILABLE,""),CapabilityAvailability("CAP.B",Availability.AVAILABLE,"")));assert m.require("CAP.B").capability_id=="CAP.B"
def test_unknown_dependency_rejected():
 with pytest.raises(CapabilityError,match="unknown capability dependency"):CapabilityMap((d("CAP.B",deps=("CAP.MISSING",)),),())
