from skeleton.learning.training_control import *
def test_admission_state_and_checkpoint_bounds():
 c=TrainingConfig("r","a"*64,"b"*64,"c"*64,"d"*64,10,5); p=TrainingControlPlane(); p.register(c); assert not p.admit("r",cpu=1,memory_mb=256,accelerator_count=0,budget_units=4).admitted; assert p.admit("r",cpu=1,memory_mb=256,accelerator_count=0,budget_units=5).admitted; p.start("r"); s=p.checkpoint("r",step=3,digest="e"*64); assert s.step==3
