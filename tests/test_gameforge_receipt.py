from skeleton.frontier.gameforge_receipt import Receipt

def test_receipt_is_observable_and_immutable():
 r=Receipt("r1","accept","ready"); assert r.accepted(); assert r.request_id=="r1"
