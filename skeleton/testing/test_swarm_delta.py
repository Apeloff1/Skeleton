from skeleton.agents.swarm_delta import diff_snapshots


def test_snapshot_delta_tracks_add_remove_change() -> None:
    before = {
        "tasks": [{"id": "a", "state": "queued"}, {"id": "b", "state": "queued"}],
        "workers": [{"id": "w1"}],
    }
    after = {
        "tasks": [{"id": "a", "state": "succeeded"}, {"id": "c", "state": "queued"}],
        "workers": [{"id": "w2"}],
    }
    delta = diff_snapshots(before, after)
    assert delta.added_tasks == ("c",)
    assert delta.removed_tasks == ("b",)
    assert delta.changed_tasks == ("a",)
    assert delta.added_workers == ("w2",)
    assert delta.removed_workers == ("w1",)
