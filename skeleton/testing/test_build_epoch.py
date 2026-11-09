from skeleton.automation.build_epoch import next_epoch
def test_epoch_stable_for_same_authority():
 a=next_epoch(None,generation="g",head_sha="a"*40);assert next_epoch(a,generation="g",head_sha="a"*40)==a
def test_epoch_advances_on_generation():a=next_epoch(None,generation="g",head_sha="a"*40);assert next_epoch(a,generation="h",head_sha="a"*40).number==1
