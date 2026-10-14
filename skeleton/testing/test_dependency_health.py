from __future__ import annotations
import hashlib,pytest
from skeleton.ai.governance.health import DependencyFinding,DependencyHealthReport,HealthScorecardError
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_dependency_health_binds_sbom_and_backlog():
    finding=DependencyFinding("pkg:a","critical","CVE-X",d("e"),"backlog:CVE-X")
    report=DependencyHealthReport(d("sbom"),(finding,),False,1)
    assert report.healthy is False and report.unresolved_critical==1 and len(report.digest)==64
def test_critical_count_cannot_be_forged():
    finding=DependencyFinding("pkg:a","critical","CVE-X",d("e"),"b")
    with pytest.raises(HealthScorecardError,match="unresolved_critical"):
        DependencyHealthReport(d("s"),(finding,),False,0)
