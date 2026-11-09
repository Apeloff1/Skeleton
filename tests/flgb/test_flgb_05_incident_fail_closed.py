import unittest
from skeleton.security.incident_fail_closed import IncidentState

class TestIncidentFailClosed(unittest.TestCase):
    def test_high_severity_incident_denies_by_default(self):
        incident=IncidentState("i","critical","open",("write",))
        self.assertFalse(incident.allows("write"))
        self.assertFalse(incident.allows("read"))
        closed=IncidentState("i","critical","closed",("write",))
        self.assertTrue(closed.allows("write"))

if __name__=="__main__": unittest.main()
