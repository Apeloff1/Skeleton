"""No-network local diagnostics and bounded read-only file tools."""
from __future__ import annotations
import hashlib,base64,json
from .spec import ToolSpec,ToolArgument,ToolError
from .registry import SecureRegistry
from .file_read import BoundedFileReader


def build_readonly_catalog(reader:BoundedFileReader|None=None)->SecureRegistry:
    catalog=SecureRegistry()
    catalog.register(ToolSpec('sha256_text',1,(ToolArgument('text','str',max_length=16384),),'read','offline'),
                     lambda a:{'sha256':hashlib.sha256(a['text'].encode()).hexdigest()})
    catalog.register(ToolSpec('json_validate',1,(ToolArgument('text','str',max_length=16384),),'read','offline'),
                     lambda a:{'value':json.loads(a['text'])})
    catalog.register(ToolSpec('utf8_length',1,(ToolArgument('text','str',max_length=16384),),'read','offline'),
                     lambda a:{'bytes':len(a['text'].encode()),'codepoints':len(a['text'])})
    if reader is not None:
        catalog.register(ToolSpec('read_source',1,(ToolArgument('path','str',max_length=512),),'read','operator-files'),
                         lambda a:reader.read_text(a['path']))
    catalog.freeze();return catalog
