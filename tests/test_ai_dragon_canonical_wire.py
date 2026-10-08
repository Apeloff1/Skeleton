"""Golden vectors for the Dragon canonical decimal wire."""
from skeleton.ai.webcrawler.dragon_canonical_wire import decimal_wire
import pytest

@pytest.mark.parametrize(("value","expected"),[
 (0.0,"0"),(-0.0,"0"),(1.0,"1"),(.125,"0.125"),(1.25,"1.25"),
 (1000.0,"1000"),(1e-7,"0.0000001"),(1e20,"100000000000000000000"),
])
def test_decimal_wire_vectors(value,expected):
 assert decimal_wire(value)==expected

def test_decimal_wire_rejects_nonfinite():
 for x in (float("nan"),float("inf"),float("-inf")):
  with pytest.raises(ValueError):decimal_wire(x)
