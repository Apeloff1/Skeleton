import unittest
from skeleton.ai.product.resource_scheduler import ProductContractError, ResourceRequest, schedule_resources

class TestResourceScheduler(unittest.TestCase):
    def test_foreground_is_considered_before_background(self):
        bg=ResourceRequest("bg",4,4,100,False,True)
        fg=ResourceRequest("fg",4,4,1,True,False)
        selected=schedule_resources((bg,fg),4,4)
        self.assertEqual([r.task_id for r in selected],["fg"])
        with self.assertRaises(ProductContractError):
            schedule_resources((fg,fg),8,8)

if __name__=="__main__": unittest.main()
