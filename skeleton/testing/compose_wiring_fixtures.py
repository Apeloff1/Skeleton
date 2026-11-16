"""Synthetic render fixtures for wiring/unit checks only."""
from skeleton.app.compose_wiring import _SECRET_ROLES,_FIXED_PATHS


def fixture_values():
    keys={key for group in _SECRET_ROLES.values() for key in group}
    return {"DOCKER_CONTEXT":"fixture-context",**{k:"fixture-"+k.lower() for k in keys}}


def populate_wiring(model,root,values):
    services=model["services"]
    # Preserve deliberate test overrides rather than replacing a fault.
    for role,keys in _SECRET_ROLES.items():
        spec=services[role]
        env=spec.setdefault("environment",{})
        for key in keys:
            env.setdefault(key,values[key])
    for role,paths in _FIXED_PATHS.items():
        env=services[role]["environment"]
        for key,value in paths.items():
            env.setdefault(key,value)
        env.update({k:env.get(k,v) for k,v in {
            "JEEVES_LOCAL_ONLY":"1","JEEVES_PRIMARY_MODEL_ID":"jeeves",
            "SKL_ENGINE_SERVICE_PRINCIPAL":"codedock-backend",
            "NO_PROXY":"localhost,127.0.0.1,::1,skeleton,mongo,backend,chroma",
            "no_proxy":"localhost,127.0.0.1,::1,skeleton,mongo,backend,chroma",
        }.items()})
        spec=services[role]
        spec.setdefault("read_only",True)
        spec.setdefault("cap_drop",["ALL"])
        spec.setdefault("security_opt",["no-new-privileges:true"])
    engine=services["skeleton"]["environment"]
    backend=services["backend"]["environment"]
    mongo=services["mongo"]["environment"]
    browser=services["frontend"].setdefault("environment",{})
    for env,items in (
        (engine,{"AI_PROVIDER":"local","AI_LOCAL_GUARD_REQUIRED":"1","SKL_MONGO_DATABASE":"skeleton",
                 "AI_LOCAL_MODEL_PATH":"","AI_LOCAL_DEPLOYMENT_PATH":"","AI_LOCAL_MODEL_CATALOG_PATH":"",
                 "SKL_ENVIRONMENT":"development"}),
        (backend,{"DB_NAME":"tutolage","GAMEFORGE_AUTH_ENFORCE":"true","ENVIRONMENT":"development",
                  "SKELETON_INTERNAL_URL":"http://skeleton:8001","PUBLIC_APP_URL":"http://localhost:3000",
                  "CORS_ORIGINS":"http://localhost:3000,http://127.0.0.1:3000"}),
        (mongo,{"MONGO_INITDB_ROOT_USERNAME":"admin","MONGO_INITDB_DATABASE":"tutolage"}),
        (browser,{"EXPO_PUBLIC_BACKEND_URL":"http://localhost:8001",
                  "EXPO_PUBLIC_SKELETON_URL":"http://localhost:8010","NODE_ENV":"development"}),
    ):
        for key,value in items.items():
            env.setdefault(key,value)
    for role,dependencies in (("backend",("mongo","skeleton")),("skeleton",("mongo",))):
        services[role].setdefault("depends_on",{d:{"condition":"service_healthy"} for d in dependencies})
    services["skeleton"].setdefault("build",{"context":str(root),"dockerfile":"Dockerfile"})
    services["backend"].setdefault("build",{"context":str(root),"dockerfile":"backend/Dockerfile","target":"development"})
    services["frontend"].setdefault("build",{"context":str(root/"frontend"),"target":"development",
        "args":{k:browser[k] for k in ("EXPO_PUBLIC_BACKEND_URL","EXPO_PUBLIC_SKELETON_URL")}})
    return model
