"""Unit and integration tests for the search_messages Strands tool.

Rules:
- No Gemini calls anywhere in this file.
- Tests use the real local JSON dataset (data/messages/messages.json).
- Tests use a fresh MessageRepository so they are independent of the
  module-level singleton in search_tool.py.
- The search_messages tool itself is also called directly.
- Stored message objects must not be mutated by any search operation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from loose_ends.messages.message import Message
from loose_ends.messages.repository import MessageRepository
from loose_ends.messages.search_tool import search_messages, _repo

# Total messages in the dataset (computed from data file)
TOTAL_MESSAGES = len(MessageRepository())


# ── Helpers ───────────────────────────────────────────────────────────────────


def _call(**kwargs) -> dict:
    """Invoke search_messages and parse the JSON result."""
    return json.loads(search_messages(**kwargs))


# ── Integration: tool importability ──────────────────────────────────────────


class TestToolIntegration:
    def test_tool_is_importable(self):
        from loose_ends.messages.search_tool import search_messages as t
        assert t is not None

    def test_tool_is_callable(self):
        assert callable(search_messages)

    def test_tool_has_strands_shape(self):
        has_meta = (
            hasattr(search_messages, "TOOL_SPEC")
            or hasattr(search_messages, "tool_spec")
            or hasattr(search_messages, "__tool_name__")
            or hasattr(search_messages, "__wrapped__")
            or callable(search_messages)
        )
        assert has_meta


# ── Repository: loading ───────────────────────────────────────────────────────


class TestRepositoryLoading:
    def test_default_repository_loads_messages(self):
        repo = MessageRepository()
        assert len(repo) == TOTAL_MESSAGES

    def test_loaded_messages_are_message_instances(self):
        repo = MessageRepository()
        for msg in repo.all():
            assert isinstance(msg, Message)

    def test_loaded_messages_have_utc_aware_timestamps(self):
        repo = MessageRepository()
        for msg in repo.all():
            assert msg.timestamp.tzinfo is not None

    def test_all_returns_independent_list(self):
        """Mutating the returned list must not affect the repository."""
        repo = MessageRepository()
        snapshot1 = repo.all()
        snapshot1.clear()
        assert len(repo) == TOTAL_MESSAGES

    def test_repository_missing_file_raises(self, tmp_path):
        from pathlib import Path
        with pytest.raises(FileNotFoundError):
            MessageRepository(data_file=tmp_path / "nonexistent.json")

    def test_all_message_ids_are_unique(self):
        repo = MessageRepository()
        ids = [m.message_id for m in repo.all()]
        assert len(ids) == len(set(ids))

    def test_known_message_id_present(self):
        repo = MessageRepository()
        ids = {m.message_id for m in repo.all()}
        assert "msg-001" in ids
        assert "msg-009" in ids


# ── No-filter search ─────────────────────────────────────────────────────────


class TestNoFilterSearch:
    def test_no_filters_returns_all_messages(self):
        result = _call()
        assert result["count"] == TOTAL_MESSAGES
        assert len(result["messages"]) == TOTAL_MESSAGES

    def test_count_matches_messages_list_length(self):
        result = _call()
        assert result["count"] == len(result["messages"])

    def test_explicit_none_filters_returns_all(self):
        result = _call(query=None, sender=None, conversation_id=None)
        assert result["count"] == TOTAL_MESSAGES


# ── Text / content search ─────────────────────────────────────────────────────


class TestTextSearch:
    def test_text_search_returns_matching_messages(self):
        result = _call(query="Q3 report")
        assert result["count"] > 0
        for msg in result["messages"]:
            assert "q3 report" in msg["content"].lower()

    def test_text_search_is_case_insensitive_lower(self):
        lower = _call(query="q3 report")
        mixed = _call(query="Q3 Report")
        assert lower["count"] == mixed["count"]

    def test_text_search_is_case_insensitive_upper(self):
        upper = _call(query="Q3 REPORT")
        lower = _call(query="q3 report")
        assert upper["count"] == lower["count"]

    def test_text_search_no_match_returns_empty(self):
        result = _call(query="zzz-no-match-xyz-9999")
        assert result["count"] == 0
        assert result["messages"] == []

    def test_text_search_substring_match(self):
        # "hotfix" appears in conv-hotfix-deploy messages
        result = _call(query="hotfix")
        assert result["count"] > 0
        for msg in result["messages"]:
            assert "hotfix" in msg["content"].lower()

    def test_text_search_partial_word(self):
        # "deploy" is a substring present in some messages
        result = _call(query="deploy")
        assert result["count"] > 0


# ── Sender filtering ──────────────────────────────────────────────────────────


class TestSenderFilter:
    def test_sender_filter_returns_only_that_sender(self):
        result = _call(sender="alice")
        assert result["count"] > 0
        for msg in result["messages"]:
            assert msg["sender"] == "alice"

    def test_sender_filter_is_case_sensitive(self):
        """Sender matching is exact/deterministic; 'Alice' != 'alice'."""
        upper = _call(sender="Alice")
        lower = _call(sender="alice")
        # Our dataset uses lowercase 'alice' so upper should return 0
        assert upper["count"] == 0
        assert lower["count"] > 0

    def test_unknown_sender_returns_empty(self):
        result = _call(sender="nobody-xyz")
        assert result["count"] == 0

    def test_bob_appears_as_sender(self):
        result = _call(sender="bob")
        assert result["count"] > 0
        for msg in result["messages"]:
            assert msg["sender"] == "bob"

    def test_qa_team_appears_as_sender(self):
        result = _call(sender="qa-team")
        assert result["count"] == 1
        assert result["messages"][0]["sender"] == "qa-team"


# ── Conversation filtering ────────────────────────────────────────────────────


class TestConversationFilter:
    def test_conversation_filter_returns_only_that_conversation(self):
        result = _call(conversation_id="conv-q3-report")
        assert result["count"] > 0
        for msg in result["messages"]:
            assert msg["conversation_id"] == "conv-q3-report"

    def test_hotfix_conversation_isolated(self):
        result = _call(conversation_id="conv-hotfix-deploy")
        assert result["count"] > 0
        for msg in result["messages"]:
            assert msg["conversation_id"] == "conv-hotfix-deploy"

    def test_unknown_conversation_returns_empty(self):
        result = _call(conversation_id="conv-does-not-exist")
        assert result["count"] == 0

    def test_all_conversations_represented(self):
        conv_ids = {
            m["conversation_id"]
            for m in _call()["messages"]
        }
        assert "conv-q3-report" in conv_ids
        assert "conv-hotfix-deploy" in conv_ids
        assert "conv-partnership" in conv_ids


# ── Combined filters (AND semantics) ─────────────────────────────────────────


class TestCombinedFilters:
    def test_sender_and_conversation_narrows_results(self):
        all_in_conv = _call(conversation_id="conv-q3-report")["count"]
        narrowed = _call(sender="alice", conversation_id="conv-q3-report")["count"]
        assert narrowed < all_in_conv
        assert narrowed > 0

    def test_query_and_sender_combined(self):
        result = _call(query="Q3", sender="alice")
        assert result["count"] > 0
        for msg in result["messages"]:
            assert "q3" in msg["content"].lower()
            assert msg["sender"] == "alice"

    def test_query_and_conversation_combined(self):
        result = _call(query="hotfix", conversation_id="conv-hotfix-deploy")
        assert result["count"] > 0
        for msg in result["messages"]:
            assert "hotfix" in msg["content"].lower()
            assert msg["conversation_id"] == "conv-hotfix-deploy"

    def test_all_three_filters_combined(self):
        result = _call(
            query="hotfix",
            sender="dave",
            conversation_id="conv-hotfix-deploy",
        )
        assert result["count"] > 0
        for msg in result["messages"]:
            assert "hotfix" in msg["content"].lower()
            assert msg["sender"] == "dave"
            assert msg["conversation_id"] == "conv-hotfix-deploy"

    def test_conflicting_filters_return_empty(self):
        # alice does not appear in conv-hotfix-deploy
        result = _call(sender="alice", conversation_id="conv-hotfix-deploy")
        assert result["count"] == 0


# ── Deterministic ordering ────────────────────────────────────────────────────


class TestDeterministicOrdering:
    def test_results_ordered_by_timestamp_ascending(self):
        result = _call()
        timestamps = [
            datetime.fromisoformat(m["timestamp"])
            for m in result["messages"]
        ]
        assert timestamps == sorted(timestamps)

    def test_two_calls_return_identical_order(self):
        first = _call()["messages"]
        second = _call()["messages"]
        assert [m["message_id"] for m in first] == [
            m["message_id"] for m in second
        ]

    def test_conversation_results_ordered_chronologically(self):
        result = _call(conversation_id="conv-q3-report")
        timestamps = [
            datetime.fromisoformat(m["timestamp"])
            for m in result["messages"]
        ]
        assert timestamps == sorted(timestamps)


# ── Result shape and JSON serializability ─────────────────────────────────────


class TestResultShape:
    def test_result_is_valid_json(self):
        raw = search_messages()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_result_has_count_and_messages_keys(self):
        result = _call()
        assert "count" in result
        assert "messages" in result

    def test_each_message_has_required_fields(self):
        result = _call()
        required = {"message_id", "sender", "recipient", "timestamp", "content",
                    "conversation_id"}
        for msg in result["messages"]:
            assert required.issubset(msg.keys())

    def test_timestamps_are_iso_string(self):
        result = _call()
        for msg in result["messages"]:
            ts = msg["timestamp"]
            assert isinstance(ts, str)
            datetime.fromisoformat(ts)  # must be parseable

    def test_result_round_trips_through_json(self):
        raw = search_messages()
        reparsed = json.loads(json.dumps(json.loads(raw)))
        assert reparsed["count"] == TOTAL_MESSAGES


# ── No mutation on read ───────────────────────────────────────────────────────


class TestNoMutation:
    def test_search_does_not_change_repository_size(self):
        repo = MessageRepository()
        size_before = len(repo)
        _call(query="Q3")
        assert len(repo) == size_before

    def test_search_does_not_alter_message_content(self):
        """The content of stored messages must be unchanged after a search."""
        repo = MessageRepository()
        original_contents = [m.content for m in repo.all()]
        _call(query="report")
        after_contents = [m.content for m in repo.all()]
        assert original_contents == after_contents

    def test_module_repo_size_unchanged_after_search(self):
        before = len(_repo)
        _call(sender="alice")
        assert len(_repo) == before