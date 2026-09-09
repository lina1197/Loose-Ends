"""Document data model for the Loose Ends document store.

Uses only the Python standard library.
Follows the same frozen-dataclass pattern as the Message model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Document:
    """A single immutable document in the local document store.

    Fields
    ------
    document_id   Unique identifier for this document.
    filename      Original filename (e.g., 'Q3_financial_figures.xlsx').
    title         Human-readable document title.
    content       Full text content of the document.
    document_type Category string (e.g., 'financial', 'policy', 'checklist').
    created_at    UTC-aware datetime the document was created.
    updated_at    UTC-aware datetime the document was last updated.
    """

    document_id: str
    filename: str
    title: str
    content: str
    document_type: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for field in ("document_id", "filename", "title", "content", "document_type"):
            val = getattr(self, field)
            if not val or not val.strip():
                raise ValueError(f"'{field}' must be a non-empty string.")
        for ts_field in ("created_at", "updated_at"):
            ts = getattr(self, ts_field)
            if not isinstance(ts, datetime):
                raise TypeError(f"'{ts_field}' must be a datetime instance.")
            if ts.tzinfo is None:
                raise ValueError(f"'{ts_field}' must be UTC-aware (tzinfo required).")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary including full content."""
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "title": self.title,
            "content": self.content,
            "document_type": self.document_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_summary_dict(self) -> dict:
        """Return a JSON-serialisable dictionary WITHOUT content.

        Used by search_documents to avoid exposing large content in
        search results.  Callers must use get_document to read content.
        """
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "title": self.title,
            "document_type": self.document_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        """Construct a Document from a plain dictionary.

        Accepts ISO 8601 timestamp strings. Naive datetimes are assumed UTC.
        """
        def _parse_dt(raw: str) -> datetime:
            ts = datetime.fromisoformat(raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts

        return cls(
            document_id=data["document_id"],
            filename=data["filename"],
            title=data["title"],
            content=data["content"],
            document_type=data["document_type"],
            created_at=_parse_dt(data["created_at"]),
            updated_at=_parse_dt(data["updated_at"]),
        )