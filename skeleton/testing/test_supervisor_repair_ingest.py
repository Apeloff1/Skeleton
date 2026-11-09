import pytest
from skeleton.automation.supervisor_repair_ingest import ingest
from skeleton.automation.ci_repair_queue import CIRepairTask
from skeleton.automation.repair_admission import Admission
def test_ingest_requires_admission():
 r=CIRepairTask("r","CI/CD","code_quality","a"*40,1,2,"b"*64,"repair")
 with pytest.raises(ValueError):ingest(r,Admission("r",False,"no"))
def test_ingested_item_is_queued():
 r=CIRepairTask("r","CI/CD","code_quality","a"*40,1,2,"b"*64,"repair");x=ingest(r,Admission("r",True,"ok","canonical-1"));assert x.status=="queued" and x.source_repair_id=="r"
