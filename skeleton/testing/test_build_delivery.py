import pytest
from skeleton.automation.build_delivery import DeliveryState
def test_all_authorities_required():
 DeliveryState(True,True,True,True,True).require()
 with pytest.raises(ValueError): DeliveryState(True,True,False,True,True).require()
