"""Minimal JSON-schema subset validator for request bodies (no external deps)."""
from __future__ import annotations

from typing import Any, Dict, List

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool,
          "integer": int, "number": (int, float), "null": type(None)}


def _type_ok(value: Any, t: str) -> bool:
    if t in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[t])


def validate(value: Any, schema: Dict[str, Any], path: str = "$") -> List[Dict[str, str]]:
    errs: List[Dict[str, str]] = []
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(value, x) for x in types):
            return [{"path": path, "error": f"expected {'|'.join(types)}"}]
    if "enum" in schema and value not in schema["enum"]:
        errs.append({"path": path, "error": "not in enum"})
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append({"path": path, "error": "too short"})
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append({"path": path, "error": "too long"})
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append({"path": path, "error": "below minimum"})
        if "maximum" in schema and value > schema["maximum"]:
            errs.append({"path": path, "error": "above maximum"})
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errs.append({"path": f"{path}.{req}", "error": "required"})
        for k, v in value.items():
            if k in props:
                errs.extend(validate(v, props[k], f"{path}.{k}"))
            elif schema.get("additionalProperties") is False:
                errs.append({"path": f"{path}.{k}", "error": "unexpected property"})
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append({"path": path, "error": "too many items"})
        if "items" in schema:
            for i, item in enumerate(value):
                errs.extend(validate(item, schema["items"], f"{path}[{i}]"))
    return errs[:50]
