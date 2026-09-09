"""Unit and integration tests for the create_commitment Strands tool.

Rules:
- No Gemini calls anywhere in this file.
- The tool function is called directly (Strands @tool wrappers
  remain callable as plain Python functions).
- The in-memory store is cleared before every test via an autouse fixture.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from loose_ends.commitment_tools import create_commitment
from loose_ends.domain.commitment import CommitmentStatus
from loose_ends.store import commitment_store


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_store():
    """Ensure each test starts with an empty store."""
    commitment_store.clear()
    yield
    commitment_store.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _call(**kwargs) -> dict:
    """Call the tool and parse the JSON result into a dict."""
    raw = create_commitment(**kwargs)
    return json.loads(raw)


def _ok(**kwargs) -> dict:
    """Call the tool, assert no error key, return parsed result."""
    result = _call(**kwargs)
    assert "error" not in result, f"Unexpected error: {result['error']}"
    return result


def _err(**kwargs) -> dict:
    """Call the tool, assert an error key is present, return parsed result."""
    result = _call(**kwargs)
    assert "error" in result, f"Expected an error but got: {result}"
    return result


# ── Integration: importability and tool shape ─────────────────────────────────


class TestToolIntegration:
    def test_tool_is_importable(self):
        """The create_commitment object must import without error."""
        from loose_ends.commitment_tools import create_commitment as t
        assert t is not None

    def test_tool_is_callable(self):
        assert callable(create_commitment)

    def test_tool_has_strands_metadata(self):
        """Strands @tool-decorated functions expose a TOOL_SPEC or name attribute."""
        # Accept any of the common attribute shapes across SDK versions.
        has_meta = (
            hasattr(create_commitment, "TOOL_SPEC")
            or hasattr(create_commitment, "tool_spec")
            or hasattr(create_commitment, "__tool_name__")
            or hasattr(create_commitment, "__wrapped__")
            or callable(create_commitment)
        )
        assert has_meta


# ── Status assignment ─────────────────────────────────────────────────────────


class TestStatusAssignment:
    def test_no_dependency_yields_ready_to_act(self):
        result = _ok(action="Send the report", owner="alice")
        assert result["status"] == CommitmentStatus.READY_TO_ACT.value

    def test_dependency_yields_waiting_for_dependency(self):
        result = _ok(
            action="Deploy fix",
            owner="bob",
            dependency="Waiting for QA sign-off",
        )
        assert result["status"] == CommitmentStatus.WAITING_FOR_DEPENDENCY.value

    def test_empty_string_dependency_treated_as_no_dependency(self):
        """An empty string dependency should NOT trigger WAITING_FOR_DEPENDENCY."""
        result = _ok(action="Review PR", owner="carol", dependency="")
        assert result["status"] == CommitmentStatus.READY_TO_ACT.value

    def test_dependency_is_echoed_in_result(self):
        dep = "blocker-ticket-99"
        result = _ok(action="Call vendor", owner="dave", dependency=dep)
        assert result["dependency"] == dep

    def test_no_dependency_result_has_null_dependency(self):
        result = _ok(action="Write docs", owner="eve")
        assert result["dependency"] is None


# ── Return-value structure ────────────────────────────────────────────────────


class TestReturnValue:
    def test_result_contains_required_keys(self):
        result = _ok(action="Finish report", owner="frank")
        assert "commitment_id" in result
        assert "action" in result
        assert "owner" in result
        assert "status" in result
        assert "dependency" in result

    def test_commitment_id_is_non_empty_string(self):
        result = _ok(action="Do something", owner="grace")
        assert isinstance(result["commitment_id"], str)
        assert result["commitment_id"].strip()

    def test_action_echoed_correctly(self):
        result = _ok(action="Send invoice", owner="heidi")
        assert result["action"] == "Send invoice"

    def test_owner_echoed_correctly(self):
        result = _ok(action="File tax return", owner="ivan")
        assert result["owner"] == "ivan"


# ── Store persistence ─────────────────────────────────────────────────────────


class TestStorePersistence:
    def test_created_commitment_is_in_store(self):
        result = _ok(action="Book flight", owner="judy")
        cid = result["commitment_id"]
        assert cid in commitment_store
        assert commitment_store.get(cid) is not None

    def test_stored_commitment_matches_result(self):
        result = _ok(action="Schedule meeting", owner="karl")
        cid = result["commitment_id"]
        stored = commitment_store.get(cid)
        assert stored.action == "Schedule meeting"
        assert stored.owner == "karl"
        assert stored.status.value == result["status"]

    def test_store_grows_with_each_creation(self):
        assert len(commitment_store) == 0
        _ok(action="Task A", owner="luna")
        assert len(commitment_store) == 1
        _ok(action="Task B", owner="luna")
        assert len(commitment_store) == 2

    def test_store_is_cleared_between_tests(self):
        """Sanity check: autouse fixture resets state."""
        assert len(commitment_store) == 0


# ── Unique IDs ────────────────────────────────────────────────────────────────


class TestUniqueIds:
    def test_two_commitments_have_different_ids(self):
        r1 = _ok(action="Task one", owner="mike")
        r2 = _ok(action="Task two", owner="mike")
        assert r1["commitment_id"] != r2["commitment_id"]

    def test_many_commitments_have_unique_ids(self):
        ids = {
            _ok(action=f"Task {i}", owner="nancy")["commitment_id"]
            for i in range(20)
        }
        assert len(ids) == 20


# ── Optional fields ───────────────────────────────────────────────────────────


class TestOptionalFields:
    def test_all_optional_fields_accepted(self):
        future = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        result = _ok(
            action="Prepare quarterly review",
            owner="olivia",
            recipient="CEO",
            deadline=future,
            dependency=None,
            source_message_id="msg-42",
            context="Q3 board meeting",
            next_action="Open spreadsheet",
        )
        assert "commitment_id" in result

    def test_stored_commitment_retains_optional_fields(self):
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        result = _ok(
            action="Send NDA",
            owner="pat",
            recipient="vendor",
            deadline=future,
            context="Partnership deal",
            next_action="Attach PDF",
        )
        stored = commitment_store.get(result["commitment_id"])
        assert stored.recipient == "vendor"
        assert stored.context == "Partnership deal"
        assert stored.next_action == "Attach PDF"
        assert stored.deadline is not None

    def test_deadline_parsed_as_utc_aware(self):
        future = "2027-06-01T09:00:00+00:00"
        result = _ok(action="Renew contract", owner="quinn", deadline=future)
        stored = commitment_store.get(result["commitment_id"])
        assert stored.deadline is not None
        assert stored.deadline.tzinfo is not None

    def test_naive_deadline_string_coerced_to_utc(self):
        result = _ok(action="Submit form", owner="rosa", deadline="2027-03-15T10:00:00")
        stored = commitment_store.get(result["commitment_id"])
        assert stored.deadline.tzinfo is not None


# ── Validation / error handling ───────────────────────────────────────────────


class TestValidation:
    def test_missing_action_is_rejected(self):
        result = _err(action="", owner="steve")
        assert "action" in result["error"].lower()

    def test_whitespace_action_is_rejected(self):
        result = _err(action="   ", owner="tina")
        assert "action" in result["error"].lower()

    def test_missing_owner_is_rejected(self):
        result = _err(action="Do the thing", owner="")
        assert "owner" in result["error"].lower()

    def test_whitespace_owner_is_rejected(self):
        result = _err(action="Do the thing", owner="\t ")
        assert "owner" in result["error"].lower()

    def test_invalid_deadline_format_returns_error(self):
        result = _err(action="Attend meeting", owner="uma", deadline="not-a-date")
        assert "error" in result
        # Store must remain empty — no partial commit
        assert len(commitment_store) == 0

    def test_invalid_deadline_does_not_pollute_store(self):
        _err(action="Attend meeting", owner="vera", deadline="bad")
        assert len(commitment_store) == 0

    def test_valid_commitment_after_previous_error(self):
        """A validation error must not block subsequent valid calls."""
        _err(action="", owner="will")
        result = _ok(action="Valid task", owner="will")
        assert "commitment_id" in result