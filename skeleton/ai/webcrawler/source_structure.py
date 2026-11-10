"""Read-only, bounded source structure annotation for already acquired code."""
from __future__ import annotations
from dataclasses import dataclass
from .python_signatures import extract_python_signatures
from .lexical_signatures import extract_lexical_signatures
from .source_signatures import SourceSignatureError

SOURCE_STRUCTURE_TYPES={
    "text/x-python":"python","text/x-rust":"rust","text/x-go":"go",
    "text/x-java-source":"java","text/x-c":"c","text/x-csrc":"c",
    "text/x-c++src":"cpp","text/javascript":"javascript",
    "application/javascript":"javascript","application/x-javascript":"javascript",
    "text/x-typescript":"typescript","application/typescript":"typescript",
}


@dataclass(frozen=True)
class SourceStructureProjection:
    text:str
    language:str
    declarations:int
    imports:int
    truncated:bool
    syntax_validated:bool
    body_executed:bool=False
    network_fetched:bool=False
    code_approved:bool=False


def analyze_source_structure(
    raw:str,media_type:str,*,max_chars:int=8192,
)->SourceStructureProjection:
    if media_type not in SOURCE_STRUCTURE_TYPES:
        raise SourceSignatureError("unsupported source language media type")
    if type(max_chars) is not int or not 128<=max_chars<=32768:
        raise SourceSignatureError("source structure text bound invalid")
    language=SOURCE_STRUCTURE_TYPES[media_type]
    analysis=(extract_python_signatures(raw) if language=="python"
              else extract_lexical_signatures(raw,language))
    lines=[
        "Unreviewed source structures (NEVER executed or verified)",
        f"Language: {language}; analysis_mode: {analysis.syntax_mode}",
        f"Definitions: {len(analysis.declarations)}; import references: {len(analysis.imports)}",
    ]
    for item in analysis.declarations:
        line=f"{item.kind}: {item.symbol}; source_line: {item.line}"
        if item.arity is not None:
            line+=f"; declared_arguments: {item.arity}"
        if item.asynchronous:
            line+="; asynchronous: true"
        lines.append(line)
    for module in analysis.imports:
        lines.append("Source import reference: "+module)
    lines.append("No imports loaded; declarations are untrusted evidence only")
    value="\n".join(lines)
    return SourceStructureProjection(
        text=value[:max_chars],language=language,
        declarations=len(analysis.declarations),imports=len(analysis.imports),
        truncated=analysis.truncated or len(value)>max_chars,
        syntax_validated=analysis.syntax_mode=="python_ast",
    )
