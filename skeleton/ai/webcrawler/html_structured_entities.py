"""Finite Microdata/RDFa/Microformats item-property source observations.

Untrusted HTML item vocabularies are labels, not remote ontology grants.
This module intentionally ignores href/src/resource/content attributes,
itemid, remote itemtype contexts, CSS, templates, nested scripts and all
linkable URL property keys. It never fetches, executes or asserts truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re

_ALLOWED=frozenset({
    "name","headline","description","author","creator",
    "datePublished","dateModified","dateCreated","keywords",
    "genre","articleSection","applicationCategory","softwareVersion",
    "programmingLanguage","operatingSystem","identifier",
    "duration","ratingValue","bestRating","worstRating",
    "position","quantity","category","summary","published",
})
_UKEYS={name.casefold():name for name in _ALLOWED}
_MARKUP_SKIP=frozenset({
    "script","style","iframe","noscript","template","svg","canvas",
    "object","embed","audio","video","source",
})
_ATTR_ID=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_SCHEMA_TYPE=re.compile(r"^https?://schema\.org/([A-Za-z][A-Za-z0-9_-]{0,63})$")
_RDF_TYPE=re.compile(r"^(?:schema:)?([A-Za-z][A-Za-z0-9_-]{0,63})$")
_MICROFORMAT=frozenset({"h-entry","h-card","h-product","h-review","h-event"})
_MF_PROP={
    "p-name":"name","p-summary":"summary","p-category":"category",
    "dt-published":"published","p-description":"description",
}
_MAX_ELEMENTS=16384
_MAX_DEPTH=64
_MAX_ITEMS=128
_MAX_PROPERTIES=512
_MAX_VALUE=1024


class StructuredHTMLError(ValueError):
    """Structural metadata markup exceeded bounded source-only complexity."""


@dataclass(frozen=True)
class HTMLStructuredEntities:
    text:str
    items:int
    properties:int
    families:tuple[str,...]
    truncated:bool
    links:tuple[str,...]=()
    body_executed:bool=False
    reference_trusted:bool=False


@dataclass
class _Entry:
    family:str
    kind:str
    props:list[tuple[str,str]]=field(default_factory=list)


@dataclass
class _Capture:
    depth:int
    item:int
    key:str
    chunks:list[str]=field(default_factory=list)
    length:int=0


class _Reader(HTMLParser):
    def __init__(self,max_chars:int):
        super().__init__(convert_charrefs=True)
        self.limit=max_chars
        self.frames:list[tuple[str,bool,int|None]]=[]
        self.items:list[_Entry]=[]
        self.active:list[_Capture]=[]
        self.lines:list[str]=[]
        self.characters=0
        self.nodes=0
        self.properties=0
        self.truncated=False
        self.hidden_depth=0
        self.families=set()

    def _emit(self,text:str)->None:
        if self.characters+len(text)+1>self.limit:
            self.truncated=True
            return
        self.lines.append(text)
        self.characters+=len(text)+1

    def _kind(self,attributes:dict[str,str|None])->tuple[str,str]|None:
        typ=attributes.get("itemtype")
        if "itemscope" in attributes and isinstance(typ,str):
            m=_SCHEMA_TYPE.fullmatch(typ.strip())
            if m:return "microdata",m.group(1)
        typ=attributes.get("typeof")
        if isinstance(typ,str):
            m=_RDF_TYPE.fullmatch(typ.strip())
            if m:return "rdfa",m.group(1)
        classes=(attributes.get("class") or "").split()
        for token in classes:
            if token in _MICROFORMAT:
                return "microformats2",token
        return None

    def _prop(self,attributes:dict[str,str|None],family:str)->str|None:
        value=(attributes.get("itemprop") if family=="microdata"
               else attributes.get("property") if family=="rdfa"
               else "")
        if family=="microformats2":
            classes=(attributes.get("class") or "").split()
            value=next((_MF_PROP[x] for x in classes if x in _MF_PROP),"")
        if not isinstance(value,str) or not value:
            return None
        if family=="rdfa" and value.startswith("schema:"):
            value=value[7:]
        if not _ATTR_ID.fullmatch(value):
            return None
        return _UKEYS.get(value.casefold())

    def handle_starttag(self,tag,attrs):
        self.nodes+=1
        if self.nodes>_MAX_ELEMENTS or len(self.frames)>=_MAX_DEPTH:
            raise StructuredHTMLError("HTML item tree node/depth cap exceeded")
        attr={k.lower():v for k,v in attrs if isinstance(k,str)}
        hidden=self.hidden_depth>0 or tag in _MARKUP_SKIP
        if hidden:self.hidden_depth+=1
        index=None
        if not hidden:
            kind=self._kind(attr)
            if kind is not None:
                if len(self.items)>=_MAX_ITEMS:
                    self.truncated=True
                else:
                    family,kind_name=kind
                    index=len(self.items)
                    self.items.append(_Entry(family,kind_name))
                    self.families.add(family)
            nearest=index
            if nearest is None:
                nearest=next((ancestor for _,ignored,ancestor in reversed(self.frames)
                              if ancestor is not None and not ignored),None)
            if nearest is not None and tag not in ("meta","link","img","input"):
                key=self._prop(attr,self.items[nearest].family)
                if key:
                    if self.properties>=_MAX_PROPERTIES:
                        self.truncated=True
                    else:
                        self.active.append(_Capture(len(self.frames)+1,nearest,key))
                        self.properties+=1
        self.frames.append((tag,hidden,index))

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        self.handle_endtag(tag)

    def handle_data(self,data):
        if self.hidden_depth or not self.active:
            return
        if len(data)>32768:
            raise StructuredHTMLError("HTML structured text chunk too long")
        for captured in self.active:
            if captured.length+len(data)>_MAX_VALUE:
                self.truncated=True
                continue
            captured.chunks.append(data)
            captured.length+=len(data)

    def _finish(self,frame_depth:int):
        remaining=[]
        for capture in self.active:
            if capture.depth<frame_depth:
                remaining.append(capture)
                continue
            text=" ".join("".join(capture.chunks).split())
            if text and len(text)<=_MAX_VALUE:
                # URLs and likely raw credentials are never promoted as
                # structured metadata; plain text is still untrusted.
                low=text.casefold()
                if "://" not in text and not any(
                    key in low for key in ("api_key=","access_token=","password=","bearer ")
                ):
                    self.items[capture.item].props.append((capture.key,text))
        self.active=remaining

    def handle_endtag(self,tag):
        # HTML in the wild can be unbalanced. Never assume a different
        # element's data was correctly associated with this closing tag.
        match=next((i for i in range(len(self.frames)-1,-1,-1)
                    if self.frames[i][0]==tag),None)
        if match is None:
            return
        while len(self.frames)>match:
            depth=len(self.frames)
            _,hidden,_=self.frames.pop()
            if hidden:self.hidden_depth=max(0,self.hidden_depth-1)
            self._finish(depth)

    def result(self)->HTMLStructuredEntities:
        for i,entry in enumerate(self.items,1):
            self._emit(f"Structured item {i}: family={entry.family}; type={entry.kind}")
            for key,value in entry.props:
                self._emit(f"  {key}: {value}")
        return HTMLStructuredEntities(
            text="\n".join(self.lines),items=len(self.items),
            properties=self.properties,
            families=tuple(sorted(self.families)),truncated=self.truncated,
        )


def extract_html_structured_entities(
    raw:str,*,max_chars:int=8192,
)->HTMLStructuredEntities:
    if (not isinstance(raw,str) or len(raw)>2_500_000
            or type(max_chars) is not int or not 128<=max_chars<=32768):
        raise StructuredHTMLError("HTML structured metadata source limits exceeded")
    parser=_Reader(max_chars)
    try:
        parser.feed(raw)
        parser.close()
        # Closing an unbalanced page is safe only for completed elements.
        # Incomplete nested properties are not projected.
    except (ValueError,RecursionError) as exc:
        raise StructuredHTMLError("malformed HTML structured metadata") from exc
    return parser.result()
