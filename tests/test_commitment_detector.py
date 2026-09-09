"""Tests for the commitment-detection agent configuration.

All tests are deterministic and do NOT call Gemini.
We test:
  - the public constants (tool list, system prompt) that drive the agent
  - that build_commitment_detector() constructs an Agent without error
    when given an explicit fake key
  - that it raises RuntimeError when no key is available
"""
from __future__ import annotations

import pytest

from loose_ends.agent import (
    COMMITMENT_DETECTION_TOOLS,
    COMMITMENT_DETECTION_SYSTEM_PROMPT,
    build_commitment_detector,
    build_agent,
)
from loose_ends.commitment_tools import (
    create_commitment,
    get_open_commitments,
    update_commitment,
)
from loose_ends.messages.search_tool import search_messages
from strands import Agent


# ---------------------------------------------------------------------------
# Tool list
# ---------------------------------------------------------------------------

class TestCommitmentDetectionTools:
    """Tests against the exported COMMITMENT_DETECTION_TOOLS list.

    This validates configuration without constructing an Agent or calling Gemini.
    """

    def _names(self) -> set[str]:
        return {t.__name__ for t in COMMITMENT_DETECTION_TOOLS}

    def test_tool_list_contains_search_messages(self):
        assert "search_messages" in self._names()

    def test_tool_list_contains_get_open_commitments(self):
        assert "get_open_commitments" in self._names()

    def test_tool_list_contains_create_commitment(self):
        assert "create_commitment" in self._names()

    def test_tool_list_has_exactly_four_tools(self):
        assert len(COMMITMENT_DETECTION_TOOLS) == 4

    def test_all_tools_are_callable(self):
        for t in COMMITMENT_DETECTION_TOOLS:
            assert callable(t), f"{t} is not callable"

    def test_search_messages_is_the_correct_object(self):
        assert search_messages in COMMITMENT_DETECTION_TOOLS

    def test_get_open_commitments_is_the_correct_object(self):
        assert get_open_commitments in COMMITMENT_DETECTION_TOOLS

    def test_create_commitment_is_the_correct_object(self):
        assert create_commitment in COMMITMENT_DETECTION_TOOLS

    def test_update_commitment_is_the_correct_object(self):
        assert update_commitment in COMMITMENT_DETECTION_TOOLS


# ---------------------------------------------------------------------------
# System prompt content
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    """Verify the prompt contains the required guidance."""

    def _prompt(self) -> str:
        return COMMITMENT_DETECTION_SYSTEM_PROMPT

    def test_prompt_is_non_empty_string(self):
        assert isinstance(self._prompt(), str)
        assert len(self._prompt()) > 50

    def test_prompt_mentions_commitment(self):
        assert "commitment" in self._prompt().lower()

    def test_prompt_instructs_to_check_existing_before_creating(self):
        p = self._prompt().lower()
        # Must mention checking existing commitments
        assert "get_open_commitments" in p or "already" in p

    def test_prompt_instructs_to_use_create_commitment_tool(self):
        assert "create_commitment" in self._prompt()

    def test_prompt_instructs_to_search_messages(self):
        assert "search_messages" in self._prompt()

    def test_prompt_defines_what_is_not_a_commitment(self):
        p = self._prompt().lower()
        # Must warn about requests / questions not being commitments
        assert "request" in p or "question" in p or "not a commitment" in p

    def test_prompt_mentions_owner(self):
        assert "owner" in self._prompt().lower()

    def test_prompt_mentions_dependency(self):
        assert "dependency" in self._prompt().lower()

    def test_prompt_warns_against_inventing_fields(self):
        p = self._prompt().lower()
        assert "invent" in p or "do not" in p or "not supported" in p


# ---------------------------------------------------------------------------
# Agent construction (no real Gemini call)
# ---------------------------------------------------------------------------

class TestBuildCommitmentDetector:
    """Test the factory function using a fake API key.

    GeminiModel stores the key but does not validate it at construction time,
    so passing a fake key is safe here -- no network requests are made.
    """

    def test_build_returns_agent_instance(self):
        agent = build_commitment_detector(api_key="fake-key-for-testing")
        assert isinstance(agent, Agent)

    def test_build_with_explicit_key_does_not_raise(self):
        # Should construct without error
        build_commitment_detector(api_key="fake-key-for-testing")

    def test_build_without_key_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            build_commitment_detector()

    def test_build_reads_key_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-fake-key")
        agent = build_commitment_detector()
        assert isinstance(agent, Agent)


# ---------------------------------------------------------------------------
# Existing PoC agent is not broken
# ---------------------------------------------------------------------------

class TestExistingPoCAgetUnchanged:
    """Ensure build_agent() still works exactly as before."""

    def test_build_agent_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            build_agent()

    def test_build_agent_constructs_with_env_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-poc-key")
        agent = build_agent()
        assert isinstance(agent, Agent)