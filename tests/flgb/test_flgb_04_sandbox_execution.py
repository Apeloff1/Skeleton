import unittest
from skeleton.ai.agents.flgb_agent_runtime import digest_json
from skeleton.ai.agents.authority_subset import AuthorityGrant
from skeleton.ai.agents.sandbox_execution import AgentContractError, SandboxExecutionRequest, SandboxPolicy, authorize_sandbox_request
from skeleton.ai.agents.tool_registry import ToolDescriptor
D="a"*64
class TestSandboxExecution(unittest.TestCase):
    def test_authority_and_policy_intersection(self):
        tool=ToolDescriptor("search","v1",D,("net.read",),"read",True,False)
        authority=AuthorityGrant("worker",("net.read",))
        policy=SandboxPolicy("s",("net.read",),1,1024,1000,"allowlisted-read")
        pd=digest_json({"sandbox_id":"s","allowed_capabilities":["net.read"],"cpu_units":1,"memory_bytes":1024,"wall_time_ms":1000,"network_mode":"allowlisted-read"})
        req=SandboxExecutionRequest("op","search","v1",D,("net.read",),authority.digest,pd)
        self.assertEqual(len(authorize_sandbox_request(req,tool=tool,authority=authority,policy=policy)),64)
        bad=SandboxExecutionRequest("op","search","v1",D,(),authority.digest,pd)
        with self.assertRaises(AgentContractError):
            authorize_sandbox_request(bad,tool=tool,authority=authority,policy=policy)
if __name__=="__main__": unittest.main()
