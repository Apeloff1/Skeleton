"""Independent tool authority and strict schema tests; no model privilege delegation."""
from __future__ import annotations
from dataclasses import replace
import time,unittest
from skeleton.ai.runtime.operational_ai.tools.secure.spec import ToolSpec,ToolArgument,ToolInvocation,ToolError
from skeleton.ai.runtime.operational_ai.tools.secure.registry import SecureRegistry
from skeleton.ai.runtime.operational_ai.tools.secure.policy import ToolPolicy
from skeleton.ai.runtime.operational_ai.tools.secure.engine import SecureToolEngine
from skeleton.ai.runtime.operational_ai.tools.secure.builtin import build_readonly_catalog
from skeleton.ai.runtime.operational_ai.tools.secure.replay import ReceiptLedger

class TestSecureTools(unittest.TestCase):
    def setUp(self):
        self.catalog=build_readonly_catalog()
        self.spec=next(s for s in self.catalog._specs.values() if s.name=='sha256_text')
        self.policy=ToolPolicy(b'k'*32)
        self.inv=ToolInvocation('tenant','user','session','call1','sha256_text',self.spec.digest,{'text':'hello'})
        self.grant=self.policy.mint(self.inv,expires_ns=time.time_ns()+1_000_000_000,nonce='a'*16)

    def test_explicit_grant_executes_and_replays(self):
        engine=SecureToolEngine(self.catalog,self.policy)
        first=engine.execute(self.inv,self.grant)
        self.assertEqual(first.state,'succeeded')
        self.assertEqual(engine.execute(self.inv,self.grant),first)
        self.assertEqual(len(first.output['sha256']),64)

    def test_changed_request_rejected(self):
        engine=SecureToolEngine(self.catalog,self.policy)
        engine.execute(self.inv,self.grant)
        with self.assertRaises(ToolError):engine.execute(replace(self.inv,arguments={'text':'changed'}),self.grant)

    def test_wrong_scope_refused(self):
        self.assertFalse(self.policy.check(self.spec,replace(self.inv,tenant='other'),self.grant).admitted)

    def test_tampered_grant_refused(self):
        self.assertFalse(self.policy.check(self.spec,self.inv,replace(self.grant,signature='0'*64)).admitted)

    def test_schema_blocks_coercion(self):
        from skeleton.ai.runtime.operational_ai.tools.secure.arguments import validate_arguments
        for arg in (None,True,42,[],{},b'bytes'):
            with self.subTest(arg=arg),self.assertRaises(ToolError):
                validate_arguments(self.spec,{'text':arg})
        with self.assertRaises(ToolError):
            validate_arguments(self.spec,{'text':'hi','unexpected':'extra'})

    def test_registry_freeze_is_immutable(self):
        with self.assertRaises(ToolError):
            self.catalog.register(self.spec,lambda _: {})

    def test_explicit_risk_ceiling(self):
        spec=ToolSpec('write_file',1,(),risk='write',scope='operator')
        inv=ToolInvocation('tenant','user','session','write','write_file',spec.digest,{})
        grant=self.policy.mint(inv,expires_ns=time.time_ns()+1000000000,nonce='b'*16)
        self.assertFalse(self.policy.check(spec,inv,grant).admitted)

    def test_receipt_ledger(self):
        from skeleton.ai.runtime.operational_ai.tools.secure.replay import ReceiptLedger
        ledger=ReceiptLedger()
        receipt=SecureToolEngine(self.catalog,self.policy).execute(self.inv,self.grant)
        self.assertTrue(ledger.admit(('tenant','user','session'),receipt))
        self.assertFalse(ledger.admit(('tenant','user','session'),receipt))

if __name__=='__main__':unittest.main()
