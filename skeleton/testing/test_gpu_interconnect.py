import pytest
from skeleton.runtime.gpu_interconnect import *
def test_collective_requires_measured_paths(): 
 with pytest.raises(ValueError):place_collective(("g0","g1"),(GPUInterconnect("g0","g1",10,False),))
def test_heterogeneous_bandwidth_is_preserved():assert place_collective(("g0","g1"),(GPUInterconnect("g0","g1",7,True),)).evidence[0].bandwidth==7

def test_three_gpu_collective_requires_all_pairwise_measurements():
 import pytest
 links=(GPUInterconnect("a","b",1,True),GPUInterconnect("b","c",1,True))
 with pytest.raises(ValueError):place_collective(("a","b","c"),links)
