from skeleton.ai.runtime.deferred.workflow_tasks import *
def test_dsl_rejects_version_privilege_and_nul():
 s=WorkflowSource("s",DSLVersion(2,0),"x\x00",("admin",)); codes={d.code for d in validate_source(s,("read",))}
 assert codes=={"DSL_VERSION","DSL_AUTHORITY","DSL_SYNTAX"}
def test_compiler_rejects_missing_capability_and_compensation():
 s=WorkflowSource("s",DSLVersion(1,0),"x",())
 r=compile_workflow(s,(WorkflowLink("n","missing","undo"),),(),())
 assert r.workflow is None and {d.code for d in r.diagnostics}=={"MISSING_CAPABILITY","INVALID_COMPENSATION"}
def test_compiler_rejects_cycle():
 s=WorkflowSource("s",DSLVersion(1,0),"x",())
 r=compile_workflow(s,(WorkflowLink("a","x",None),WorkflowLink("b","x",None)),("x",),(("a","b"),("b","a")))
 assert any(d.code=="CYCLE" for d in r.diagnostics)
def test_compile_identity_is_order_deterministic():
 s=WorkflowSource("s",DSLVersion(1,0),"x",())
 a=compile_workflow(s,(WorkflowLink("b","x",None),WorkflowLink("a","x",None)),("x",),()).workflow
 b=compile_workflow(s,(WorkflowLink("a","x",None),WorkflowLink("b","x",None)),("x",),()).workflow
 assert a.identity==b.identity
def test_binding_stays_pinned_without_explicit_migration():
 a=WorkflowVersion("w",1,"a"); b=WorkflowVersion("w",2,"b"); x=WorkflowBinding("r",a)
 assert rebind(x,b,WorkflowCompatibility(1,2,True),explicit_migration=False)==x
def test_incompatible_explicit_migration_fails():
 try:rebind(WorkflowBinding("r",WorkflowVersion("w",1,"a")),WorkflowVersion("w",2,"b"),WorkflowCompatibility(1,2,False),explicit_migration=True);assert False
 except ValueError:pass
def test_unmigratable_run_pins_or_explicitly_restarts():
 m=WorkflowMigration("m",1,2,(),False)
 assert migrate(m,compatible=False).pinned
 assert migrate(m,compatible=False,terminate_and_restart=True).restarted
def test_irreversible_migration_cannot_claim_rollback():
 try:migrate(WorkflowMigration("m",1,2,(StateMapping("a","b",True),),True),compatible=True);assert False
 except ValueError:pass
def test_unknown_task_is_conservative_generic():
 ps={TaskType.GENERIC:TaskProfile(TaskType.GENERIC,1,("generic",)),TaskType.CODE:TaskProfile(TaskType.CODE,5,("code",),("write",))}
 c=classify("mystery",ps);assert c.task_type is TaskType.GENERIC and c.profile.authority==()
def test_complexity_revision_preserves_calibration():
 e=ComplexityEstimate(1,.5,"cal",(ComplexityFeature("files",2),));r=revise(e,4,.2,"runtime")
 assert r.revised.calibration_id=="cal" and r.runtime_evidence=="runtime"
