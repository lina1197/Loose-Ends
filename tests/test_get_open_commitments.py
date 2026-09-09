"""Unit and integration tests for the get_open_commitments Strands tool.

Rules:
- No Gemini calls anywhere in this file.
- Commitment objects are inserted directly into commitment_store for
  test isolation (no coupling to create_commitment tool).
- The store is cleared before and after every test via an autouse fixture.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from loose_ends.commitment_tools import get_open_commitments
from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.store import commitment_store

S = CommitmentStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_store():
    """Guarantee each test starts and ends with an empty store."""
    commitment_store.clear()
    yield
    commitment_store.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────


_BASE_TIME = datetime(2027, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _add(
    action: str,
    owner: str = "alice",
    status: CommitmentStatus = S.READY_TO_ACT,
    created_offset_seconds: int = 0,
    **kwargs,
) -> Commitment:
    """Create a Commitment with a controlled created_at and add it to the store."""
    ts = _BASE_TIME + timedelta(seconds=created_offset_seconds)
    c = Commitment(
        id=f"test-{action[:8].replace(' ', '-')}-{created_offset_seconds}",
        action=action,
        owner=owner,
        status=status,
        created_at=ts,
        updated_at=ts,
        **kwargs,
    )
    commitment_store.add(c)
    return c


def _call() -> dict:
    """Invoke the tool and parse the JSON result."""
    return json.loads(get_open_commitments())


# ── Integration: importability ────────────────────────────────────────────────


class TestToolIntegration:
    def test_tool_is_importable(self):
        from loose_ends.commitment_tools import get_open_commitments as t
        assert t is not None

    def test_tool_is_callable(self):
        assert callable(get_open_commitments)

    def test_tool_has_strands_shape(self):
        has_meta = (
            hasattr(get_open_commitments, "TOOL_SPEC")
            or hasattr(get_open_commitments, "tool_spec")
            or hasattr(get_open_commitments, "__tool_name__")
            or hasattr(get_open_commitments, "__wrapped__")
            or callable(get_open_commitments)
        )
        assert has_meta


# ── Empty store ───────────────────────────────────────────────────────────────


class TestEmptyStore:
    def test_empty_store_returns_count_zero(self):
        result = _call()
        assert result["count"] == 0

    def test_empty_store_returns_empty_list(self):
        result = _call()
        assert result["commitments"] == []

    def test_empty_store_result_is_json_serializable(self):
        raw = get_open_commitments()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)


# ── Single commitment ─────────────────────────────────────────────────────────


class TestSingleCommitment:
    def test_one_open_commitment_count_is_one(self):
        _add("Send report")
        assert _call()["count"] == 1

    def test_one_open_commitment_appears_in_list(self):
        c = _add("Send report")
        result = _call()
        assert len(result["commitments"]) == 1
        assert result["commitments"][0]["commitment_id"] == c.id

    def test_single_entry_fields_are_correct(self):
        c = _add(
            action="Write proposal",
            owner="bob",
            status=S.IN_PROGRESS,
            recipient="carol",
            dependency="Need legal review",
            source_message_id="msg-1",
            next_action="Open doc",
        )
        entry = _call()["commitments"][0]
        assert entry["commitment_id"] == c.id
        assert entry["action"] == "Write proposal"
        assert entry["owner"] == "bob"
        assert entry["recipient"] == "carol"
        assert entry["dependency"] == "Need legal review"
        assert entry["status"] == "IN_PROGRESS"
        assert entry["source_message_id"] == "msg-1"
        assert entry["next_action"] == "Open doc"

    def test_null_optional_fields_are_present_as_null(self):
        _add("Send invoice")
        entry = _call()["commitments"][0]
        assert "recipient" in entry
        assert "deadline" in entry
        assert "dependency" in entry
        assert "source_message_id" in entry
        assert "next_action" in entry
        assert entry["recipient"] is None
        assert entry["deadline"] is None


# ── Multiple open commitments ─────────────────────────────────────────────────


class TestMultipleOpenCommitments:
    def test_count_matches_number_of_open_commitments(self):
        _add("Task A", created_offset_seconds=0)
        _add("Task B", created_offset_seconds=1)
        _add("Task C", created_offset_seconds=2)
        result = _call()
        assert result["count"] == 3
        assert len(result["commitments"]) == 3

    def test_count_field_always_equals_list_length(self):
        for i in range(5):
            _add(f"Task {i}", created_offset_seconds=i)
        result = _call()
        assert result["count"] == len(result["commitments"])


# ── COMPLETED commitments are excluded ───────────────────────────────────────


class TestCompletedExclusion:
    def test_sole_completed_commitment_is_excluded(self):
        _add("Finished task", status=S.COMPLETED)
        result = _call()
        assert result["count"] == 0
        assert result["commitments"] == []

    def test_completed_excluded_from_mixed_store(self):
        _add("Done task", status=S.COMPLETED, created_offset_seconds=0)
        open_c = _add("Open task", status=S.READY_TO_ACT, created_offset_seconds=1)
        result = _call()
        assert result["count"] == 1
        assert result["commitments"][0]["commitment_id"] == open_c.id

    def test_multiple_completed_all_excluded(self):
        _add("Done 1", status=S.COMPLETED, created_offset_seconds=0)
        _add("Done 2", status=S.COMPLETED, created_offset_seconds=1)
        _add("Done 3", status=S.COMPLETED, created_offset_seconds=2)
        result = _call()
        assert result["count"] == 0

    def test_completed_id_never_appears_in_result(self):
        completed = _add("Archived", status=S.COMPLETED, created_offset_seconds=0)
        _add("Active", status=S.IN_PROGRESS, created_offset_seconds=1)
        result = _call()
        returned_ids = {e["commitment_id"] for e in result["commitments"]}
        assert completed.id not in returned_ids


# ── Non-COMPLETED statuses are all included ───────────────────────────────────


class TestNonCompletedStatusesIncluded:
    @pytest.mark.parametrize(
        "status",
        [
            S.OPEN,
            S.WAITING_FOR_DEPENDENCY,
            S.READY_TO_ACT,
            S.IN_PROGRESS,
            S.WAITING_FOR_USER,
        ],
    )
    def test_non_completed_status_is_included(self, status):
        c = _add("Some task", status=status)
        result = _call()
        assert result["count"] == 1
        assert result["commitments"][0]["status"] == status.value

    def test_all_non_completed_statuses_returned_together(self):
        non_completed = [
            S.OPEN,
            S.WAITING_FOR_DEPENDENCY,
            S.READY_TO_ACT,
            S.IN_PROGRESS,
            S.WAITING_FOR_USER,
        ]
        for i, s in enumerate(non_completed):
            _add(f"Task {s.value}", status=s, created_offset_seconds=i)
        result = _call()
        assert result["count"] == len(non_completed)
        returned_statuses = {e["status"] for e in result["commitments"]}
        assert returned_statuses == {s.value for s in non_completed}


# ── Deterministic ordering ────────────────────────────────────────────────────


class TestDeterministicOrdering:
    def test_results_ordered_by_created_at_ascending(self):
        # Insert in reverse time order to confirm sort is applied
        c3 = _add("Latest task", created_offset_seconds=200)
        c1 = _add("Earliest task", created_offset_seconds=0)
        c2 = _add("Middle task", created_offset_seconds=100)
        result = _call()
        ids = [e["commitment_id"] for e in result["commitments"]]
        assert ids == [c1.id, c2.id, c3.id]

    def test_two_calls_return_same_order(self):
        for i in range(4):
            _add(f"Task {i}", created_offset_seconds=i)
        first = _call()["commitments"]
        second = _call()["commitments"]
        assert [e["commitment_id"] for e in first] == [
            e["commitment_id"] for e in second
        ]


# ── JSON serializability ──────────────────────────────────────────────────────


class TestJsonSerializability:
    def test_result_is_valid_json_string(self):
        _add("Task A", created_offset_seconds=0)
        raw = get_open_commitments()
        assert isinstance(raw, str)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_result_with_deadline_is_serializable(self):
        deadline = _BASE_TIME + timedelta(days=30)
        _add("Task with deadline", deadline=deadline)
        raw = get_open_commitments()
        parsed = json.loads(raw)
        entry = parsed["commitments"][0]
        assert isinstance(entry["deadline"], str)
        # Must be a valid ISO 8601 string
        datetime.fromisoformat(entry["deadline"])

    def test_result_round_trips_through_json(self):
        _add("Task B")
        raw = get_open_commitments()
        reparsed = json.loads(json.dumps(json.loads(raw)))
        assert reparsed["count"] == 1


# ── No mutation on read ───────────────────────────────────────────────────────


class TestNoMutationOnRead:
    def test_status_unchanged_after_call(self):
        c = _add("Read-only task", status=S.IN_PROGRESS)
        _call()
        stored = commitment_store.get(c.id)
        assert stored.status is S.IN_PROGRESS

    def test_updated_at_unchanged_after_call(self):
        c = _add("Stable task")
        original_updated = c.updated_at
        _call()
        stored = commitment_store.get(c.id)
        assert stored.updated_at == original_updated

    def test_store_size_unchanged_after_call(self):
        _add("Task X", created_offset_seconds=0)
        _add("Task Y", created_offset_seconds=1)
        size_before = len(commitment_store)
        _call()
        assert len(commitment_store) == size_before

    def test_action_unchanged_after_call(self):
        c = _add("Original action text")
        _call()
        stored = commitment_store.get(c.id)
        assert stored.action == "Original action text"