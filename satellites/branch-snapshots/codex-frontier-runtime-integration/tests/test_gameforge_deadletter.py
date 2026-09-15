from skeleton.frontier.gameforge_deadletter import DeadLetterQueue

def test_deadletter_is_bounded_and_fifo():
    q=DeadLetterQueue(2); assert q.push("a"); assert q.push("b"); assert not q.push("c"); assert q.drain()==["a","b"]; assert len(q)==0

def test_deadletter_rejects_invalid_capacity():
    try: DeadLetterQueue(0)
    except ValueError: pass
    else: raise AssertionError("expected ValueError")
