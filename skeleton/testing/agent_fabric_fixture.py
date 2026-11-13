"""Real SQLite transactional fixture and explicitly fixture-only model ports."""
from __future__ import annotations
from contextlib import contextmanager
from hashlib import sha256
import sqlite3
from skeleton.ai.runtime.operational_ai.agent_fabric.core.identity import Identity
from skeleton.ai.runtime.operational_ai.agent_fabric.custody.store import AgentStore
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.spec import Plan,Step
from skeleton.ai.runtime.operational_ai.agent_fabric.execution.ports import Ports
from skeleton.ai.runtime.operational_ai.agent_fabric.execution.engine import AgentFabric
MODEL='a'*64
class Database:
    def __init__(self):
        self.db=sqlite3.connect(':memory:',isolation_level=None)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA trusted_schema=OFF')
        self.db.execute('PRAGMA synchronous=FULL')
    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield self.db;self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise
    @contextmanager
    def snapshot(self):
        self.db.execute('BEGIN')
        try:yield self.db
        finally:self.db.execute('ROLLBACK')
    def close(self):self.db.close()
class Model:
    def __init__(self):self.calls=0;self.fail=False
    def complete(self,*,session,request_id,prompt,seed=0,temperature=.8):
        self.calls+=1
        if self.fail:raise RuntimeError('simulated model interruption')
        return {'schema':'fixture-model-not-real-inference',
                'model_sha256':MODEL,'tokenizer_sha256':MODEL,
                'output_sha256':sha256(prompt.encode()).hexdigest()}
class Tool:
    def __init__(self):self.calls=0
    def execute(self,resource,operation,arguments):
        self.calls+=1
        return {'result':'operator-side-effect-fixture','resource':resource,'args':arguments}
class Reader:
    def read(self,*,instruction,owner):
        return {'sha256':sha256((owner+instruction).encode()).hexdigest()}
class Reviewer:
    def __init__(self,approved=False):self.approved=approved
    def request_approval(self,plan_id,step_id,instruction):return {'approved':self.approved}
def prepare(*,steps=None):
    db=Database();identity=Identity('tenant','operator',MODEL,MODEL)
    store=AgentStore(db,identity);model=Model();tool=Tool()
    ports=Ports(model=model,tool=tool,reader=Reader(),reviewer=Reviewer(),operator_key=b'k'*32)
    fabric=AgentFabric(store,ports)
    if steps is None:steps=(Step('first','model','Explain offline inference'),)
    plan=Plan('plan_1','session_1',tuple(steps),'A real AI workflow contract')
    fabric.submit(plan)
    return db,store,fabric,plan,model,tool
