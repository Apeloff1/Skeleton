"""Finite, inert research graph syntax dispatch under canonical source rights."""
from __future__ import annotations

from .graphml_documents import GRAPHML_TYPES,extract_graphml
from .gexf_documents import GEXF_TYPES,extract_gexf
from .dot_documents import DOT_TYPES,extract_dot_graph
from .research_projection import ResearchFormatError,ResearchProjection

GRAPH_ARTIFACT_TYPES=GRAPHML_TYPES | GEXF_TYPES | DOT_TYPES


def extract_graph_artifact(
    raw:str,mime:str,*,max_chars:int,max_links:int,
)->ResearchProjection:
    for types,parser in (
        (GRAPHML_TYPES,extract_graphml),
        (GEXF_TYPES,extract_gexf),
        (DOT_TYPES,extract_dot_graph),
    ):
        if mime in types:
            return parser(raw,max_chars=max_chars,max_links=max_links)
    raise ResearchFormatError("unapproved research graph source type")
