from skeleton.automation.build_resume import decide
def test_head_change_quarantines():assert decide(saved_head="a",current_head="b",journal_phase=None,receipt_present=False,baseline_matches=True).action=="quarantine"
def test_applied_crash_rolls_back_task():assert decide(saved_head="a",current_head="a",journal_phase="applied",receipt_present=False,baseline_matches=True).action=="rollback_task"
def test_validated_without_receipt_reconciles():assert decide(saved_head="a",current_head="a",journal_phase="validated",receipt_present=False,baseline_matches=True).action=="reconcile_receipt"
