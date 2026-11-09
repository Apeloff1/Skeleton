import unittest
from skeleton.ai.agents.worker_leases import WorkerLease
D="a"*64
class TestWorkerLease(unittest.TestCase):
    def test_half_open_validity_and_generation(self):
        lease=WorkerLease("l","w",D,D,10,20)
        self.assertTrue(lease.valid_at(10))
        self.assertFalse(lease.valid_at(20))
        renewed=lease.renew(issued_sequence=20,expires_sequence=30)
        self.assertEqual(renewed.generation,1)
if __name__=="__main__": unittest.main()
