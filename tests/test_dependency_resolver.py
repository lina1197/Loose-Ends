"""Tests for the dependency-resolution workflow and its architectural separation.

All tests are deterministic and do NOT call Gemini.

Coverage:
  - DEPENDENCY_RESOLUTION_TOOLS contains the right tools
  - create_commitment is absent from DEPENDENCY_RESOLUTION_TOOLS
  - COMMITMENT_DETECTION_TOOLS still contains create_commitment
  - System prompt explicitly prohibits create_commitment
  - build_dependency_resolver() constructs without error
  - Demo scenario: seed -> update -> verify (no Gemini call)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from strands import Agent

from loose_ends.agent import (
    COMMITMENT_DETECTION_TOOLS,
    DEPENDENCY_RESOLUTION_TOOLS,
    DEPENDENCY_RESOLUTION_SYSTEM_PROMPT,
    build_dependency_resolver,
    build_commitment_detector,
)
from loose_ends.commitment_tools import (
    create_commitment,
    get_open_commitments,
    update_commitment,
)
from loose_ends.messages.search_tool import search_messages
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
    """Create the canonical demo commitment and add it to the store."""
    ts = datetime(2027, 9, 3, 10, 45, 0, tzinfo=timezone.utc)
    c = Commitment(
        id="demo-hotfix-commitment",
        action="Deploy the hotfix to production",
        owner="dave",
        recipient="carol",
        status=S.WAITING_FOR_DEPENDENCY,
        dependency="QA approval of the build",
        source_message_id="msg-006",
        created_at=ts,
        updated_at=ts,
    )
    commitment_store.add(c)
    return c


# ---------------------------------------------------------------------------
# Dependency-resolution tool list
# ---------------------------------------------------------------------------

class TestDependencyResolutionTools:
    def _names(self) -> set[str]:
        return {t.__name__ for t in DEPENDENCY_RESOLUTION_TOOLS}

    def test_has_search_messages(self):
        assert "search_messages" in self._names()

    def test_has_get_open_commitments(self):
        assert "get_open_commitments" in self._names()

    def test_has_update_commitment(self):
        assert "update_commitment" in self._names()

    def test_does_not_have_create_commitment(self):
        assert "create_commitment" not in self._names()

    def test_has_exactly_three_tools(self):
        assert len(DEPENDENCY_RESOLUTION_TOOLS) == 3

    def test_search_messages_is_the_correct_object(self):
        assert search_messages in DEPENDENCY_RESOLUTION_TOOLS

    def test_get_open_commitments_is_the_correct_object(self):
        assert get_open_commitments in DEPENDENCY_RESOLUTION_TOOLS

    def test_update_commitment_is_the_correct_object(self):
        assert update_commitment in DEPENDENCY_RESOLUTION_TOOLS

    def test_create_commitment_object_is_absent(self):
        assert create_commitment not in DEPENDENCY_RESOLUTION_TOOLS

    def test_all_tools_are_callable(self):
        for t in DEPENDENCY_RESOLUTION_TOOLS:
            assert callable(t)


# ---------------------------------------------------------------------------
# Architectural separation from commitment-detection workflow
# ---------------------------------------------------------------------------

class TestArchitecturalSeparation:
    def test_detection_has_create_commitment(self):
        names = {t.__name__ for t in COMMITMENT_DETECTION_TOOLS}
        assert "create_commitment" in names

    def test_resolution_lacks_create_commitment(self):
        names = {t.__name__ for t in DEPENDENCY_RESOLUTION_TOOLS}
        assert "create_commitment" not in names

    def test_tool_lists_are_different_objects(self):
        assert DEPENDENCY_RESOLUTION_TOOLS is not COMMITMENT_DETECTION_TOOLS

    def test_resolution_tools_are_subset_of_detection_tools(self):
        res_names = {t.__name__ for t in DEPENDENCY_RESOLUTION_TOOLS}
        det_names = {t.__name__ for t in COMMITMENT_DETECTION_TOOLS}
        assert res_names.issubset(det_names)

    def test_detection_has_strictly_more_tools_than_resolution(self):
        assert len(COMMITMENT_DETECTION_TOOLS) > len(DEPENDENCY_RESOLUTION_TOOLS)

    def test_detection_has_four_tools(self):
        assert len(COMMITMENT_DETECTION_TOOLS) == 4

    def test_resolution_has_three_tools(self):
        assert len(DEPENDENCY_RESOLUTION_TOOLS) == 3


# ---------------------------------------------------------------------------
# Dependency-resolution system prompt
# ---------------------------------------------------------------------------

class TestDependencyResolutionSystemPrompt:
    def _p(self) -> str:
        return DEPENDENCY_RESOLUTION_SYSTEM_PROMPT

    def test_is_non_empty_string(self):
        assert isinstance(self._p(), str) and len(self._p()) > 50

    def test_explicitly_prohibits_create_commitment(self):
        p = self._p().lower()
        # Must say create_commitment is not available / must not be called
        assert "create_commitment" in self._p()
        assert ("not available" in p or "must not" in p or "do not" in p)

    def test_mentions_update_commitment(self):
        assert "update_commitment" in self._p()

    def test_mentions_ready_to_act(self):
        assert "READY_TO_ACT" in self._p()

    def test_instructs_to_check_waiting_for_dependency(self):
        assert "WAITING_FOR_DEPENDENCY" in self._p()

    def test_warns_against_keyword_overlap(self):
        p = self._p().lower()
        assert "keyword" in p or "keyword overlap" in p or "keyword" in p

    def test_instructs_not_to_invent_evidence(self):
        p = self._p().lower()
        assert "invent" in p or "assume" in p

    def test_instructs_to_search_messages(self):
        assert "search_messages" in self._p()

    def test_instructs_to_call_get_open_commitments(self):
        assert "get_open_commitments" in self._p()


# ---------------------------------------------------------------------------
# Agent construction (no real Gemini call)
# ---------------------------------------------------------------------------

class TestBuildDependencyResolver:
    def test_constructs_with_fake_key(self):
        agent = build_dependency_resolver(api_key="fake-key")
        assert isinstance(agent, Agent)

    def test_does_not_raise_with_explicit_key(self):
        build_dependency_resolver(api_key="fake-key-for-testing")

    def test_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            build_dependency_resolver()

    def test_reads_key_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-fake-key")
        agent = build_dependency_resolver()
        assert isinstance(agent, Agent)

    def test_returns_agent_instance(self):
        agent = build_dependency_resolver(api_key="x")
        assert isinstance(agent, Agent)


# ---------------------------------------------------------------------------
# Demo scenario: store behavior (deterministic, no Gemini)
# ---------------------------------------------------------------------------

class TestDemoScenario:
    """Tests that mirror the expected behavior of the demo script
    without making any Gemini API calls."""

    def test_seed_creates_exactly_one_commitment(self):
        _seed()
        assert len(commitment_store) == 1

    def test_seeded_commitment_is_waiting_for_dependency(self):
        c = _seed()
        assert c.status is S.WAITING_FOR_DEPENDENCY

    def test_seeded_commitment_has_correct_action(self):
        c = _seed()
        assert c.action == "Deploy the hotfix to production"

    def test_seeded_commitment_has_correct_owner(self):
        c = _seed()
        assert c.owner == "dave"

    def test_seeded_commitment_has_correct_recipient(self):
        c = _seed()
        assert c.recipient == "carol"

    def test_seeded_commitment_has_qa_dependency(self):
        c = _seed()
        assert "QA" in c.dependency

    def test_seeded_commitment_has_expected_id(self):
        c = _seed()
        assert c.id == "demo-hotfix-commitment"

    def test_update_transitions_to_ready_to_act(self):
        """Simulate what the resolution agent does: call update_commitment."""
        import json
        c = _seed()
        result = json.loads(
            update_commitment(commitment_id=c.id, status="READY_TO_ACT")
        )
        assert "error" not in result
        assert result["status"] == "READY_TO_ACT"

    def test_store_has_one_commitment_after_update(self):
        import json
        c = _seed()
        update_commitment(commitment_id=c.id, status="READY_TO_ACT")
        assert len(commitment_store) == 1

    def test_commitment_status_is_ready_after_update(self):
        import json
        c = _seed()
        update_commitment(commitment_id=c.id, status="READY_TO_ACT")
        stored = commitment_store.get(c.id)
        assert stored.status is S.READY_TO_ACT

    def test_no_additional_commitment_created_by_update(self):
        import json
        _seed()
        update_commitment(
            commitment_id="demo-hotfix-commitment",
            status="READY_TO_ACT",
        )
        # Only the seeded commitment should exist
        assert len(commitment_store) == 1

    def test_create_commitment_not_in_resolution_tool_list(self):
        """Structural guarantee: resolution workflow cannot call create_commitment."""
        tool_names = {t.__name__ for t in DEPENDENCY_RESOLUTION_TOOLS}
        assert "create_commitment" not in tool_names