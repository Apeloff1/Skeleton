"""Shipping semantic admission for a resolved local Compose application.

Validate credential propagation, local-only inference custody and browser
wiring against the exact operator inputs. Inspect resolved values only in
memory. All failures use constant codes; no value or URI is returned.
This is a configuration contract, not attestation of running process env.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from skeleton.app.assembly import _local_http_origin
from skeleton.app.compose_runtime_identity import HOST_DEFAULTS


class WiringDenied(ValueError):
    pass


def _need(condition, code):
    if condition is not True:
        raise WiringDenied(code)


_SECRET_ROLES = {
    "mongo": ("MONGO_INITDB_ROOT_PASSWORD",),
    "backend": ("MONGO_URL","JWT_SECRET","GAMEFORGE_JWT_SECRET",
                "GF_SEAL_SECRET","GF_KEYHOLDER_SEED","SKL_ENGINE_SERVICE_TOKEN"),
    "skeleton": ("SKL_MONGO_URI","GF_SEAL_SECRET","SKELETON_MASTER_SECRET",
                 "SKL_ENGINE_SERVICE_TOKEN"),
}
_FIXED_PATHS = {
    "backend": {
        "GALAXY_BUILDS_VAULT_DIR":"/app/data/builds_vault",
        "CURIOSITY_DATA_ROOT":"/app/data/curiosity",
        "CHROMA_PERSIST_DIR":"/app/data/chroma",
        "SKL_DRAGON_PRACTICE_DB_PATH":"/app/data/dragon_practice.sqlite",
        "SKL_DRAGON_KNOWLEDGE_DB_PATH":"/app/data/dragon_knowledge.sqlite",
    },
    "skeleton": {
        "SKL_OPERATION_STATE_PATH":"/app/data/operation_state.sqlite",
        "SKL_OPERATION_STREAM_PATH":"/app/data/operation_stream.sqlite",
        "BACKEND_TOOL_RECEIPT_PATH":"/app/data/backend_tool_receipts.sqlite3",
        "BACKEND_TOOL_RESULT_PATH":"/app/data/backend_tool_results.sqlite3",
        "SKL_ENGINE_EXECUTION_STATE_PATH":"/app/data/engine_execution.sqlite",
        "SKL_ENGINE_SUBMISSION_STATE_PATH":"/app/data/engine_submissions.sqlite",
        "SKL_ENGINE_TOOL_RECEIPT_PATH":"/app/data/engine_tool_receipts.sqlite",
        "SKL_ENGINE_QUOTA_STATE_PATH":"/app/data/engine_quota.sqlite",
        "SKL_ENGINE_PRESSURE_STATE_PATH":"/app/data/engine_pressure.sqlite",
        "SKL_GOVERNANCE_LIFECYCLE_PATH":"/app/data/governance_lifecycle.sqlite",
    },
}
_PRIVATE_HOSTS = frozenset({"localhost","127.0.0.1","::1","skeleton","mongo","backend","chroma"})
_MODEL_SELECTION = ("AI_LOCAL_MODEL_PATH","AI_LOCAL_DEPLOYMENT_PATH","AI_LOCAL_MODEL_CATALOG_PATH")


def _selected(values,key,default=""):
    value=values.get(key) or default
    _need(type(value) is str,"compose_input_type_invalid")
    return value


def _env(spec):
    result=spec.get("environment")
    _need(type(result) is dict and len(result)<=512
          and all(type(k) is str and (v is None or type(v) is str) for k,v in result.items()),
          "compose_environment_inventory_invalid")
    return result


def _build(spec, root, context, dockerfile, target=None):
    build=spec.get("build")
    _need(type(build) is dict,"compose_build_missing")
    source=build.get("context")
    _need(type(source) is str and Path(source).is_absolute()
          and Path(source).resolve()==(root/context).resolve(),"compose_build_context_mismatch")
    _need(build.get("dockerfile","Dockerfile")==dockerfile,"compose_build_file_mismatch")
    if target is not None:
        _need(build.get("target")==target,"compose_build_target_mismatch")
    return build


def validate_wiring(model: dict, *, root: Path, values: Mapping[str,str],
                    hot: bool=False) -> None:
    """Reject any semantic mismatch before a Compose mutation is admitted."""
    services=model["services"]
    backend,engine,mongo,frontend=(services[role] for role in ("backend","skeleton","mongo","frontend"))
    envs={role:_env(services[role]) for role in ("backend","skeleton","mongo","frontend")}
    for role,keys in _SECRET_ROLES.items():
        for key in keys:
            expected=_selected(values,key)
            _need(bool(expected) and envs[role].get(key)==expected,
                  "compose_private_identity_mismatch")
    for role,key,default in (
        ("mongo","MONGO_INITDB_ROOT_USERNAME","admin"),
        ("mongo","MONGO_INITDB_DATABASE","tutolage"),
        ("backend","DB_NAME","tutolage"),
    ):
        _need(envs[role].get(key)==_selected(values,key,default),"compose_database_identity_mismatch")
    _need(envs["skeleton"].get("SKL_MONGO_DATABASE")=="skeleton","compose_database_identity_mismatch")
    for role,paths in _FIXED_PATHS.items():
        _need(all(envs[role].get(k)==v for k,v in paths.items()),"compose_durable_path_mismatch")
    for role in ("backend","skeleton"):
        _need(envs[role].get("JEEVES_LOCAL_ONLY")=="1"
              and envs[role].get("JEEVES_PRIMARY_MODEL_ID")==_selected(values,"JEEVES_PRIMARY_MODEL_ID","jeeves")
              and envs[role].get("SKL_ENGINE_SERVICE_PRINCIPAL")==_selected(values,"SKL_ENGINE_SERVICE_PRINCIPAL","codedock-backend"),
              "compose_local_identity_mismatch")
        for key in ("NO_PROXY","no_proxy"):
            raw=envs[role].get(key)
            _need(type(raw) is str and _PRIVATE_HOSTS.issubset({part.strip() for part in raw.split(",")}),
                  "compose_private_proxy_bypass_missing")
    _need(envs["skeleton"].get("AI_PROVIDER")=="local"
          and envs["skeleton"].get("AI_LOCAL_GUARD_REQUIRED")=="1",
          "compose_local_inference_policy_mismatch")
    # Missing model configuration is valid service-only first installation.
    # A set of conflicting model selectors must not claim local AI readiness.
    for key in _MODEL_SELECTION:
        _need(envs["skeleton"].get(key)==_selected(values,key),"compose_model_selection_mismatch")
    _need(envs["backend"].get("GAMEFORGE_AUTH_ENFORCE")=="true",
          "compose_application_auth_policy_mismatch")
    _need(envs["backend"].get("SKELETON_INTERNAL_URL") in {"http://skeleton:8001","http://skeleton:8001/"}
          and envs["backend"].get("SKELETON_INTERNAL_URL")==_selected(values,"SKELETON_INTERNAL_URL","http://skeleton:8001"),
          "compose_internal_engine_origin_mismatch")
    for role,dependencies in (("backend",{"mongo","skeleton"}),("skeleton",{"mongo"})):
        deps=services[role].get("depends_on")
        _need(type(deps) is dict and set(deps)==dependencies
              and all(type(v) is dict and v.get("condition")=="service_healthy"
                      and v.get("required",True) is True for v in deps.values()),
              "compose_dependency_health_mismatch")
    _need(not frontend.get("depends_on"),"compose_frontend_recovery_not_isolated")
    _build(engine,root,".","Dockerfile")
    _build(backend,root,".","backend/Dockerfile",_selected(values,"BUILD_TARGET","development"))
    browser_build=_build(frontend,root,"frontend","Dockerfile",_selected(values,"FRONTEND_BUILD_TARGET","development"))
    args=browser_build.get("args")
    _need(type(args) is dict,"compose_browser_arguments_missing")
    for key,role in (("EXPO_PUBLIC_BACKEND_URL","backend"),("EXPO_PUBLIC_SKELETON_URL","skeleton")):
        port_key,default,_=HOST_DEFAULTS[role]
        port=int(_selected(values,port_key,str(default)))
        expected=_selected(values,key,"http://localhost:"+str(port))
        _need(_local_http_origin(expected,port)
              and envs["frontend"].get(key)==args.get(key)==expected,
              "compose_browser_api_origin_mismatch")
    port=int(_selected(values,"FRONTEND_PORT","3000"))
    public=_selected(values,"PUBLIC_APP_URL","http://localhost:"+str(port))
    _need(_local_http_origin(public,port) and envs["backend"].get("PUBLIC_APP_URL")==public,
          "compose_public_application_origin_mismatch")
    cors=_selected(values,"CORS_ORIGINS","http://localhost:"+str(port)+",http://127.0.0.1:"+str(port))
    _need(envs["backend"].get("CORS_ORIGINS")==cors
          and "http://localhost:"+str(port) in {part.strip() for part in cors.split(",")}
          and "*" not in {part.strip() for part in cors.split(",")},
          "compose_browser_cors_mismatch")
    # Validate mode coherence rather than forcing the backend's independent
    # E2E build target to equal the browser target.
    mode=_selected(values,"FRONTEND_BUILD_TARGET","development")
    _need(mode in {"development","production"} and (not hot or mode=="development")
          and _selected(values,"FRONTEND_CONTAINER_PORT","3000")==("8080" if mode=="production" else "3000"),
          "compose_frontend_mode_mismatch")
    _need(envs["frontend"].get("NODE_ENV")==_selected(values,"NODE_ENV","development")
          and envs["backend"].get("ENVIRONMENT")==_selected(values,"ENVIRONMENT","development")
          and envs["skeleton"].get("SKL_ENVIRONMENT")==_selected(values,"ENVIRONMENT","development"),
          "compose_runtime_mode_mismatch")
