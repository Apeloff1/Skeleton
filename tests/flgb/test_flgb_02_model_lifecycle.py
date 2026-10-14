import unittest
from skeleton.ai.model_runtime.model_lifecycle import ModelLifecycle, ModelRuntimeError
D="a"*64
class TestLifecycle(unittest.TestCase):
    def test_state_machine_and_generation(self):
        state=ModelLifecycle(D).transition("loading").transition("ready").transition("draining").transition("stopped")
        self.assertEqual((state.state,state.generation),("stopped",1))
        state=state.transition("loading")
        self.assertEqual(state.generation,2)
        with self.assertRaises(ModelRuntimeError): state.transition("retired")
if __name__=="__main__": unittest.main()
