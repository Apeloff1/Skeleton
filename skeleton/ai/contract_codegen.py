from dataclasses import dataclass
import hashlib,re
_IDENT=re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
@dataclass(frozen=True)
class ExtensionPoint: name:str
@dataclass(frozen=True)
class GenerationSpec: contract_version:str; target:str; fields:tuple[str,...]; extensions:tuple[ExtensionPoint,...]=()
@dataclass(frozen=True)
class GeneratedCode: content:str; digest:str; generated:bool=True
def generate_code(spec):
 if spec.target not in {"python-model","python-adapter","python-validator"}:raise ValueError("unsupported generation target")
 names=tuple(spec.fields)+tuple(x.name for x in spec.extensions)
 if any(not _IDENT.fullmatch(x) for x in names):raise ValueError("unsafe generated identifier")
 fields="\n".join(f"    {x}: object" for x in sorted(set(spec.fields)))
 ext=",".join(sorted(x.name for x in spec.extensions))
 content=f"# GENERATED; contract={spec.contract_version}; target={spec.target}; extensions={ext}\nclass Generated:\n{fields or '    pass'}\n"
 return GeneratedCode(content,hashlib.sha256(content.encode()).hexdigest())
