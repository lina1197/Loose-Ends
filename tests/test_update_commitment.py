"""Unit tests for the update_commitment Strands tool.

All tests are deterministic and do NOT call Gemini.
Commitments are inserted directly into commitment_store for isolation.
The store is cleared before and after every test via an autouse fixture.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from loose_ends.commitment_tools import update_commitment
from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.store import commitment_store

S = CommitmentStatus
_BASE = datetime(2027, 9, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_store():
    commitment_store.clear()
    yield
    commitment_store.clear()


def _add(
    action: str = "Do something",
    owner: str = "alice",
    status: CommitmentStatus = S.READY_TO_ACT,
    dependency: str | None = None,
    next_action: str | None = None,
    context: str | None = None,
    offset: int = 0,
) -> Commitment:
    ts = _BASE + timedelta(seconds=offset)
    c = Commitment(
        id=f"test-{offset}-{action[:8].replace(' ', '-')}",
        action=action,
        owner=owner,
        status=status,
        dependency=dependency,
        next_action=next_action,
        context=context,
        created_at=ts,
        updated_at=ts,
    )
    commitment_store.add(c)
    return c


def _call(**kwargs) -> dict:
    return json.loads(update_commitment(**kwargs))


# ---------------------------------------------------------------------------
# Tool importability
# ---------------------------------------------------------------------------

class TestToolImport:
    def test_tool_is_importable(self):
        from loose_ends.commitment_tools import update_commitment as t
        assert t is not None

    def test_tool_is_callable(self):
        assert callable(update_commitment)


# ---------------------------------------------------------------------------
# Unknown commitment ID
# ---------------------------------------------------------------------------

class TestUnknownId:
    def test_unknown_id_returns_error(self):
        result = _call(commitment_id="no-such-id")
        assert "error" in result

    def test_unknown_id_error_mentions_id(self):
        result = _call(commitment_id="ghost-abc-123")
        assert "ghost-abc-123" in result["error"]

    def test_unknown_id_does_not_mutate_store(self):
        _add(offset=0)
        before = len(commitment_store)
        _call(commitment_id="nonexistent")
        assert len(commitment_store) == before


# ---------------------------------------------------------------------------
# WAITING_FOR_DEPENDENCY -> READY_TO_ACT (the core step-7 transition)
# ---------------------------------------------------------------------------

class TestDependencyResolutionTransition:
    def test_waiting_to_ready_succeeds(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY, dependency="QA approval")
        result = _call(commitment_id=c.id, status="READY_TO_ACT")
        assert "error" not in result
        assert result["status"] == "READY_TO_ACT"

    def test_waiting_to_ready_updates_store(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY, dependency="QA approval")
        _call(commitment_id=c.id, status="READY_TO_ACT")
        stored = commitment_store.get(c.id)
        assert stored.status is S.READY_TO_ACT

    def test_updated_fields_contains_status(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY)
        result = _call(commitment_id=c.id, status="READY_TO_ACT")
        assert "status" in result["updated_fields"]

    def test_result_contains_commitment_id(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY)
        result = _call(commitment_id=c.id, status="READY_TO_ACT")
        assert result["commitment_id"] == c.id

    def test_result_is_json_serializable(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY)
        raw = update_commitment(commitment_id=c.id, status="READY_TO_ACT")
        assert isinstance(raw, str)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_result_round_trips_through_json(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY)
        raw = update_commitment(commitment_id=c.id, status="READY_TO_ACT")
        reparsed = json.loads(json.dumps(json.loads(raw)))
        assert reparsed["status"] == "READY_TO_ACT"


# ---------------------------------------------------------------------------
# Invalid status transitions are rejected
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    def test_completed_to_ready_rejected(self):
        c = _add(status=S.COMPLETED)
        result = _call(commitment_id=c.id, status="READY_TO_ACT")
        assert "error" in result

    def test_ready_to_waiting_rejected(self):
        c = _add(status=S.READY_TO_ACT)
        result = _call(commitment_id=c.id, status="WAITING_FOR_DEPENDENCY")
        assert "error" in result

    def test_invalid_transition_does_not_change_status(self):
        c = _add(status=S.COMPLETED)
        _call(commitment_id=c.id, status="READY_TO_ACT")
        stored = commitment_store.get(c.id)
        assert stored.status is S.COMPLETED

    def test_unknown_status_value_rejected(self):
        c = _add()
        result = _call(commitment_id=c.id, status="FLYING")
        assert "error" in result

    def test_unknown_status_does_not_mutate_store(self):
        c = _add()
        original_status = c.status
        _call(commitment_id=c.id, status="NONEXISTENT")
        stored = commitment_store.get(c.id)
        assert stored.status is original_status


# ---------------------------------------------------------------------------
# Updating next_action
# ---------------------------------------------------------------------------

class TestUpdateNextAction:
    def test_set_next_action(self):
        c = _add()
        result = _call(commitment_id=c.id, next_action="Open the dashboard")
        assert "error" not in result
        assert "next_action" in result["updated_fields"]

    def test_next_action_persisted_in_store(self):
        c = _add()
        _call(commitment_id=c.id, next_action="Open the dashboard")
        stored = commitment_store.get(c.id)
        assert stored.next_action == "Open the dashboard"

    def test_next_action_status_unchanged(self):
        c = _add(status=S.IN_PROGRESS)
        _call(commitment_id=c.id, next_action="Write summary")
        stored = commitment_store.get(c.id)
        assert stored.status is S.IN_PROGRESS


# ---------------------------------------------------------------------------
# Updating dependency field
# ---------------------------------------------------------------------------

class TestUpdateDependency:
    def test_set_dependency(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY)
        result = _call(commitment_id=c.id, dependency="Finance team sign-off")
        assert "error" not in result
        assert "dependency" in result["updated_fields"]

    def test_dependency_persisted_in_store(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY, dependency="Old dep")
        _call(commitment_id=c.id, dependency="New dep")
        stored = commitment_store.get(c.id)
        assert stored.dependency == "New dep"


# ---------------------------------------------------------------------------
# Updating context field
# ---------------------------------------------------------------------------

class TestUpdateContext:
    def test_set_context(self):
        c = _add()
        result = _call(commitment_id=c.id, context="Discussed in Monday standup")
        assert "error" not in result
        assert "context" in result["updated_fields"]

    def test_context_persisted_in_store(self):
        c = _add()
        _call(commitment_id=c.id, context="From meeting notes")
        stored = commitment_store.get(c.id)
        assert stored.context == "From meeting notes"


# ---------------------------------------------------------------------------
# Multiple fields updated in one call
# ---------------------------------------------------------------------------

class TestMultiFieldUpdate:
    def test_status_and_next_action_together(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY)
        result = _call(
            commitment_id=c.id,
            status="READY_TO_ACT",
            next_action="Run deployment script",
        )
        assert "error" not in result
        assert "status" in result["updated_fields"]
        assert "next_action" in result["updated_fields"]
        assert result["status"] == "READY_TO_ACT"

    def test_multi_field_persisted_in_store(self):
        c = _add(status=S.WAITING_FOR_DEPENDENCY)
        _call(
            commitment_id=c.id,
            status="READY_TO_ACT",
            next_action="Run deployment script",
            context="QA approved at 14:30",
        )
        stored = commitment_store.get(c.id)
        assert stored.status is S.READY_TO_ACT
        assert stored.next_action == "Run deployment script"
        assert stored.context == "QA approved at 14:30"


# ---------------------------------------------------------------------------
# No unintended mutation on error
# ---------------------------------------------------------------------------

class TestNoUnintendedMutation:
    def test_failed_transition_leaves_status_intact(self):
        c = _add(status=S.READY_TO_ACT)
        _call(commitment_id=c.id, status="WAITING_FOR_DEPENDENCY")
        assert commitment_store.get(c.id).status is S.READY_TO_ACT

    def test_failed_transition_leaves_action_intact(self):
        c = _add(action="Write the report", status=S.COMPLETED)
        _call(commitment_id=c.id, status="READY_TO_ACT")
        assert commitment_store.get(c.id).action == "Write the report"

    def test_store_size_unchanged_after_error(self):
        _add(offset=0)
        _add(offset=1)
        before = len(commitment_store)
        _call(commitment_id="nonexistent")
        assert len(commitment_store) == before


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------

class TestResultShape:
    def test_success_result_has_required_keys(self):
        c = _add()
        result = _call(commitment_id=c.id, next_action="Do it")
        assert "commitment_id" in result
        assert "updated_fields" in result
        assert "status" in result

    def test_error_result_has_error_key(self):
        result = _call(commitment_id="bad-id")
        assert "error" in result

    def test_updated_fields_is_list(self):
        c = _add()
        result = _call(commitment_id=c.id, next_action="Step 1")
        assert isinstance(result["updated_fields"], list)

    def test_no_op_call_returns_empty_updated_fields(self):
        c = _add()
        # Calling with no fields to change produces an empty updated_fields
        result = _call(commitment_id=c.id)
        assert result["updated_fields"] == []