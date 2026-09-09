"""In-memory commitment store for development use.

Holds a process-scoped singleton of Commitment objects keyed by ID.
This will be replaced by a proper persistence layer in a later step.
"""
from __future__ import annotations

from typing import Optional

from loose_ends.domain.commitment import Commitment


class _InMemoryCommitmentStore:
    """Thread-unsafe in-memory store — sufficient for a single-process PoC."""

    def __init__(self) -> None:
        self._data: dict[str, Commitment] = {}
        self._drafts: dict[str, str] = {}

    # ── Drafts ─────────────────────────────────────────────────────────────

    def set_draft(self, commitment_id: str, draft_text: str) -> None:
        """Store a response draft for a commitment."""
        self._drafts[commitment_id] = draft_text

    def get_draft(self, commitment_id: str) -> Optional[str]:
        """Retrieve a stored response draft for a commitment."""
        return self._drafts.get(commitment_id)

    def remove_draft(self, commitment_id: str) -> None:
        """Remove a response draft for a commitment."""
        self._drafts.pop(commitment_id, None)

    # ── Write ──────────────────────────────────────────────────────────────

    def add(self, commitment: Commitment) -> None:
        """Insert or overwrite a commitment by its ID."""
        self._data[commitment.id] = commitment

    # ── Read ───────────────────────────────────────────────────────────────

    def get(self, commitment_id: str) -> Optional[Commitment]:
        """Return the commitment with *commitment_id*, or None."""
        return self._data.get(commitment_id)

    def all(self) -> list[Commitment]:
        """Return all stored commitments in insertion order."""
        return list(self._data.values())

    # ── Utility ────────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove every stored commitment.  Intended for test teardown."""
        self._data.clear()
        self._drafts.clear()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, commitment_id: str) -> bool:
        return commitment_id in self._data


# Module-level singleton — imported by tools and tests.
commitment_store = _InMemoryCommitmentStore()