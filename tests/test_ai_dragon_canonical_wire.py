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


def test_shared_visual_wire_golden_bytes_and_digest():
 import json
 from pathlib import Path
 fixture=json.loads(Path("tests/fixtures/dragon_visual_wire_v1.json").read_text(encoding="utf-8"))
 canonical=json.dumps(fixture,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
 assert canonical.decode()=="{\"consent_id\":\"consent-1\",\"consent_scope_digest\":\""+("a"*64)+"\",\"decoder_version\":\"dragon.local-visual.rgb64x36.v1\",\"frames\":[[\"wire-frame\",\""+("d"*64)+"\",\"125\",\"local-frame://0\"]],\"job_id\":\"job-1\",\"observations\":[[\"wire-frame\",\""+("d"*64)+"\",\"0.125\",\"0\",\"0.0000001\",\"1\"]],\"owner\":\"user-α\",\"recording_digest\":\""+("b"*64)+"\",\"retention_until\":\"1000\",\"schema\":\"dragon.visual-observations.v1\",\"wire\":\"dragon.canonical-decimal.v1\"}"
 assert __import__("hashlib").sha256(canonical).hexdigest()=="e00ec3da67a7785fa438a35df5158f8d84156e0c51805ed8deeef3c030718139"
