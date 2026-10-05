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
