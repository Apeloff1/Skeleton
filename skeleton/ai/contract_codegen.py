from dataclasses import dataclass
import hashlib
@dataclass(frozen=True)
class ExtensionPoint: name:str
@dataclass(frozen=True)
class GenerationSpec: contract_version:str; target:str; fields:tuple[str,...]; extensions:tuple[ExtensionPoint,...]=()
@dataclass(frozen=True)
class GeneratedCode: content:str; digest:str; generated:bool=True
def generate_code(spec):
 fields="\n".join(f"    {x}: object" for x in sorted(set(spec.fields)))
 ext=",".join(sorted(x.name for x in spec.extensions))
 content=f"# GENERATED; contract={spec.contract_version}; extensions={ext}\nclass Generated:\n{fields or '    pass'}\n"
 return GeneratedCode(content,hashlib.sha256(content.encode()).hexdigest())
