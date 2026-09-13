from skeleton.frontier.gameforge_watermark import Watermark

def test_watermark_only_moves_forward():
    w=Watermark(); w.observe(4); w.observe(2); assert w.value==4

def test_watermark_rejects_negative_observation():
    try: Watermark().observe(-1)
    except ValueError: pass
    else: raise AssertionError("expected ValueError")
