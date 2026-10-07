import unittest
from skeleton.security.audit_evidence import SecurityPlaneError, append_audit_event
D="a"*64
E="b"*64

class TestAuditEvidence(unittest.TestCase):
    def test_audit_chain_is_append_only(self):
        events=append_audit_event((),actor_id="a",action="read",object_digest=D,outcome="allowed")
        events=append_audit_event(events,actor_id="b",action="write",object_digest=E,outcome="denied")
        self.assertEqual(events[1].prior_event_digest,events[0].digest)
        broken=(events[1],)
        with self.assertRaises(SecurityPlaneError):
            append_audit_event(broken,actor_id="c",action="read",object_digest=D,outcome="allowed")

if __name__=="__main__": unittest.main()
