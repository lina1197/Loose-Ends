"""Tests for the action-preparation workflow and its architectural separation.

All tests are deterministic and do NOT call Gemini.

Coverage:
  - ACTION_PREPARATION_TOOLS contains exactly the right tools
  - create_commitment, update_commitment, search_messages are absent
  - system prompt explicitly prohibits state changes and message search
  - build_action_preparer() constructs and raises correctly
  - demo scenario: seeded store stays read-only
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from strands import Agent

from loose_ends.agent import (
    ACTION_PREPARATION_TOOLS,
    ACTION_PREPARATION_SYSTEM_PROMPT,
    COMMITMENT_DETECTION_TOOLS,
    DEPENDENCY_RESOLUTION_TOOLS,
    build_action_preparer,
)
from loose_ends.commitment_tools import (
    create_commitment,
    get_open_commitments,
    update_commitment,
)
from loose_ends.messages.search_tool import search_messages
from loose_ends.documents.document_tools import search_documents, get_document
from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.store import commitment_store

S = CommitmentStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_store():
    commitment_store.clear()
    yield
    commitment_store.clear()


def _seed() -> Commitment:
    """Insert the canonical Q3 demo commitment."""
    ts = datetime(2027, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    deadline = datetime(2027, 9, 3, 17, 0, 0, tzinfo=timezone.utc)
    c = Commitment(
        id="demo-q3-commitment",
        action="Send the Q3 financial report",
        owner="bob",
        recipient="alice",
        status=S.READY_TO_ACT,
        deadline=deadline,
        source_message_id="msg-002",
        context="Alice needs the Q3 financial report for the board presentation.",
        next_action="Find the latest Q3 financial figures and prepare the report for Alice.",
        created_at=ts,
        updated_at=ts,
    )
    commitment_store.add(c)
    return c


# ---------------------------------------------------------------------------
# Action-preparation tool list
# ---------------------------------------------------------------------------

class TestActionPreparationTools:
    def _names(self) -> set[str]:
        return {t.__name__ for t in ACTION_PREPARATION_TOOLS}

    def test_has_get_open_commitments(self):
        assert "get_open_commitments" in self._names()

    def test_has_search_documents(self):
        assert "search_documents" in self._names()

    def test_has_get_document(self):
        assert "get_document" in self._names()

    def test_does_not_have_create_commitment(self):
        assert "create_commitment" not in self._names()

    def test_does_not_have_update_commitment(self):
        assert "update_commitment" not in self._names()

    def test_does_not_have_search_messages(self):
        assert "search_messages" not in self._names()

    def test_has_exactly_three_tools(self):
        assert len(ACTION_PREPARATION_TOOLS) == 3

    def test_get_open_commitments_is_correct_object(self):
        assert get_open_commitments in ACTION_PREPARATION_TOOLS

    def test_search_documents_is_correct_object(self):
        assert search_documents in ACTION_PREPARATION_TOOLS

    def test_get_document_is_correct_object(self):
        assert get_document in ACTION_PREPARATION_TOOLS

    def test_create_commitment_object_is_absent(self):
        assert create_commitment not in ACTION_PREPARATION_TOOLS

    def test_update_commitment_object_is_absent(self):
        assert update_commitment not in ACTION_PREPARATION_TOOLS

    def test_search_messages_object_is_absent(self):
        assert search_messages not in ACTION_PREPARATION_TOOLS

    def test_all_tools_are_callable(self):
        for t in ACTION_PREPARATION_TOOLS:
            assert callable(t)


# ---------------------------------------------------------------------------
# Architectural separation from other workflows
# ---------------------------------------------------------------------------

class TestArchitecturalSeparation:
    def _ap_names(self) -> set[str]:
        return {t.__name__ for t in ACTION_PREPARATION_TOOLS}

    def _det_names(self) -> set[str]:
        return {t.__name__ for t in COMMITMENT_DETECTION_TOOLS}

    def _res_names(self) -> set[str]:
        return {t.__name__ for t in DEPENDENCY_RESOLUTION_TOOLS}

    def test_action_prep_is_different_from_detection(self):
        assert ACTION_PREPARATION_TOOLS is not COMMITMENT_DETECTION_TOOLS

    def test_action_prep_is_different_from_resolution(self):
        assert ACTION_PREPARATION_TOOLS is not DEPENDENCY_RESOLUTION_TOOLS

    def test_detection_has_create_commitment(self):
        assert "create_commitment" in self._det_names()

    def test_resolution_has_update_commitment(self):
        assert "update_commitment" in self._res_names()

    def test_action_prep_has_neither_write_tool(self):
        ap = self._ap_names()
        assert "create_commitment" not in ap
        assert "update_commitment" not in ap

    def test_action_prep_has_document_tools(self):
        ap = self._ap_names()
        assert "search_documents" in ap
        assert "get_document" in ap

    def test_detection_does_not_have_document_tools(self):
        # Detection workflow should NOT have document tools yet
        det = self._det_names()
        assert "search_documents" not in det
        assert "get_document" not in det

    def test_resolution_does_not_have_document_tools(self):
        res = self._res_names()
        assert "search_documents" not in res
        assert "get_document" not in res

    def test_three_distinct_tool_sets(self):
        assert self._ap_names() != self._det_names()
        assert self._ap_names() != self._res_names()
        assert self._det_names() != self._res_names()


# ---------------------------------------------------------------------------
# System prompt content
# ---------------------------------------------------------------------------

class TestActionPreparationSystemPrompt:
    def _p(self) -> str:
        return ACTION_PREPARATION_SYSTEM_PROMPT

    def test_is_non_empty_string(self):
        assert isinstance(self._p(), str) and len(self._p()) > 50

    def test_explicitly_prohibits_create_commitment(self):
        assert "create_commitment" in self._p()
        assert "not available" in self._p().lower() or "do not" in self._p().lower()

    def test_explicitly_prohibits_update_commitment(self):
        assert "update_commitment" in self._p()

    def test_explicitly_prohibits_search_messages(self):
        assert "search_messages" in self._p()

    def test_instructs_not_to_change_status(self):
        p = self._p().lower()
        assert "read-only" in p or "do not change" in p or "do not alter" in p

    def test_instructs_to_call_get_open_commitments_first(self):
        assert "get_open_commitments" in self._p()

    def test_instructs_to_call_search_documents(self):
        assert "search_documents" in self._p()

    def test_instructs_to_call_get_document(self):
        assert "get_document" in self._p()

    def test_instructs_to_focus_on_ready_to_act(self):
        assert "READY_TO_ACT" in self._p()

    def test_warns_against_inventing_information(self):
        p = self._p().lower()
        assert "invent" in p or "do not invent" in p

    def test_instructs_to_verify_relevance(self):
        p = self._p().lower()
        assert "relevant" in p

    def test_instructs_to_report_missing_info(self):
        p = self._p().lower()
        assert "missing" in p


# ---------------------------------------------------------------------------
# Agent construction (no real Gemini call)
# ---------------------------------------------------------------------------

class TestBuildActionPreparer:
    def test_constructs_with_fake_key(self):
        agent = build_action_preparer(api_key="fake-key")
        assert isinstance(agent, Agent)

    def test_does_not_raise_with_explicit_key(self):
        build_action_preparer(api_key="fake-key-for-testing")

    def test_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            build_action_preparer()

    def test_reads_key_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-fake-key")
        agent = build_action_preparer()
        assert isinstance(agent, Agent)


# ---------------------------------------------------------------------------
# Demo scenario: store behavior (deterministic, no Gemini)
# ---------------------------------------------------------------------------

class TestDemoScenario:
    """Verify the store invariants expected of a read-only workflow."""

    def test_seed_creates_exactly_one_commitment(self):
        _seed()
        assert len(commitment_store) == 1

    def test_seeded_commitment_is_ready_to_act(self):
        c = _seed()
        assert c.status is S.READY_TO_ACT

    def test_seeded_commitment_has_correct_action(self):
        c = _seed()
        assert c.action == "Send the Q3 financial report"

    def test_seeded_commitment_has_correct_owner(self):
        c = _seed()
        assert c.owner == "bob"

    def test_seeded_commitment_has_correct_recipient(self):
        c = _seed()
        assert c.recipient == "alice"

    def test_seeded_commitment_has_expected_id(self):
        c = _seed()
        assert c.id == "demo-q3-commitment"

    def test_seeded_commitment_has_context(self):
        c = _seed()
        assert c.context is not None and len(c.context) > 0

    def test_seeded_commitment_has_next_action(self):
        c = _seed()
        assert c.next_action is not None and len(c.next_action) > 0

    def test_read_only_tools_cannot_change_status(self):
        """Structural guarantee: update_commitment is not in ACTION_PREPARATION_TOOLS."""
        tool_names = {t.__name__ for t in ACTION_PREPARATION_TOOLS}
        assert "update_commitment" not in tool_names

    def test_read_only_tools_cannot_create_commitment(self):
        """Structural guarantee: create_commitment is not in ACTION_PREPARATION_TOOLS."""
        tool_names = {t.__name__ for t in ACTION_PREPARATION_TOOLS}
        assert "create_commitment" not in tool_names

    def test_commitment_status_unchanged_after_get_open_commitments(self):
        """Calling get_open_commitments is read-only and must not change state."""
        import json
        c = _seed()
        result = json.loads(get_open_commitments())
        stored = commitment_store.get(c.id)
        assert stored.status is S.READY_TO_ACT
        assert result["count"] == 1

    def test_store_size_unchanged_after_get_open_commitments(self):
        import json
        _seed()
        json.loads(get_open_commitments())
        assert len(commitment_store) == 1

    def test_search_documents_does_not_touch_commitment_store(self):
        import json
        _seed()
        before = len(commitment_store)
        json.loads(search_documents(query="Q3 financial figures"))
        assert len(commitment_store) == before

    def test_get_document_does_not_touch_commitment_store(self):
        import json
        _seed()
        before = len(commitment_store)
        json.loads(get_document(document_id="doc-q3-figures"))
        assert len(commitment_store) == before