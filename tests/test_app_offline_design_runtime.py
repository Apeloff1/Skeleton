"""Production-shaped private runtime composition with explicit provisioning."""
import os
import pytest
from skeleton.app.offline_custody import open_work_custody, open_worker_results
from skeleton.app.offline_design_runtime import open_local_design_runtime
from skeleton.prood.design_contract import DesignRequest

pytestmark=pytest.mark.skipif(os.name!="posix",reason="private SQLite POSIX boundary")


class Policy:
    def allow(self, work):
        return True


@pytest.mark.asyncio
async def test_app_composition_executes_and_reopens(tmp_path):
    tmp_path.chmod(0o700)
    args=dict(scope="tenant",work_key=b"w"*32,result_key=b"r"*32,recovery_key=b"c"*32,
              request=DesignRequest("sample","Original maze adventure",variants=1),
              admission=Policy(),owner="operator")
    with pytest.raises(OSError):
        with open_local_design_runtime(tmp_path,**args):
            pass
    with open_work_custody(tmp_path,scope="tenant",custody_key=args["work_key"],
                           recovery_key=args["recovery_key"],create=True):
        pass
    with open_worker_results(tmp_path,scope="tenant",key=args["result_key"],create=True):
        pass
    with open_local_design_runtime(tmp_path,**args) as runtime:
        assert runtime.admit().worker_count==6
        for _ in range(6):
            assert len((await runtime.advance()).completed)==1
        source=runtime.native_source()
    with open_local_design_runtime(tmp_path,**args) as runtime:
        assert runtime.progress().succeeded==6
        assert runtime.native_source()==source
        assert (await runtime.advance()).claimed==0
    with pytest.raises(ValueError,match="separate"):
        with open_local_design_runtime(tmp_path,**{**args,"result_key":args["work_key"]}):
            pass
