"""End-user wiring faults are denied before Docker mutations."""
import pytest

from skeleton.app.compose_wiring import validate_wiring,WiringDenied
from skeleton.testing.compose_wiring_fixtures import fixture_values,populate_wiring
from skeleton.testing.test_compose_storage_binding import model,observe,fixture_runner


@pytest.mark.parametrize("role,key,replacement,code",[
    ("backend","GF_SEAL_SECRET","foreign-secret","compose_private_identity_mismatch"),
    ("skeleton","SKL_ENGINE_SERVICE_TOKEN","foreign-token","compose_private_identity_mismatch"),
    ("mongo","MONGO_INITDB_ROOT_PASSWORD","foreign-password","compose_private_identity_mismatch"),
    ("backend","DB_NAME","other","compose_database_identity_mismatch"),
    ("skeleton","SKL_OPERATION_STATE_PATH","/tmp/operation.sqlite","compose_durable_path_mismatch"),
    ("backend","SKL_DRAGON_KNOWLEDGE_DB_PATH","/tmp/knowledge.sqlite","compose_durable_path_mismatch"),
    ("backend","JEEVES_LOCAL_ONLY","0","compose_local_identity_mismatch"),
    ("skeleton","AI_PROVIDER","hosted","compose_local_inference_policy_mismatch"),
    ("skeleton","AI_LOCAL_GUARD_REQUIRED","0","compose_local_inference_policy_mismatch"),
    ("skeleton","AI_LOCAL_MODEL_PATH","foreign-model","compose_model_selection_mismatch"),
    ("backend","GAMEFORGE_AUTH_ENFORCE","false","compose_application_auth_policy_mismatch"),
    ("backend","SKELETON_INTERNAL_URL","http://remote.invalid:8001","compose_internal_engine_origin_mismatch"),
    ("backend","NO_PROXY","localhost","compose_private_proxy_bypass_missing"),
    ("frontend","EXPO_PUBLIC_BACKEND_URL","http://localhost:9999","compose_browser_api_origin_mismatch"),
    ("backend","PUBLIC_APP_URL","http://foreign.invalid","compose_public_application_origin_mismatch"),
    ("backend","CORS_ORIGINS","*","compose_browser_cors_mismatch"),
    ("frontend","NODE_ENV","production","compose_runtime_mode_mismatch"),
])
def test_resolved_environment_drift_blocks_before_inventory(tmp_path,role,key,replacement,code):
    value=populate_wiring(model(),tmp_path,fixture_values())
    value["services"][role]["environment"][key]=replacement
    runner,calls=fixture_runner(resolved=value)
    report=observe(tmp_path,runner)
    assert not report.admitted and report.code==code
    assert replacement not in report.code
    assert len(calls)==2


@pytest.mark.parametrize("fault",["foreign_build","dockerfile","dependency",
                                  "optional_dependency","frontend_dependency","browser_arg"])
def test_semantic_structure_is_admitted_only_with_canonical_wiring(tmp_path,fault):
    value=populate_wiring(model(),tmp_path,fixture_values())
    services=value["services"]
    if fault=="foreign_build":
        services["backend"]["build"]["context"]=str(tmp_path/"other")
    elif fault=="dockerfile":
        services["backend"]["build"]["dockerfile"]="OtherDockerfile"
    elif fault=="dependency":
        services["backend"]["depends_on"]["mongo"]["condition"]="service_started"
    elif fault=="optional_dependency":
        services["skeleton"]["depends_on"]["mongo"]["required"]=False
    elif fault=="frontend_dependency":
        services["frontend"]["depends_on"]={"backend":{"condition":"service_healthy"}}
    else:
        services["frontend"]["build"]["args"]["EXPO_PUBLIC_BACKEND_URL"]="http://localhost:9000"
    with pytest.raises(WiringDenied):
        validate_wiring(value,root=tmp_path,values=fixture_values())


def test_canonical_service_only_render_admits_without_model_selection(tmp_path):
    value=populate_wiring(model(),tmp_path,fixture_values())
    assert validate_wiring(value,root=tmp_path,values=fixture_values()) is None
