"""Tests for Step 12: mark_completed and explicit approval flow."""

import json
from datetime import datetime, timezone

import pytest

from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.commitment_tools import (
    prepare_response,
    mark_completed,
    get_open_commitments,
)
from loose_ends.store import commitment_store
from loose_ends.agent import (
    COMMITMENT_DETECTION_TOOLS,
    DEPENDENCY_RESOLUTION_TOOLS,
    ACTION_PREPARATION_TOOLS,
    RESPONSE_PREPARATION_TOOLS,
)


@pytest.fixture(autouse=True)
def _clear_store():
    """Ensure a clean in-memory store before each test."""
    commitment_store.clear()
    yield
    commitment_store.clear()


def _make_commitment(
    status: CommitmentStatus = CommitmentStatus.READY_TO_ACT,
    id: str = "comm-123",
) -> Commitment:
    ts = datetime(2027, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    c = Commitment(
        id=id,
        action="Send Q3 financial report",
        owner="bob",
        recipient="alice",
        status=status,
        created_at=ts,
        updated_at=ts,
    )
    commitment_store.add(c)
    return c


# ---------------------------------------------------------------------------
# 1. Successful mark_completed
# ---------------------------------------------------------------------------

def test_successful_mark_completed():
    c = _make_commitment(CommitmentStatus.READY_TO_ACT)

    res_raw = mark_completed(c.id)
    res = json.loads(res_raw)

    assert "error" not in res
    assert res["commitment_id"] == c.id
    assert res["status"] == "COMPLETED"

    stored = commitment_store.get(c.id)
    assert stored is not None
    assert stored.status == CommitmentStatus.COMPLETED


# ---------------------------------------------------------------------------
# 2. Unknown commitment
# ---------------------------------------------------------------------------

def test_unknown_commitment():
    res_raw = mark_completed("nonexistent-id")
    res = json.loads(res_raw)

    assert "error" in res
    assert "nonexistent-id" in res["error"]


# ---------------------------------------------------------------------------
# 3. Invalid transition (e.g. already COMPLETED)
# ---------------------------------------------------------------------------

def test_invalid_transition():
    c = _make_commitment(CommitmentStatus.COMPLETED)

    res_raw = mark_completed(c.id)
    res = json.loads(res_raw)

    assert "error" in res
    assert "Cannot transition" in res["error"] or "terminal state" in res["error"]


# ---------------------------------------------------------------------------
# 4. No mutation on failure
# ---------------------------------------------------------------------------

def test_no_mutation_on_failure():
    c = _make_commitment(CommitmentStatus.COMPLETED)
    updated_at_before = c.updated_at

    res_raw = mark_completed(c.id)
    res = json.loads(res_raw)

    assert "error" in res
    stored = commitment_store.get(c.id)
    assert stored is not None
    assert stored.status == CommitmentStatus.COMPLETED
    assert stored.updated_at == updated_at_before


# ---------------------------------------------------------------------------
# 5. JSON-serializable result
# ---------------------------------------------------------------------------

def test_json_serializable_result():
    c = _make_commitment()

    res_raw = mark_completed(c.id)
    assert isinstance(res_raw, str)

    # Must parse cleanly without error
    parsed = json.loads(res_raw)
    assert isinstance(parsed, dict)
    assert parsed["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# 6. No completion before explicit approval
# ---------------------------------------------------------------------------

def test_no_completion_before_explicit_approval():
    c = _make_commitment(CommitmentStatus.READY_TO_ACT)

    # Prepare response draft
    draft_raw = prepare_response(c.id, "Draft figures: $4.2M")
    draft_res = json.loads(draft_raw)

    assert draft_res["status"] == "DRAFT_PENDING_APPROVAL"

    # Verify state in store remains READY_TO_ACT
    stored = commitment_store.get(c.id)
    assert stored.status == CommitmentStatus.READY_TO_ACT
    assert stored.status != CommitmentStatus.COMPLETED


# ---------------------------------------------------------------------------
# 7. Successful explicit approval -> COMPLETED
# ---------------------------------------------------------------------------

def test_successful_explicit_approval_to_completed():
    c = _make_commitment(CommitmentStatus.READY_TO_ACT)

    # Step 1: Draft response
    draft_raw = prepare_response(c.id, "Draft figures: $4.2M")
    assert "DRAFT_PENDING_APPROVAL" in draft_raw

    # Step 2: Explicit application approval gate
    human_approved = True

    # Step 3: Call mark_completed upon approval
    if human_approved:
        res_raw = mark_completed(c.id)
        res = json.loads(res_raw)
        assert res["status"] == "COMPLETED"

    stored = commitment_store.get(c.id)
    assert stored.status == CommitmentStatus.COMPLETED

    # get_open_commitments must no longer include completed items
    open_raw = get_open_commitments()
    open_res = json.loads(open_raw)
    assert open_res["count"] == 0


# ---------------------------------------------------------------------------
# 8. Already COMPLETED cannot be completed again
# ---------------------------------------------------------------------------

def test_already_completed_cannot_be_completed_again():
    c = _make_commitment(CommitmentStatus.READY_TO_ACT)

    res1_raw = mark_completed(c.id)
    res1 = json.loads(res1_raw)
    assert res1["status"] == "COMPLETED"

    # Second call fails
    res2_raw = mark_completed(c.id)
    res2 = json.loads(res2_raw)
    assert "error" in res2
    assert commitment_store.get(c.id).status == CommitmentStatus.COMPLETED


# ---------------------------------------------------------------------------
# 9. mark_completed absent from detection, resolution, action-prep workflows
# ---------------------------------------------------------------------------

def test_mark_completed_absent_from_detection_resolution_action_workflows():
    det_names = [t.__name__ for t in COMMITMENT_DETECTION_TOOLS]
    res_names = [t.__name__ for t in DEPENDENCY_RESOLUTION_TOOLS]
    act_names = [t.__name__ for t in ACTION_PREPARATION_TOOLS]
    resp_names = [t.__name__ for t in RESPONSE_PREPARATION_TOOLS]

    assert "mark_completed" not in det_names
    assert "mark_completed" not in res_names
    assert "mark_completed" not in act_names
    assert "mark_completed" not in resp_names  # response preparer is also draft-only


# ---------------------------------------------------------------------------
# 10. mark_completed tool presence and contract
# ---------------------------------------------------------------------------

def test_mark_completed_tool_presence():
    assert callable(mark_completed)
    assert mark_completed.__name__ == "mark_completed"

