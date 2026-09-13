from skeleton.frontier.gameforge_window import SlidingWindow

def test_window_retains_latest_values():
    w=SlidingWindow(2); w.add(1); w.add(2); w.add(3); assert w.values()==(2,3); assert len(w)==2

def test_window_rejects_zero_capacity():
    try: SlidingWindow(0)
    except ValueError: pass
    else: raise AssertionError("expected ValueError")
