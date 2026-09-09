"""Loose Ends message sub-package: data model, repository, and search tool."""
from loose_ends.messages.message import Message
from loose_ends.messages.repository import MessageRepository

__all__ = ["Message", "MessageRepository"]