from __future__ import annotations
import pytest
from skeleton.training.distributed import *
def topo():return TrainingTopology("TOPO.1",(TrainingWorker("WORKER.A",0,3),TrainingWorker("WORKER.B",1,3)),5)
def test_collective_completes_only_all_current_epoch_ranks():assert CollectiveCoordinator(topo()).evaluate(CollectiveState("COLL.1","TOPO.1",3,0,frozenset({0,1})),1)=="complete"
def test_collective_has_explicit_timeout():assert CollectiveCoordinator(topo()).evaluate(CollectiveState("COLL.1","TOPO.1",3,0,frozenset({0})),5)=="timeout"
def test_stale_epoch_worker_cannot_contribute():
 with pytest.raises(DistributedTrainingError,match="stale"):CollectiveCoordinator(topo()).evaluate(CollectiveState("COLL.1","TOPO.1",2,0,frozenset({0,1})),1)
def test_unknown_rank_rejected():
 with pytest.raises(DistributedTrainingError,match="unknown"):CollectiveCoordinator(topo()).evaluate(CollectiveState("COLL.1","TOPO.1",3,0,frozenset({0,2})),1)
def test_topology_rejects_rank_gaps_and_mixed_epochs():
 with pytest.raises(DistributedTrainingError,match="contiguous"):TrainingTopology("TOPO.1",(TrainingWorker("WORKER.A",0,1),TrainingWorker("WORKER.B",2,1)),5)
 with pytest.raises(DistributedTrainingError,match="mixed"):TrainingTopology("TOPO.1",(TrainingWorker("WORKER.A",0,1),TrainingWorker("WORKER.B",1,2)),5)
