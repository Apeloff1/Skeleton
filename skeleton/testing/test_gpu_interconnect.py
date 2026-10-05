import pytest
from skeleton.runtime.gpu_interconnect import *
def test_collective_requires_measured_paths(): 
 with pytest.raises(ValueError):place_collective(("g0","g1"),(GPUInterconnect("g0","g1",10,False),))
def test_heterogeneous_bandwidth_is_preserved():assert place_collective(("g0","g1"),(GPUInterconnect("g0","g1",7,True),)).evidence[0].bandwidth==7
