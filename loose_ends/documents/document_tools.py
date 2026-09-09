"""Strands tools for document retrieval: search_documents, get_document.

Tools
-----
search_documents  - case-insensitive keyword search across title, filename,
                    and content; returns summaries (no content field).
get_document      - retrieve a single document by ID including full content.

No embeddings, no vector search, no ranking algorithms.
Matching and ordering are fully deterministic.
"""
from __future__ import annotations

import json
from typing import Optional

from strands import tool

from loose_ends.documents.document import Document
from loose_ends.documents.repository import DocumentRepository

# Module-level singleton: loaded once at import time.
_repo = DocumentRepository()


def _matches(
    doc: Document,
    query: Optional[str],
    document_type: Optional[str],
) -> bool:
    """Return True when *doc* satisfies all supplied filters (AND semantics)."""
    if query:
        needle = query.lower()
        if (
            needle not in doc.title.lower()
            and needle not in doc.filename.lower()
            and needle not in doc.content.lower()
        ):
            return False
    if document_type and doc.document_type != document_type:
        return False
    return True


def _sort_key(doc: Document):
    """Primary: created_at ascending. Secondary: document_id ascending."""
    return (doc.created_at, doc.document_id)


@tool
def search_documents(
    query: Optional[str] = None,
    document_type: Optional[str] = None,
) -> str:
    """Search the local document store and return matching document summaries.

    Content is intentionally excluded from results to keep responses concise.
    Use get_document to retrieve the full text of a specific document.

    All filters are optional. Supplying no filters returns every document.
    Multiple filters are combined with AND semantics.

    Args:
        query: Case-insensitive substring matched against title, filename,
               and content. A document matches if the query appears in ANY
               of these three fields.
        document_type: Exact document type to filter by (e.g., 'financial',
                       'policy', 'checklist', 'presentation').

    Returns:
        A JSON string with:
            count     - total number of matching documents
            documents - list ordered by created_at asc, then document_id asc.
                        Each entry contains: document_id, filename, title,
                        document_type, created_at, updated_at.
                        Content is NOT included.
    """
    matched = [
        d for d in _repo.all()
        if _matches(d, query, document_type)
    ]
    matched.sort(key=_sort_key)

    return json.dumps(
        {
            "count": len(matched),
            "documents": [d.to_summary_dict() for d in matched],
        }
    )


@tool
def get_document(document_id: str) -> str:
    """Retrieve a single document by ID, including its full content.

    Args:
        document_id: The unique identifier of the document to retrieve.

    Returns:
        A JSON string with all document fields including content.
        On error, returns a JSON string with an "error" key.
    """
    doc = _repo.get(document_id)
    if doc is None:
        return json.dumps(
            {
                "error": f"No document found with id {document_id!r}.",
                "document_id": document_id,
            }
        )
    return json.dumps(doc.to_dict())