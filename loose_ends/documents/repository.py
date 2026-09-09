"""DocumentRepository: loads local document JSON files into memory.

The data directory is resolved relative to this source file so the
repository works regardless of the current working directory.

Default data path: <project_root>/data/documents/documents.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from loose_ends.documents.document import Document

_DEFAULT_DATA_FILE = (
    Path(__file__).parent.parent.parent / "data" / "documents" / "documents.json"
)


class DocumentRepository:
    """Loads and holds an in-memory dict of Document objects keyed by document_id.

    Parameters
    ----------
    data_file:
        Path to the JSON file containing the document array.
        Defaults to data/documents/documents.json at the project root.
    """

    def __init__(self, data_file: Optional[Path] = None) -> None:
        self._file = Path(data_file) if data_file else _DEFAULT_DATA_FILE
        self._documents: dict[str, Document] = {}
        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._file.exists():
            raise FileNotFoundError(
                f"Document data file not found: {self._file}"
            )
        raw = json.loads(self._file.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(
                f"Expected a JSON array in {self._file}, "
                f"got {type(raw).__name__}."
            )
        for item in raw:
            doc = Document.from_dict(item)
            self._documents[doc.document_id] = doc

    # ------------------------------------------------------------------
    # Read access (no mutation)
    # ------------------------------------------------------------------

    def all(self) -> list[Document]:
        """Return all loaded documents in load order."""
        return list(self._documents.values())

    def get(self, document_id: str) -> Optional[Document]:
        """Return the document with *document_id*, or None if not found."""
        return self._documents.get(document_id)

    def __len__(self) -> int:
        return len(self._documents)