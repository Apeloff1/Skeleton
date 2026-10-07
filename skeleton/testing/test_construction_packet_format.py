from __future__ import annotations
import hashlib,pytest
from skeleton.automation.construction_packet import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def sections():
 return tuple(SectionContent(x,x.value) for x in PacketSection)
def test_complete_packet_is_deterministic_and_diffable():
 a=ConstructionPacket("PACKET.111","AIQ.111",sections());b=ConstructionPacket("PACKET.111","AIQ.111",tuple(reversed(sections())));assert a.digest==b.digest
def test_missing_handoff_context_rejected():
 with pytest.raises(PacketError,match="missing sections"):ConstructionPacket("PACKET.111","AIQ.111",sections()[:-1])
def test_machine_reference_detects_stale_source():
 r=PacketReference("REF.PLAN","machine/ai_master_plan.json",S("old"));ss=list(sections());ss[0]=SectionContent(ss[0].section,"",(r,));p=ConstructionPacket("PACKET.111","AIQ.111",tuple(ss));assert p.validate_references({"machine/ai_master_plan.json":S("new")})==("REF.PLAN",)
def test_exact_machine_reference_is_current():
 r=PacketReference("REF.PLAN","machine/ai_master_plan.json",S("same"));ss=list(sections());ss[0]=SectionContent(ss[0].section,"",(r,));p=ConstructionPacket("PACKET.111","AIQ.111",tuple(ss));assert p.validate_references({"machine/ai_master_plan.json":S("same")})==()
def test_duplicate_section_rejected():
 with pytest.raises(PacketError,match="duplicate"):ConstructionPacket("PACKET.111","AIQ.111",sections()+(sections()[0],))
