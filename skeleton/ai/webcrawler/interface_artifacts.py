"""Explicit source-only interface catalog for GraphQL, AsyncAPI and proto3."""
from __future__ import annotations

from .graphql_documents import GRAPHQL_MEDIA_TYPES,extract_graphql_schema
from .asyncapi_documents import ASYNCAPI_MEDIA_TYPES,extract_asyncapi
from .proto_documents import PROTO_MEDIA_TYPES,extract_proto
from .research_projection import ResearchFormatError,ResearchProjection

INTERFACE_TYPES=GRAPHQL_MEDIA_TYPES | ASYNCAPI_MEDIA_TYPES | PROTO_MEDIA_TYPES


def extract_interface_artifact(
    raw:str,mime:str,*,max_chars:int,max_links:int,
)->ResearchProjection:
    for types,parser in (
        (GRAPHQL_MEDIA_TYPES,extract_graphql_schema),
        (ASYNCAPI_MEDIA_TYPES,extract_asyncapi),
        (PROTO_MEDIA_TYPES,extract_proto),
    ):
        if mime in types:
            return parser(raw,max_chars=max_chars,max_links=max_links)
    raise ResearchFormatError("unsupported interface source MIME type")
