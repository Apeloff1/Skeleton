"""Bounded first-install runtime acceptance, not inference or release certification.

The installer and operator CLI use the already-running application contract.
No API token, model, synthetic provider, mutation, container recreation or
arbitrary endpoint is admitted here. Only redacted verdicts leave the worker.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from skeleton.app.assembly import find_repo_root, load_manifest, runtime_manifest
from skeleton.app.bootstrap import public_bootstrap_payload
from skeleton.app.setup_runtime import runtime_source_fingerprint

SCHEMA = "skeleton.application.strict_install_observation.v1"
_REQUIRED_CHECKS = ("mongo", "vault_galaxy", "vault_builds", "critical_routes")
_CODES = frozenset(("observed", "endpoint_unreachable", "http_status", "invalid_protocol",
                    "identity_mismatch", "unqualified", "deadline_exceeded", "worker_unavailable"))
_SHA = re.compile(r"[a-f0-9]{40}\Z", re.ASCII)
_HEX = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_MAX_PACKET = 512 * 1024
_MAX_RECEIPT = 32 * 1024
_MAX_PASSES = 4
_MAX_INDEX_BYTES = 64 * 1024 * 1024
_MAX_SOURCE_PATH_BYTES = 32768
_WORKER_SOURCE_PATHS = ("skeleton/app", "skeleton/__init__.py", "skeleton.py",
                        "sitecustomize.py", "usercustomize.py")
_PROVIDERS = frozenset(("local", "openai"))
_LANES = ("frontend_setup", "frontend_product", "backend_bootstrap", "backend_health",
          "engine_health", "aggregate_ready", "aggregate_status", "critical_routes",
          "provider_readiness")


class QualificationDenied(RuntimeError):
    """A strict install observation could not establish its required scope."""


def _require(condition):
    if condition is not True:
        raise QualificationDenied("strict install acceptance denied")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _constant(_):
    raise QualificationDenied("nonfinite runtime response")


def _numeric_float(value):
    value = float(value)
    _require(math.isfinite(value))
    return value


def _decode(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= _MAX_PACKET)
    obj = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique,
                     parse_constant=_constant, parse_float=_numeric_float)
    _require(type(obj) is dict)
    return obj


def _digest(value):
    return type(value) is str and _HEX.fullmatch(value) is not None and value != "0"*64


def _base(value):
    _require(type(value) is str and 0 < len(value) <= 256
             and not any(ord(c) <= 32 or ord(c) >= 127 for c in value)
             and not any(c in value for c in ("?", "#", "%", chr(92))))
    parts = urlsplit(value)
    _require(parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")
             and parts.username is None and parts.password is None
             and parts.path in ("", "/") and not parts.query and not parts.fragment
             and parts.port is not None and 1 <= parts.port <= 65535)
    # Do not let DNS, hosts-file overrides, proxy or redirect targets select
    # another endpoint. The Host header remains the declared local origin.
    return ("127.0.0.1" if parts.hostname == "localhost" else parts.hostname,
            parts.port, parts.netloc)


def _get(base, path, *, timeout, html=False):
    host, port, authority = _base(base)
    _require(type(path) is str and 1 <= len(path) <= 512
             and re.fullmatch(r"/[A-Za-z0-9_/-]+", path) is not None
             and "//" not in path)
    _require(type(timeout) in (float, int) and math.isfinite(timeout)
             and 0 < timeout <= 10 and type(html) is bool)
    connection = http.client.HTTPConnection(host, port=port, timeout=timeout)
    cap = 65536 if html else _MAX_PACKET
    try:
        connection.request("GET", path, headers={"Host": authority, "Accept": "text/html" if html else "application/json",
            "Accept-Encoding": "identity", "Connection": "close", "User-Agent": "skeleton-install-qualification/1"})
        response = connection.getresponse()
        if response.status != 200:
            return "http_status", None
        content_types = response.headers.get_all("Content-Type") or []
        lengths = response.headers.get_all("Content-Length") or []
        encodings = response.headers.get_all("Content-Encoding") or []
        transfers = response.headers.get_all("Transfer-Encoding") or []
        _require(len(content_types) == 1 and len(lengths) <= 1 and len(encodings) <= 1
                 and len(transfers) <= 1 and not (lengths and transfers))
        _require(not encodings or encodings[0].strip().lower() == "identity")
        _require(not transfers or transfers[0].strip().lower() == "chunked")
        if lengths:
            _require(re.fullmatch(r"[0-9]{1,8}", lengths[0]) is not None)
            length = int(lengths[0])
            if not html:
                _require(0 < length <= cap)
        mime = content_types[0].split(";", 1)[0].strip().lower()
        _require(mime == ("text/html" if html else "application/json"))
        if html:
            # HTML presence is intentionally not a JS/browser or UI identity
            # assertion. A static SPA shell alone cannot prove functionality.
            sample = response.read(4096)
            _require(re.match(rb"\s*<!doctype\s+html\s*>", sample, re.IGNORECASE) is not None)
            return "observed", None
        data = response.read(cap + 1)
        _require(0 < len(data) <= cap)
        if lengths:
            _require(len(data) == int(lengths[0]))
        return "observed", _decode(data)
    except (OSError, TimeoutError, http.client.HTTPException):
        return "endpoint_unreachable", None
    except (QualificationDenied, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return "invalid_protocol", None
    finally:
        connection.close()


@dataclass(frozen=True, slots=True)
class Lane:
    name: str
    ok: bool
    code: str
    facts: dict

    def __post_init__(self):
        _require(self.name in _LANES and type(self.ok) is bool and self.code in _CODES
                 and self.ok == (self.code == "observed") and type(self.facts) is dict)

    def document(self):
        return {"name": self.name, "ok": self.ok, "code": self.code, "facts": self.facts}


def _identity(actual, expected):
    return type(actual) is dict and all(
        type(actual.get(key)) is type(value) and actual[key] == value
        for key, value in expected.items()
    )


def _same_json(actual, expected):
    # Python bool == 1 is not equivalence for public contracts.
    return _canonical(actual) == _canonical(expected)


def _component(bootstrap, service, prefix):
    identity = bootstrap["application"]
    return {"name": identity["name"], "version": identity["version"],
            "component": service, "ingress_prefix": prefix}


def _writer_facts(check):
    if type(check) is not dict:
        return None
    required, ok = check.get("required"), check.get("ok")
    observed = check.get("known_local_writer_binding_observed")
    if (type(required) is not bool or type(ok) is not bool or type(observed) is not bool
            or check.get("external_writer_coverage_verified") is not False
            or check.get("guarded_local_ai_ready") is not False):
        return None
    code = check.get("code")
    if required and ok:
        if code != "protected_writer_binding_observed" or observed is not True:
            return None
        return {"writer_mode": "protected_observed"}
    if not required and ok:
        if code != "legacy_writer_mode_unqualified" or observed is not False:
            return None
        return {"writer_mode": "legacy_unqualified"}
    if required and not ok and not observed and code in (
        "protected_writer_authority_unavailable", "protected_writer_observation_pending"
    ):
        return {"writer_mode": "protected_unavailable"}
    return None


def _backend(value, expected):
    if not _identity(value.get("canonical_application"), expected):
        return "identity_mismatch", {}
    checks = value.get("checks")
    if type(checks) is not dict or len(checks) > 64:
        return "invalid_protocol", {}
    facts = _writer_facts(checks.get("canonical_writer_custody"))
    if facts is None:
        return "invalid_protocol", {}
    if value.get("status") != "ready" or facts["writer_mode"] == "protected_unavailable":
        return "unqualified", facts
    for name in _REQUIRED_CHECKS:
        if type(checks.get(name)) is not dict or checks[name].get("ok") is not True:
            return "unqualified", facts
    return "observed", facts


def _aggregate(value, bootstrap, engine_expected):
    if (not _same_json(value.get("application"), bootstrap["application"])
            or not _same_json(value.get("contract"), bootstrap["contract"])
            or value.get("scope") != "public-runtime"):
        return "identity_mismatch", {}
    rows = value.get("services")
    if type(rows) is not list or len(rows) != 3:
        return "invalid_protocol", {}
    if not all(type(row) is dict and type(row.get("name")) is str for row in rows):
        return "invalid_protocol", {}
    indexed = {row["name"]: row for row in rows}
    if set(indexed) != {"backend", "skeleton", "mongo"}:
        return "invalid_protocol", {}
    if not _identity(indexed["skeleton"].get("application"), engine_expected):
        return "identity_mismatch", {}
    if value.get("ok") is not True or any(row.get("ok") is not True or
            type(row.get("status")) is not int or row["status"] != 200 for row in rows):
        return "unqualified", {}
    product = value.get("product")
    if type(product) is not dict or product.get("available") is not True:
        return "unqualified", {}
    for key in ("canonical_actions", "ready_actions", "governed_unbound", "unsafe_actions", "policy_gaps"):
        if type(product.get(key)) is not int or not 0 <= product[key] <= 1_000_000:
            return "invalid_protocol", {}
    if (product["canonical_actions"] == 0 or product["ready_actions"] > product["canonical_actions"]
            or product["governed_unbound"] > product["canonical_actions"]
            or product["unsafe_actions"] != 0 or product["policy_gaps"] != 0
            or not _digest(product.get("attestation_sha256"))):
        return "unqualified", {}
    return "observed", {"product_attestation_sha256": product["attestation_sha256"],
                        "canonical_actions": product["canonical_actions"],
                        "ready_actions": product["ready_actions"],
                        "governed_unbound": product["governed_unbound"]}


def _routes(value):
    from skeleton.app.first_install import critical_route_evidence

    observed, ready, missing = critical_route_evidence(value)
    if not observed:
        return "invalid_protocol", {}
    if not ready:
        return "unqualified", {"missing_count": len(missing)}
    return "observed", {"missing_count": 0}


def _provider(value, selected):
    providers = value.get("providers")
    if (value.get("engine") != "skeleton-engine" or type(providers) is not list
            or len(providers) > 32 or not all(type(p) is str and 0 < len(p) <= 64 for p in providers)
            or len(set(providers)) != len(providers)
            or type(value.get("llm_available")) is not bool):
        return "invalid_protocol", {}
    if (selected not in _PROVIDERS or value.get("active") != selected or selected not in providers
            or value.get("availability_observed") is not True or value["llm_available"] is not True):
        return "unqualified", {"provider_available": False}
    return "observed", {"provider_available": True, "selected_provider": selected}


def _lane(name, base, path, timeout, validator=None):
    try:
        code, payload = _get(base, path, timeout=timeout, html=validator is None)
        facts = {}
        if code == "observed" and validator is not None:
            code, facts = validator(payload)
        return Lane(name, code == "observed", code, facts)
    except (QualificationDenied, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return Lane(name, False, "invalid_protocol", {})


def _worker(args):
    _require(type(args) is dict and set(args) == {"bases", "bootstrap", "timeout", "selected_provider"})
    bases, expected = args["bases"], args["bootstrap"]
    _require(type(bases) is dict and set(bases) == {"frontend", "backend", "skeleton"})
    for base in bases.values():
        _base(base)
    timeout = args["timeout"]
    _require(type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 10)
    backend = _component(expected, "backend", "/api")
    engine = _component(expected, "engine", "/api/v1")
    def bootstrap_check(value):
        return ("observed", {}) if _same_json(value, expected) else ("identity_mismatch", {})
    def engine_check(value):
        if not _identity(value.get("application"), engine):
            return "identity_mismatch", {}
        return ("observed", {}) if value.get("alive") is True else ("unqualified", {})
    tasks = (
        ("frontend_setup", "frontend", "/setup", None),
        ("frontend_product", "frontend", "/product", None),
        ("backend_bootstrap", "backend", expected["contract"]["bootstrap"], bootstrap_check),
        ("backend_health", "backend", "/api/health/ready", lambda v: _backend(v, backend)),
        ("engine_health", "skeleton", "/api/v1/health/live", engine_check),
        ("aggregate_ready", "backend", expected["contract"]["ready"], lambda v: _aggregate(v, expected, engine)),
        ("aggregate_status", "backend", expected["contract"]["status"], lambda v: _aggregate(v, expected, engine)),
        ("critical_routes", "backend", "/api/health/registry", _routes),
        ("provider_readiness", "backend", "/api/ai/providers", lambda v: _provider(v, args["selected_provider"])),
    )
    # Bounded isolated process owns the threads; parent enforces hard
    # wall-clock limit even against drip-fed loopback HTTP.
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_lane, name, bases[service], path, timeout, validator)
                   for name, service, path, validator in tasks]
        return [future.result().document() for future in futures]


def _worker_entry():
    try:
        raw = sys.stdin.buffer.read(_MAX_RECEIPT + 1)
        _require(len(raw) <= _MAX_RECEIPT)
        print(json.dumps(_worker(_decode(raw)), separators=(",", ":"), allow_nan=False))
        return 0
    except Exception:
        # No remote payload, URL or secret may escape a worker error.
        return 2


def _validate_worker_result(raw, *, selected=None):
    """Check exact fact schemas and their relationship to each lane verdict.

    A positive worker flag is not authority when mandatory facts are absent,
    contradictory, or belong to another configured provider.
    """
    _require(type(raw) is list and len(raw) == len(_LANES))
    result = []
    for name, item in zip(_LANES, raw, strict=True):
        _require(type(item) is dict and set(item) == {"name", "ok", "code", "facts"}
                 and item["name"] == name)
        lane = Lane(**item)
        facts = lane.facts
        if name == "backend_health":
            if lane.ok:
                _require(set(facts) == {"writer_mode"} and facts["writer_mode"] in
                         ("protected_observed", "legacy_unqualified"))
            else:
                _require(not facts or (lane.code == "unqualified" and set(facts) == {"writer_mode"}
                         and facts["writer_mode"] in ("protected_observed", "legacy_unqualified",
                                                      "protected_unavailable")))
        elif name in ("aggregate_ready", "aggregate_status"):
            if lane.ok:
                _require(set(facts) == {"product_attestation_sha256","canonical_actions",
                                        "ready_actions","governed_unbound"}
                         and _digest(facts["product_attestation_sha256"])
                         and all(type(facts[key]) is int and 0 <= facts[key] <= 1_000_000
                                 for key in ("canonical_actions","ready_actions","governed_unbound"))
                         and 0 < facts["canonical_actions"]
                         and facts["ready_actions"] <= facts["canonical_actions"]
                         and facts["governed_unbound"] <= facts["canonical_actions"])
            else:
                _require(not facts)
        elif name == "critical_routes":
            if lane.ok:
                _require(set(facts) == {"missing_count"} and type(facts["missing_count"]) is int
                         and facts["missing_count"] == 0)
            else:
                _require(not facts or (lane.code == "unqualified" and set(facts) == {"missing_count"}
                         and type(facts["missing_count"]) is int and 0 <= facts["missing_count"] <= 64))
        elif name == "provider_readiness":
            if lane.ok:
                _require(set(facts) == {"provider_available","selected_provider"}
                         and facts["provider_available"] is True
                         and type(facts["selected_provider"]) is str
                         and facts["selected_provider"] in _PROVIDERS
                         and (selected is None or facts["selected_provider"] == selected))
            else:
                _require(not facts or (lane.code == "unqualified"
                         and set(facts) == {"provider_available"} and facts["provider_available"] is False))
        else:
            _require(not facts)
        result.append(lane.document())
    return result


def _failed_worker(code):
    return [Lane(name, False, code, {}).document() for name in _LANES]


def _bounded_worker(root, args, timeout):
    code = ("import sys;sys.path.insert(0," + repr(str(root)) +
            ");from skeleton.app.strict_install_qualification import _worker_entry;"
            "raise SystemExit(_worker_entry())")
    # No auth or ambient proxy information is forwarded to the child.
    env = {key: os.environ[key] for key in ("PATH","SYSTEMROOT","WINDIR","TEMP","TMP")
           if key in os.environ}
    try:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
            done = subprocess.run([sys.executable,"-I","-B","-c",code], cwd=root, env=env,
                                  input=_canonical(args), stdout=output, stderr=error,
                                  timeout=timeout, check=False)
            if type(done.returncode) is not int or done.returncode != 0:
                return _failed_worker("worker_unavailable")
            output.seek(0)
            raw = output.read(_MAX_RECEIPT+1)
        _require(len(raw) <= _MAX_RECEIPT)
        value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)
        return _validate_worker_result(value, selected=args["selected_provider"])
    except subprocess.TimeoutExpired:
        return _failed_worker("deadline_exceeded")
    except (OSError, ValueError, TypeError, QualificationDenied, RecursionError):
        return _failed_worker("worker_unavailable")


def _git_observation(root, env, args, *, limit, timeout=30):
    # Use disk-backed output rather than accumulating arbitrary path names in
    # process memory. Reports never expose path names or Git diagnostic text.
    command = ["git", "-C", str(root), "-c", "core.fsmonitor=false",
               "-c", "core.untrackedCache=false", "-c", "core.ignoreStat=false", *args]
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.DEVNULL, check=False, timeout=timeout)
        _require(type(result.returncode) is int and result.returncode == 0)
        output.seek(0)
        raw = output.read(limit + 1)
        _require(len(raw) <= limit)
        return raw


def _index_records(raw):
    if not raw:
        return ()
    _require(raw.endswith(b"\0"))
    rows = raw[:-1].split(b"\0")
    _require(all(0 < len(row) <= _MAX_SOURCE_PATH_BYTES for row in rows))
    return rows


def _deny_shadow_paths(root, env):
    # Include ignored executable/importable files: a .gitignore rule must
    # not make an unreviewed module visible to the isolated Python worker.
    for flags in (["--others", "--exclude-standard"],
                  ["--others", "--ignored", "--exclude-standard"]):
        raw = _git_observation(root, env, ["ls-files", "-z", *flags, "--",
                                               *_WORKER_SOURCE_PATHS],
                               limit=_MAX_INDEX_BYTES)
        for row in _index_records(raw):
            path = row.lower()
            is_executable = path.endswith((b".py", b".pyw", b".pyd", b".so", b".dll",
                                          b".pth", b".zip", b".egg"))
            # Bytecode-only modules can be imported directly when placed
            # beside a package; ordinary __pycache__ entries are not such
            # paths. This is not a comprehensive interpreter provenance check.
            direct_bytecode = path.endswith(b".pyc") and b"/__pycache__/" not in path
            _require(not (is_executable or direct_bytecode))


def assert_source_head(root, expected):
    """Pin an observed host checkout, never the identity of running images."""
    _require(type(expected) is str and _SHA.fullmatch(expected) is not None)
    env = {key: os.environ[key] for key in ("PATH","SYSTEMROOT","WINDIR","TEMP","TMP")
           if key in os.environ}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        root = Path(root).resolve(strict=True)
        top = _git_observation(root, env, ["rev-parse", "--show-toplevel"],
                               limit=_MAX_SOURCE_PATH_BYTES, timeout=10)
        _require(bool(top) and top.endswith(b"\n"))
        _require(Path(os.fsdecode(top.rstrip(b"\r\n"))).resolve(strict=True) == root)
        head = _git_observation(root, env, ["rev-parse", "--verify", "HEAD^{commit}"],
                                limit=128, timeout=10)
        _require(head == expected.encode("ascii") + b"\n"
                 or head == expected.encode("ascii") + b"\r\n")
        # A sparse/skip-worktree or assume-unchanged entry can suppress
        # ordinary diff evidence. Deny the entire masked checkout rather
        # than silently granting a full-source observation.
        records = _index_records(_git_observation(
            root, env, ["ls-files", "-v", "-z", "--cached"], limit=_MAX_INDEX_BYTES))
        _require(bool(records) and all(row.startswith(b"H ") for row in records))
        for flags in (["diff","--quiet","--no-ext-diff","--ignore-submodules=none","HEAD","--"],
                      ["diff","--cached","--quiet","--no-ext-diff","--ignore-submodules=none","HEAD","--"]):
            _git_observation(root, env, flags, limit=0)
        _deny_shadow_paths(root, env)
        # A change to HEAD during a long index scan invalidates the observation.
        again = _git_observation(root, env, ["rev-parse", "--verify", "HEAD^{commit}"],
                                 limit=128, timeout=10)
        _require(again == head)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        raise QualificationDenied("host source identity could not be observed") from None


def _pass_scope(lanes):
    lanes = _validate_worker_result(lanes)
    indexed = {row["name"]: row for row in lanes}
    core = all(indexed[name]["ok"] is True for name in _LANES if name != "provider_readiness")
    a = indexed["aggregate_ready"]["facts"]
    b = indexed["aggregate_status"]["facts"]
    # Two distinct aggregate routes must agree on the local product authority.
    core = bool(core and a and b and a == b)
    mode = indexed["backend_health"]["facts"].get("writer_mode","unobserved")
    return {"services_observed":core, "protected_writer_observed":core and mode=="protected_observed",
            "provider_available_observed":core and indexed["provider_readiness"]["ok"] is True,
            "product_attestation_sha256":a.get("product_attestation_sha256") if core else None,
            "writer_mode":mode,
            "canonical_actions":a.get("canonical_actions") if core else None,
            "ready_actions":a.get("ready_actions") if core else None,
            "governed_unbound":a.get("governed_unbound") if core else None,
            "selected_provider":indexed["provider_readiness"]["facts"].get("selected_provider")
            if core and indexed["provider_readiness"]["ok"] else None}


def qualify_live_install(root=None, *, source_head, passes=2, per_probe_timeout=5.0,
                         hard_timeout=20.0, require_protected=False, require_ai=False,
                         environ=None):
    """Check multiple complete rounds of the configured loopback application.

    Returns a redacted, non-authorizing observation receipt. Running image
    provenance, browser JS, actual inference, durable restore and device
    evidence are independent gates, not inferred from this result.
    """
    _require(type(passes) is int and 2 <= passes <= _MAX_PASSES
             and type(per_probe_timeout) in (int,float) and math.isfinite(per_probe_timeout)
             and 0 < per_probe_timeout <= 10
             and type(hard_timeout) in (int,float) and math.isfinite(hard_timeout)
             and per_probe_timeout < hard_timeout <= 45
             and type(require_protected) is bool and type(require_ai) is bool)
    root = (root or find_repo_root()).resolve()
    from skeleton.app.assembly import _runtime_env
    captured = dict(os.environ if environ is None else environ)
    receipt = {"schema":SCHEMA,"source_head":source_head if type(source_head) is str and
               _SHA.fullmatch(source_head) else None,"source_observed":False,
               "service_observation_complete":False,"protected_writer_observed":False,
               "provider_available_observed":False,"inference_qualified":False,
               "running_image_source_verified":False,"browser_execution_verified":False,
               "durable_restore_verified":False,"device_qualified":False,"release_qualified":False,
               "required":{"protected_writer":require_protected,"provider_availability":require_ai},
               "rounds":[],"ok":False,"code":"host_inputs_unqualified"}
    try:
        assert_source_head(root,source_head)
        env_digest = runtime_source_fingerprint(root)
        values = _runtime_env(root,captured)
        manifest = runtime_manifest(load_manifest(),root=root,environ=captured)
        selected = values.get("AI_PROVIDER","local").strip().lower() or "local"
        if selected not in _PROVIDERS:
            selected = "unsupported"
        expected = public_bootstrap_payload(manifest)
        bases = {name:manifest.service(name).public_url for name in ("frontend","backend","skeleton")}
        for base in bases.values():
            _base(base)
        _require(len({_base(base)[1] for base in bases.values()}) == 3)
        inputs = {"bases":bases,"bootstrap":expected,"timeout":per_probe_timeout,
                  "selected_provider":selected}
        def unchanged():
            assert_source_head(root,source_head)
            _require(runtime_source_fingerprint(root)==env_digest)
        unchanged()
        receipt["source_observed"]=True
        scopes=[]
        for index in range(passes):
            lanes = _validate_worker_result(
                _bounded_worker(root, inputs, hard_timeout), selected=selected,
            )
            # Never emit stale or partially accumulated success after an
            # observed .env/source mutation at a round boundary.
            unchanged()
            scope = _pass_scope(lanes)
            scopes.append(scope)
            receipt["rounds"].append({"round":index+1,"lanes":lanes,"scope":scope})
            if index+1 < passes:
                time.sleep(1.1)  # exceed existing aggregate one-second cache
        stable = all(scope == scopes[0] for scope in scopes)
        complete = stable and all(scope["services_observed"] for scope in scopes)
        receipt.update(service_observation_complete=bool(complete),
                       protected_writer_observed=bool(complete and all(s["protected_writer_observed"] for s in scopes)),
                       provider_available_observed=bool(complete and all(s["provider_available_observed"] for s in scopes)),
                       code="observed" if complete else "runtime_observation_incomplete")
        receipt["ok"]=bool(complete and (not require_protected or receipt["protected_writer_observed"])
                           and (not require_ai or receipt["provider_available_observed"]))
        if complete and not receipt["ok"]:
            receipt["code"]="required_scope_unqualified"
    except (QualificationDenied, OSError, ValueError, TypeError, KeyError, UnicodeError):
        receipt.update(source_observed=False,service_observation_complete=False,
                       protected_writer_observed=False,provider_available_observed=False,
                       rounds=[],ok=False,code="host_inputs_unqualified_or_changed")
    receipt["receipt_sha256"]=hashlib.sha256(b"skeleton.strict-install-receipt.v1\0"+
                                             _canonical(receipt)).hexdigest()
    return receipt
