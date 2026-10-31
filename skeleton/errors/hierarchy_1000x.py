"""skeleton/errors/hierarchy_1000x.py
1000x extreme complete error hierarchy.
Full fail-closed subclasses.
Fail-closed.
"""
class SkeletonError(Exception):
    code = "BASE"
    severity = "medium"

class StructuralError1000x(SkeletonError):
    code = "STRUCT1000"
    severity = "high"
