from dataclasses import dataclass
@dataclass(frozen=True)
class LicenseObligation: kind:str; value:str
@dataclass(frozen=True)
class LicenseRecord: artifact:str; version:str; license_id:str|None; obligations:tuple[LicenseObligation,...]
@dataclass(frozen=True)
class LicenseCompatibility: compatible:bool; reason:str
def compatible(records,distribution):
 records=tuple(records)
 if not isinstance(distribution,bool) or not records:return LicenseCompatibility(False,"invalid license query")
 if any(not r.artifact or not r.version or any(not o.kind or not o.value for o in r.obligations) for r in records):return LicenseCompatibility(False,"invalid license record")
 if any(r.license_id is None for r in records):return LicenseCompatibility(False,"unknown license")
 if distribution and any(o.kind=="no-redistribution" for r in records for o in r.obligations):return LicenseCompatibility(False,"redistribution forbidden")
 return LicenseCompatibility(True,"compatible")
