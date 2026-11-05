"""Prove the native model child itself retains global RAM occupancy after parent death."""
from __future__ import annotations
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from skeleton.ai.runtime.operational_ai.model.admission import (
    CapacityBroker,CapacityPolicy,Reservation,AdmissionBusy,
)

class ChildLifetimeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'capacity';self.root.mkdir(mode=0o700)
        self.policy=CapacityPolicy(1,1_000_000_000,268435456)
        self.claim=Reservation('a'*64,'b'*64,'c'*64,300000000)

    def test_parent_exits_but_descendant_retains_kernel_model_lease(self):
        source='''from skeleton.ai.runtime.operational_ai.model.admission import *
import subprocess,sys,os
b=CapacityBroker(sys.argv[1],CapacityPolicy(1,1000000000,268435456))
lease=b.acquire(Reservation('a'*64,'b'*64,'c'*64,300000000),check_headroom=False)
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(6)'],
                       pass_fds=(lease.fd,),start_new_session=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print(child.pid,flush=True)
os._exit(0)
'''
        p=subprocess.run([sys.executable,'-c',source,str(self.root)],
            env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])},
            capture_output=True,text=True,timeout=4)
        self.assertEqual(p.returncode,0,p.stderr)
        pid=int(p.stdout.strip())
        try:
            with CapacityBroker(self.root,self.policy) as broker:
                proof=broker.inspect()
                self.assertEqual(proof['occupied_slots'],1)
                with self.assertRaises(AdmissionBusy):
                    broker.acquire(self.claim,check_headroom=False)
        finally:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
            # The worker may remain a zombie briefly; its fd is already closed.
        until=time.monotonic()+3
        while True:
            with CapacityBroker(self.root,self.policy) as broker:
                if broker.inspect()['occupied_slots']==0:
                    self.assertEqual(broker.inspect()['orphaned_slots'],[0])
                    break
            if time.monotonic()>=until:self.fail('orphaned model lease did not release')
            time.sleep(.02)

    def test_native_child_and_parent_ordered_release(self):
        with CapacityBroker(self.root,self.policy) as broker:
            lease=broker.acquire(self.claim,check_headroom=False)
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.1)'],
                                   pass_fds=(lease.fd,),stdout=subprocess.DEVNULL)
            child.wait(timeout=6)
            lease.close()
            self.assertEqual(broker.inspect()['occupied_slots'],0)
            self.assertEqual(broker.inspect()['orphaned_slots'],[])

if __name__=='__main__':unittest.main()
