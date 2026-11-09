from dataclasses import replace
import pytest
from skeleton.modeling.training import TrainingBudget,StepReceipt,TrainingExecution,TrainingError,BudgetExceeded,ReplayError,StateConflict

D="a"*64
def r(n,t=3,c=2,run=D):
    return StepReceipt(run,n,("%064x"%n),("%064x"%(n+100)),t,c,{"loss":1/n})

def test_deterministic_checkpoint_and_recovery():
    a=TrainingExecution(D,TrainingBudget(4,20,20,4),7)
    a.record_step(r(1)); a.record_step(r(2)); cp=a.checkpoint()
    b=TrainingExecution(D,TrainingBudget(4,20,20,4),7)
    assert b.recover(cp,(r(1),r(2)))==cp.state_digest
    assert b.checkpoint().prior_checkpoint_digest==cp.checkpoint_digest

def test_budget_failure_is_atomic():
    x=TrainingExecution(D,TrainingBudget(2,4,4),1)
    before=x.state_digest
    with pytest.raises(BudgetExceeded): x.record_step(r(1,5,1))
    assert x.state_digest==before and x.next_ordinal==1

def test_rejects_gap_wrong_run_and_tampered_chain():
    x=TrainingExecution(D,TrainingBudget(4,20,20),1)
    with pytest.raises(ReplayError): x.record_step(r(2))
    with pytest.raises(ReplayError): x.record_step(r(1,run="b"*64))
    x.record_step(r(1)); cp=x.checkpoint()
    y=TrainingExecution(D,TrainingBudget(4,20,20),1)
    with pytest.raises(ReplayError): y.recover(cp,(r(1,4,2),))

def test_seed_and_numeric_type_confusion_fail_closed():
    with pytest.raises(TrainingError): TrainingExecution(D,TrainingBudget(1,1,1),True)
    with pytest.raises(TrainingError): TrainingBudget(True,1,1)
    with pytest.raises(TrainingError): StepReceipt(D,1,D,D,True,1,{})

def test_nonfinite_metric_rejected():
    with pytest.raises(TrainingError): StepReceipt(D,1,D,D,1,1,{"loss":float("nan")})

def test_closed_execution_rejects_mutation_and_receipt_is_immutable():
    x=TrainingExecution(D,TrainingBudget(2,10,10),1); receipt=r(1); x.record_step(receipt)
    final=x.close()
    assert len(final)==64
    with pytest.raises(StateConflict): x.record_step(r(2))
    with pytest.raises(TypeError): receipt.metrics["loss"]=0.0

def test_checkpoint_budget_is_bounded():
    x=TrainingExecution(D,TrainingBudget(2,10,10,1),1); x.checkpoint()
    with pytest.raises(BudgetExceeded): x.checkpoint()

def test_recovery_requires_pristine_execution():
    x=TrainingExecution(D,TrainingBudget(2,10,10),1); x.record_step(r(1)); cp=x.checkpoint()
    with pytest.raises(StateConflict): x.recover(cp,(r(1),))

def test_mirror_parity():
    from pathlib import Path
    root=Path(__file__).parents[2]
    assert (root/"skeleton/modeling/training.py").read_bytes()==(root/"skeleton/ai/modeling/training.py").read_bytes()
