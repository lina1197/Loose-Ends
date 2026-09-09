"""MessageRepository: loads local message JSON files into memory.

The data directory is resolved relative to this source file so the
repository works regardless of the current working directory.

Default data path: <project_root>/data/messages/messages.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from loose_ends.messages.message import Message

# Default location: three levels up from this file -> project root
_DEFAULT_DATA_FILE = (
    Path(__file__).parent.parent.parent / "data" / "messages" / "messages.json"
)


class MessageRepository:
    """Loads and holds an in-memory list of Message objects.

    Parameters
    ----------
    data_file:
        Path to the JSON file containing the message array.
        Defaults to data/messages/messages.json at the project root.
    """

    def __init__(self, data_file: Optional[Path] = None) -> None:
        self._file = Path(data_file) if data_file else _DEFAULT_DATA_FILE
        self._messages: list[Message] = []
        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Parse the JSON file and populate the in-memory list."""
        if not self._file.exists():
            raise FileNotFoundError(
                f"Message data file not found: {self._file}"
            )
        raw = json.loads(self._file.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(
                f"Expected a JSON array in {self._file}, got {type(raw).__name__}."
            )
        self._messages = [Message.from_dict(item) for item in raw]

    # ------------------------------------------------------------------
    # Read access (no mutation)
    # ------------------------------------------------------------------

    def all(self) -> list[Message]:
        """Return all loaded messages in load order (not sorted)."""
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)