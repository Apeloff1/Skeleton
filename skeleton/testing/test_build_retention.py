from skeleton.automation.build_retention import retain
def test_unresolved_never_trimmed():assert any(x["id"]=="open" for x in retain(tuple([{"id":"done","state":"complete"}]*20+[{"id":"open","state":"building"}]),limit=16))
