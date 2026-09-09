"""Unit tests for the Loose Ends commitment domain model.

Covers:
- Successful creation (direct and via factory)
- Required-field validation
- Every valid state transition
- Invalid state transitions (several cases)
- COMPLETED being a terminal state
- Round-trip serialization / deserialization (dict and JSON)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest

from loose_ends.domain.commitment import (
    Commitment,
    CommitmentStatus,
    CommitmentValidationError,
    InvalidTransitionError,
    VALID_TRANSITIONS,
)

S = CommitmentStatus  # short alias for readability


# ── Helpers ───────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make(**overrides) -> Commitment:
    """Return a minimal valid Commitment, optionally overriding fields."""
    defaults = dict(
        id="test-id-001",
        action="Send the report",
        owner="alice",
        status=S.OPEN,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    defaults.update(overrides)
    return Commitment(**defaults)


# ── Creation ──────────────────────────────────────────────────────────────────


class TestCommitmentCreation:
    def test_direct_construction_with_all_required_fields(self):
        now = _utcnow()
        c = Commitment(
            id="abc-123",
            action="Follow up with vendor",
            owner="bob",
            status=S.OPEN,
            created_at=now,
            updated_at=now,
        )
        assert c.id == "abc-123"
        assert c.action == "Follow up with vendor"
        assert c.owner == "bob"
        assert c.status is S.OPEN
        assert c.created_at == now
        assert c.updated_at == now

    def test_optional_fields_default_to_none(self):
        c = _make()
        assert c.recipient is None
        assert c.deadline is None
        assert c.dependency is None
        assert c.source_message_id is None
        assert c.context is None
        assert c.next_action is None

    def test_optional_fields_accepted_when_provided(self):
        deadline = _utcnow() + timedelta(days=7)
        c = _make(
            recipient="carol",
            deadline=deadline,
            dependency="ticket-42",
            source_message_id="msg-007",
            context="Quarterly review",
            next_action="Draft email",
        )
        assert c.recipient == "carol"
        assert c.deadline == deadline
        assert c.dependency == "ticket-42"
        assert c.source_message_id == "msg-007"
        assert c.context == "Quarterly review"
        assert c.next_action == "Draft email"

    def test_factory_auto_generates_id_and_timestamps(self):
        c = Commitment.create(action="Review PR", owner="dave")
        assert c.id  # non-empty
        assert c.status is S.OPEN
        assert c.created_at.tzinfo is not None
        assert c.updated_at.tzinfo is not None
        assert c.created_at == c.updated_at

    def test_factory_accepts_explicit_id(self):
        c = Commitment.create(action="Deploy fix", owner="eve", id="explicit-id")
        assert c.id == "explicit-id"

    def test_factory_accepts_non_open_initial_status(self):
        c = Commitment.create(action="Call client", owner="frank", status=S.IN_PROGRESS)
        assert c.status is S.IN_PROGRESS


# ── Required-field validation ─────────────────────────────────────────────────


class TestCommitmentValidation:
    def test_empty_id_raises(self):
        with pytest.raises(CommitmentValidationError, match="id"):
            _make(id="")

    def test_whitespace_id_raises(self):
        with pytest.raises(CommitmentValidationError, match="id"):
            _make(id="   ")

    def test_empty_action_raises(self):
        with pytest.raises(CommitmentValidationError, match="action"):
            _make(action="")

    def test_whitespace_action_raises(self):
        with pytest.raises(CommitmentValidationError, match="action"):
            _make(action="  ")

    def test_empty_owner_raises(self):
        with pytest.raises(CommitmentValidationError, match="owner"):
            _make(owner="")

    def test_whitespace_owner_raises(self):
        with pytest.raises(CommitmentValidationError, match="owner"):
            _make(owner="\t")

    def test_invalid_status_type_raises(self):
        with pytest.raises(CommitmentValidationError, match="status"):
            _make(status="OPEN")  # plain string, not enum

    def test_naive_created_at_raises(self):
        naive = datetime(2025, 1, 1, 12, 0, 0)  # no tzinfo
        with pytest.raises(CommitmentValidationError, match="created_at"):
            _make(created_at=naive)

    def test_naive_updated_at_raises(self):
        naive = datetime(2025, 1, 1, 12, 0, 0)
        with pytest.raises(CommitmentValidationError, match="updated_at"):
            _make(updated_at=naive)

    def test_non_datetime_created_at_raises(self):
        with pytest.raises(CommitmentValidationError, match="created_at"):
            _make(created_at="2025-01-01T00:00:00Z")  # string, not datetime

    def test_non_datetime_updated_at_raises(self):
        with pytest.raises(CommitmentValidationError, match="updated_at"):
            _make(updated_at=12345)


# ── State transitions ─────────────────────────────────────────────────────────


class TestValidTransitions:
    """Verify every edge listed in VALID_TRANSITIONS succeeds."""

    @pytest.mark.parametrize(
        "from_status, to_status",
        [
            # OPEN edges
            (S.OPEN, S.WAITING_FOR_DEPENDENCY),
            (S.OPEN, S.READY_TO_ACT),
            (S.OPEN, S.IN_PROGRESS),
            (S.OPEN, S.WAITING_FOR_USER),
            (S.OPEN, S.COMPLETED),
            # WAITING_FOR_DEPENDENCY edges
            (S.WAITING_FOR_DEPENDENCY, S.READY_TO_ACT),
            (S.WAITING_FOR_DEPENDENCY, S.WAITING_FOR_USER),
            # READY_TO_ACT edges
            (S.READY_TO_ACT, S.IN_PROGRESS),
            (S.READY_TO_ACT, S.WAITING_FOR_USER),
            (S.READY_TO_ACT, S.COMPLETED),
            # IN_PROGRESS edges
            (S.IN_PROGRESS, S.WAITING_FOR_USER),
            (S.IN_PROGRESS, S.COMPLETED),
            (S.IN_PROGRESS, S.READY_TO_ACT),
            # WAITING_FOR_USER edges
            (S.WAITING_FOR_USER, S.READY_TO_ACT),
            (S.WAITING_FOR_USER, S.COMPLETED),
        ],
    )
    def test_valid_transition(self, from_status, to_status):
        c = _make(status=from_status)
        before_updated = c.updated_at
        c.transition_to(to_status)
        assert c.status is to_status
        # updated_at must have advanced (or at worst stayed equal on fast machines)
        assert c.updated_at >= before_updated

    def test_transition_updates_updated_at(self):
        c = _make(status=S.OPEN)
        original = c.updated_at
        c.transition_to(S.IN_PROGRESS)
        assert c.updated_at >= original
        assert c.updated_at.tzinfo is not None


class TestInvalidTransitions:
    """Verify disallowed transitions raise InvalidTransitionError."""

    @pytest.mark.parametrize(
        "from_status, to_status",
        [
            # Backward / nonsensical moves
            (S.WAITING_FOR_DEPENDENCY, S.OPEN),
            (S.WAITING_FOR_DEPENDENCY, S.IN_PROGRESS),
            (S.WAITING_FOR_DEPENDENCY, S.COMPLETED),
            (S.READY_TO_ACT, S.OPEN),
            (S.READY_TO_ACT, S.WAITING_FOR_DEPENDENCY),
            (S.IN_PROGRESS, S.OPEN),
            (S.IN_PROGRESS, S.WAITING_FOR_DEPENDENCY),
            (S.WAITING_FOR_USER, S.OPEN),
            (S.WAITING_FOR_USER, S.WAITING_FOR_DEPENDENCY),
            (S.WAITING_FOR_USER, S.IN_PROGRESS),
        ],
    )
    def test_invalid_transition_raises(self, from_status, to_status):
        c = _make(status=from_status)
        with pytest.raises(InvalidTransitionError):
            c.transition_to(to_status)

    def test_invalid_transition_does_not_mutate_status(self):
        c = _make(status=S.WAITING_FOR_DEPENDENCY)
        try:
            c.transition_to(S.OPEN)
        except InvalidTransitionError:
            pass
        assert c.status is S.WAITING_FOR_DEPENDENCY

    def test_invalid_transition_error_message_is_informative(self):
        c = _make(status=S.WAITING_FOR_DEPENDENCY)
        with pytest.raises(InvalidTransitionError, match="WAITING_FOR_DEPENDENCY"):
            c.transition_to(S.IN_PROGRESS)


class TestCompletedIsTerminal:
    def test_completed_to_any_raises(self):
        for target in S:
            if target is S.COMPLETED:
                continue
            c = _make(status=S.COMPLETED)
            with pytest.raises(InvalidTransitionError, match="terminal"):
                c.transition_to(target)

    def test_completed_to_completed_raises(self):
        """Self-transition on COMPLETED is also disallowed."""
        c = _make(status=S.COMPLETED)
        with pytest.raises(InvalidTransitionError):
            c.transition_to(S.COMPLETED)


# ── Serialization / deserialization ───────────────────────────────────────────


class TestSerialization:
    def _full_commitment(self) -> Commitment:
        now = _utcnow()
        return Commitment(
            id="ser-001",
            action="Write tests",
            owner="grace",
            status=S.IN_PROGRESS,
            created_at=now,
            updated_at=now,
            recipient="heidi",
            deadline=now + timedelta(days=3),
            dependency="blocker-99",
            source_message_id="msg-111",
            context="Sprint 4",
            next_action="Open IDE",
        )

    # to_dict / from_dict ---------------------------------------------------

    def test_to_dict_contains_all_keys(self):
        d = self._full_commitment().to_dict()
        expected_keys = {
            "id", "action", "owner", "status", "created_at", "updated_at",
            "recipient", "deadline", "dependency", "source_message_id",
            "context", "next_action",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_status_is_string(self):
        d = self._full_commitment().to_dict()
        assert isinstance(d["status"], str)
        assert d["status"] == "IN_PROGRESS"

    def test_to_dict_datetimes_are_iso_strings(self):
        d = self._full_commitment().to_dict()
        assert isinstance(d["created_at"], str)
        assert isinstance(d["updated_at"], str)
        # Must be parseable
        datetime.fromisoformat(d["created_at"])
        datetime.fromisoformat(d["updated_at"])

    def test_to_dict_optional_none_fields_present(self):
        c = _make()  # all optionals are None
        d = c.to_dict()
        assert d["recipient"] is None
        assert d["deadline"] is None
        assert d["dependency"] is None

    def test_round_trip_dict_full(self):
        original = self._full_commitment()
        restored = Commitment.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.action == original.action
        assert restored.owner == original.owner
        assert restored.status is original.status
        assert restored.recipient == original.recipient
        assert restored.dependency == original.dependency
        assert restored.context == original.context
        assert restored.next_action == original.next_action
        # Datetimes round-trip through ISO 8601
        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at
        assert restored.deadline == original.deadline

    def test_round_trip_dict_minimal(self):
        original = _make()
        restored = Commitment.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.status is original.status
        assert restored.recipient is None

    def test_from_dict_restores_utc_aware_timestamps(self):
        d = _make().to_dict()
        restored = Commitment.from_dict(d)
        assert restored.created_at.tzinfo is not None
        assert restored.updated_at.tzinfo is not None

    # to_json / from_json ---------------------------------------------------

    def test_to_json_produces_valid_json(self):
        payload = self._full_commitment().to_json()
        parsed = json.loads(payload)
        assert parsed["id"] == "ser-001"

    def test_round_trip_json_full(self):
        original = self._full_commitment()
        restored = Commitment.from_json(original.to_json())
        assert restored.id == original.id
        assert restored.status is original.status
        assert restored.deadline == original.deadline

    def test_round_trip_json_minimal(self):
        original = _make()
        restored = Commitment.from_json(original.to_json())
        assert restored.action == original.action
        assert restored.recipient is None

    def test_serialized_commitment_is_valid_after_transition(self):
        """A transitioned commitment must round-trip correctly."""
        c = _make(status=S.OPEN)
        c.transition_to(S.IN_PROGRESS)
        restored = Commitment.from_dict(c.to_dict())
        assert restored.status is S.IN_PROGRESS