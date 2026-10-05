from __future__ import annotations
import pytest
from skeleton.automation.technical_debt import *
def item():return DebtItem("DEBT.1","legacy serializer",("CONTRACT.STATE",),"OWNER.RUNTIME","replace with canonical codec",DebtImpact(3,4,5))
def receipt():return DebtRetirement("DEBT.1","EVID.MIGRATION","EVID.COMPAT","EVID.ROLLBACK","EVID.VERIFY")
def test_debt_requires_owner_contract_and_disposition():assert item().owner_id=="OWNER.RUNTIME"
def test_interest_combines_operational_engineering_and_risk():assert DebtLedger((item(),)).interest("DEBT.1")==12
def test_retirement_requires_migration_compatibility_rollback_and_verification():assert DebtLedger((item(),)).retire(receipt()).rollback_evidence_id=="EVID.ROLLBACK"
def test_unknown_debt_cannot_be_retired():
 with pytest.raises(DebtError,match="unknown"):DebtLedger((item(),)).retire(DebtRetirement("DEBT.9","EVID.M","EVID.C","EVID.R","EVID.V"))
def test_retired_debt_leaves_active_risk_queue():
 l=DebtLedger((item(),));assert l.active_by_risk();l.retire(receipt());assert l.active_by_risk()==()
def test_debt_cannot_be_retired_twice():
 l=DebtLedger((item(),));l.retire(receipt())
 with pytest.raises(DebtError,match="already"):l.retire(receipt())

def test_debt_impact_rejects_boolean_and_non_integer_interest():
 with pytest.raises(DebtError,match="integers"):DebtImpact(True,1,1)
 with pytest.raises(DebtError,match="integers"):DebtImpact(1,1.5,1)
def test_duplicate_debt_and_contract_identity_rejected():
 with pytest.raises(DebtError,match="duplicate affected contract"):DebtItem("DEBT.2","x",("CONTRACT.X","CONTRACT.X"),"OWNER.X","fix",DebtImpact(1,1,1))
 with pytest.raises(DebtError,match="duplicate debt identity"):DebtLedger((item(),item()))
def test_unknown_interest_query_fails_with_domain_error():
 with pytest.raises(DebtError,match="unknown debt"):DebtLedger((item(),)).interest("DEBT.9")
def test_retirement_receipt_is_runtime_typed():
 with pytest.raises(DebtError,match="receipt must"):DebtLedger((item(),)).retire("DEBT.1")
