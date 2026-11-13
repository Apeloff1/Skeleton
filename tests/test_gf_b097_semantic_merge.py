from skeleton.gameforge.batch_b09x import b097_semantic_merge as m

BASE = {
    "r": {"type": "Node"},
    "h": {"type": "Sprite", "parent": "r", "props": {"x": 0, "y": 0}},
}


def test_independent_field_edits_merge():
    ours = {**BASE, "h": {**BASE["h"], "props": {"x": 5, "y": 0}}}
    theirs = {**BASE, "h": {**BASE["h"], "props": {"x": 0, "y": 7}}}
    merged, c = m.merge_nodes(BASE, ours, theirs)
    assert not c and merged["h"]["props"] == {"x": 5, "y": 7}


def test_irreducible_conflicts():
    ours = {**BASE, "h": {**BASE["h"], "props": {"x": 1, "y": 0}}}
    theirs = {**BASE, "h": {**BASE["h"], "props": {"x": 2, "y": 0}}}
    _, c = m.merge_nodes(BASE, ours, theirs)
    assert c and c[0]["kind"] == "field"


def test_delete_modify_and_orphans():
    ours = {"r": BASE["r"]}
    theirs = {**BASE, "h": {**BASE["h"], "props": {"x": 9, "y": 0}}}
    _, c = m.merge_nodes(BASE, ours, theirs)
    assert c[0]["kind"] == "delete_modify"
    _, c = m.merge_nodes(BASE, {"h": BASE["h"]}, BASE)
    assert {"node": "h", "kind": "orphaned"} in c


def test_add_add_same_merges_and_different_conflicts():
    n = {"type": "Node", "parent": "r"}
    merged, c = m.merge_nodes(BASE, {**BASE, "n": n}, {**BASE, "n": dict(n)})
    assert not c and merged["n"] == n
    _, c = m.merge_nodes(
        BASE, {**BASE, "n": n}, {**BASE, "n": {"type": "UI", "parent": "r"}}
    )
    assert c == [{"node": "n", "kind": "add_add"}]


def test_unchanged_delete_is_clean():
    merged, c = m.merge_nodes(BASE, {"r": BASE["r"]}, BASE)
    assert not c and set(merged) == {"r"}
