"""Message data model for the Loose Ends message store.

Uses only the Python standard library.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Message:
    """A single immutable message in the local message store.

    Fields
    ------
    message_id      Unique identifier for this message.
    sender          Name or identifier of the person who sent the message.
    recipient       Name or identifier of the intended recipient.
    timestamp       UTC-aware datetime the message was sent.
    content         Full text of the message.
    conversation_id Groups related messages into a thread.
    """

    message_id: str
    sender: str
    recipient: str
    timestamp: datetime
    content: str
    conversation_id: str

    def __post_init__(self) -> None:
        if not self.message_id or not self.message_id.strip():
            raise ValueError("'message_id' must be a non-empty string.")
        if not self.sender or not self.sender.strip():
            raise ValueError("'sender' must be a non-empty string.")
        if not self.recipient or not self.recipient.strip():
            raise ValueError("'recipient' must be a non-empty string.")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("'timestamp' must be a datetime instance.")
        if self.timestamp.tzinfo is None:
            raise ValueError("'timestamp' must be UTC-aware (tzinfo required).")
        if not self.content:
            raise ValueError("'content' must be a non-empty string.")
        if not self.conversation_id or not self.conversation_id.strip():
            raise ValueError("'conversation_id' must be a non-empty string.")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary."""
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "conversation_id": self.conversation_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """Construct a Message from a plain dictionary.

        Accepts ISO 8601 timestamp strings. Naive datetimes are assumed UTC.
        """
        raw_ts = data["timestamp"]
        ts = datetime.fromisoformat(raw_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return cls(
            message_id=data["message_id"],
            sender=data["sender"],
            recipient=data["recipient"],
            timestamp=ts,
            content=data["content"],
            conversation_id=data["conversation_id"],
        )