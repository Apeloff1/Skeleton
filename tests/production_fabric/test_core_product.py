import unittest
from skeleton.ai.runtime.production_fabric.product.api import LocalAPI
from skeleton.ai.runtime.production_fabric.product.export import export_world, import_world
from skeleton.ai.runtime.production_fabric.product.workspace import Workspace
from skeleton.ai.runtime.production_fabric.product.save import save, validate
from skeleton.ai.runtime.production_fabric.product.branches import fork
from skeleton.ai.runtime.production_fabric.planning.engine import ProductionEngine
from skeleton.ai.runtime.production_fabric.contracts.canonical import loads
from skeleton.ai.runtime.production_fabric.contracts.errors import ConflictError, IntegrityError
from skeleton.ai.runtime.production_fabric.product.content.worlds.cloudbreak_signal import WORLD

class ProductTests(unittest.TestCase):

    def setUp(self):
        self.engine = ProductionEngine(WORLD)

    def tearDown(self):
        self.engine.close()

    def test_json_api_inspect(self):
        result = loads(LocalAPI(self.engine).json(b'{"method":"inspect","session":"a"}'))
        self.assertTrue(result['ok'])
        self.assertEqual(result['result']['state']['revision'], 0)

    def test_json_api_denial(self):
        result = loads(LocalAPI(self.engine).json(b'{"method":"unknown","session":"a"}'))
        self.assertFalse(result['ok'])

    def test_world_portable_digest(self):
        self.assertEqual(import_world(export_world(WORLD))['id'], WORLD['id'])
        raw = export_world(WORLD)
        with self.assertRaises(IntegrityError):
            import_world(raw.replace(b'cloudbreak', b'forgedxxxx'))

    def test_workspace_identity_cas(self):
        workspace = Workspace()
        workspace.admit(WORLD)
        self.assertEqual(len(workspace.inventory()), 1)
        changed = dict(WORLD)
        changed['title'] = 'different'
        with self.assertRaises(ConflictError):
            workspace.admit(changed)

    def test_save_and_fork(self):
        self.engine.play('source', 'first', 'visit_commons', 0)
        receipt = save(self.engine.store, 'source')
        self.assertTrue(validate(self.engine.store, receipt))
        fork(self.engine.store, 'source', 'fork', upto_revision=1)
        self.assertEqual(self.engine.inspect('fork')['state'], self.engine.inspect('source')['state'])
