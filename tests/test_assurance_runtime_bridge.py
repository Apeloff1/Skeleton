from skeleton.kernel.assurance_runtime_bridge import AssuranceRuntimeBridge


class FakeReplay:
    def __init__(self):
        self.calls = []

    def admit(self, **kwargs):
        self.calls.append(kwargs)
        return type("Decision", (), {"accepted": True, "reason": "accepted", "event_key": "x"})()


def test_runtime_bridge_accepts_valid_event():
    replay = FakeReplay()
    bridge = AssuranceRuntimeBridge(None, replay)

    result = bridge.process(
        task_id="task-1",
        evidence_digest="digest",
        state="accepted",
    )

    assert result.accepted
    assert replay.calls[0]["task_id"] == "task-1"


def test_runtime_bridge_rejects_missing_identity():
    bridge = AssuranceRuntimeBridge(None, FakeReplay())
    result = bridge.process(task_id="", evidence_digest="digest", state="accepted")

    assert not result.accepted
