import pytest
from skeleton.automation.build_lease import acquire
def test_lease_epoch_advances():
 l=acquire(None,owner="run-1",expected_epoch=0,head_sha="a"*40);assert l.epoch==1
def test_stale_epoch_rejected():
 l=acquire(None,owner="run-1",expected_epoch=0,head_sha="a"*40)
 with pytest.raises(ValueError):acquire(l,owner="run-1",expected_epoch=0,head_sha="a"*40)
def test_other_writer_rejected():
 l=acquire(None,owner="run-1",expected_epoch=0,head_sha="a"*40)
 with pytest.raises(ValueError):acquire(l,owner="run-2",expected_epoch=1,head_sha="a"*40)
