"""Explicit application entry point for the local Prood design campaign.

Storage provisioning is intentionally separate from opening the campaign:
an interrupted provisioning must not silently bootstrap missing databases.
This entry point starts no background activity and publishes no external files.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from os import PathLike
import hmac

from skeleton.app.offline_custody import open_work_custody, open_worker_results
from skeleton.frontier.durable_work import DurableWorkJournal
from skeleton.frontier.worker_results import WorkerResultStore
from skeleton.prood.design_contract import DesignRequest
from skeleton.prood.design_campaign import admit_design, collect_package, design_supervisor, progress
from skeleton.prood.native_maze import export_native_maze
from skeleton.prood.recovery_review import review_worker_result


@dataclass(slots=True)
class LocalDesignRuntime:
    journal: DurableWorkJournal
    results: WorkerResultStore
    request: DesignRequest
    supervisor: object

    def admit(self):
        return admit_design(self.journal,self.request)

    def progress(self):
        return progress(self.journal,self.request)

    async def advance(self,*,limit=16):
        return await self.supervisor.dispatch(limit=limit)

    def collect(self):
        return collect_package(self.journal,self.results,self.request)

    def native_source(self,*,variant=1):
        return export_native_maze(self.journal,self.results,self.request,variant=variant)

    def virtual_campaign(self,*,variant=1,scale=None):
        from skeleton.prood.campaign_world import CampaignScale,campaign_from_results
        return campaign_from_results(self.journal,self.results,self.request,variant=variant,
                                     scale=CampaignScale() if scale is None else scale)

    def review_claim(self,work_id):
        return review_worker_result(self.journal,self.results,work_id)


@contextmanager
def open_local_design_runtime(directory: str | PathLike[str], *, scope: str,
                              work_key: bytes, result_key: bytes, recovery_key: bytes,
                              request: DesignRequest, admission, owner: str):
    """Open previously provisioned independent owners, with explicit live admission."""
    keys=(work_key,result_key,recovery_key)
    if any(type(key) is not bytes or len(key)!=32 for key in keys):
        raise ValueError("three independent 256-bit keys required")
    if any(hmac.compare_digest(keys[i],keys[j]) for i,j in ((0,1),(0,2),(1,2))):
        raise ValueError("custody and recovery keys must be separate")
    if type(request) is not DesignRequest:
        raise TypeError("canonical design request required")
    with ExitStack() as stack:
        journal,_=stack.enter_context(open_work_custody(directory,scope=scope,
                                    custody_key=work_key,recovery_key=recovery_key,create=False))
        results=stack.enter_context(open_worker_results(directory,scope=scope,key=result_key,create=False))
        supervisor=design_supervisor(journal,results,request,admission=admission,owner=owner)
        yield LocalDesignRuntime(journal,results,request,supervisor)


@contextmanager
def open_campaign_save(directory: str | PathLike[str], *, campaign, scope: str,
                       key: bytes, create: bool, max_database_bytes: int = 192 << 20):
    """Open distinct private save custody; explicit creation is never a restore."""
    from skeleton.ai.model_runtime.private_sqlite import open_private_sqlite
    from skeleton.prood.campaign_save import CampaignSaveStore
    with open_private_sqlite(directory,filename="prood-campaign-save.db",create=create,
                             max_database_bytes=max_database_bytes) as handle:
        store=CampaignSaveStore(handle.connection,campaign=campaign,scope=scope,key=key,
                                private_handle=handle,initialize=create)
        try:
            yield store
        finally:
            store.close()
