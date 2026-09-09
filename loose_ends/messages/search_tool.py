"""Strands tool: search_messages.

Performs deterministic, case-insensitive text search and exact-match
filtering over the local message dataset.  No embeddings or network
calls are used.

Filter semantics
----------------
* text query  - case-insensitive substring match against message content
* sender      - exact-match (case-sensitive) on the sender field
* conversation_id - exact-match on the conversation_id field
* Multiple filters are combined with AND semantics.
* Passing no filters returns all messages.

Ordering: timestamp ascending, then message_id ascending as tie-breaker.
"""
from __future__ import annotations

import json
from typing import Optional

from strands import tool

from loose_ends.messages.message import Message
from loose_ends.messages.repository import MessageRepository

# Module-level singleton: loaded once at import time.
_repo = MessageRepository()


def _matches(
    msg: Message,
    query: Optional[str],
    sender: Optional[str],
    conversation_id: Optional[str],
) -> bool:
    """Return True when msg satisfies all supplied filters."""
    if query and query.lower() not in msg.content.lower():
        return False
    if sender and msg.sender != sender:
        return False
    if conversation_id and msg.conversation_id != conversation_id:
        return False
    return True


def _sort_key(msg: Message):
    """Primary: timestamp ascending.  Secondary: message_id ascending."""
    return (msg.timestamp, msg.message_id)


@tool
def search_messages(
    query: Optional[str] = None,
    sender: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> str:
    """Search the local message store and return matching messages.

    All filters are optional.  Supplying no filters returns every message.
    Multiple filters are combined with AND semantics.

    Args:
        query: Case-insensitive substring to search for in message content.
        sender: Exact sender name to filter by.
        conversation_id: Exact conversation ID to filter by.

    Returns:
        A JSON string with:
            count    - total number of matching messages
            messages - list ordered by timestamp asc, then message_id asc.
                       Each entry contains: message_id, sender, recipient,
                       timestamp (ISO 8601), content, conversation_id.
    """
    matched = [
        m for m in _repo.all()
        if _matches(m, query, sender, conversation_id)
    ]

    matched.sort(key=_sort_key)

    return json.dumps(
        {
            "count": len(matched),
            "messages": [m.to_dict() for m in matched],
        }
    )