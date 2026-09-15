from skeleton.frontier.gameforge_outbox import BoundedOutbox

def test_outbox_is_hard_bounded():
    q=BoundedOutbox[int](2); assert q.append(1); assert q.append(2); assert not q.append(3); assert len(q)==2

def test_outbox_fifo():
    q=BoundedOutbox[int](2); q.append(1); q.append(2); assert q.pop()==1; assert q.pop()==2; assert q.pop() is None

def test_outbox_rejects_invalid_capacity():
    try: BoundedOutbox(0)
    except ValueError: pass
    else: raise AssertionError("expected ValueError")
