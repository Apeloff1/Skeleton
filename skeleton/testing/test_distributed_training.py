import pytest
from skeleton.learning.distributed_training import *
def test_topology_collective_and_divergence_fail_closed():
 t=TrainingTopology(2,2,1,30); c=DistributedTrainingCoordinator(t); c.join(TrainingWorker("a",0,1,"x"*16)); c.join(TrainingWorker("b",1,1,"y"*16)); c.record_collective(step=1,replica_digest="a"*64,participants=(0,1))
 with pytest.raises(DistributedTrainingError): c.record_collective(step=1,replica_digest="b"*64,participants=(0,1))
 with pytest.raises(DistributedTrainingError): c.record_collective(step=2,replica_digest="c"*64,participants=(0,))
