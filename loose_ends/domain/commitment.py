"""Commitment domain model for Loose Ends.

Uses only the Python standard library (dataclasses, enum, datetime, uuid, json).
No database or external dependencies are introduced here.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ── Enum ──────────────────────────────────────────────────────────────────────


class CommitmentStatus(str, Enum):
    """Lifecycle states for a commitment."""

    OPEN = "OPEN"
    WAITING_FOR_DEPENDENCY = "WAITING_FOR_DEPENDENCY"
    READY_TO_ACT = "READY_TO_ACT"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"


# ── Allowed transitions (COMPLETED maps to an empty set — terminal) ───────────

VALID_TRANSITIONS: dict[CommitmentStatus, set[CommitmentStatus]] = {
    CommitmentStatus.OPEN: {
        CommitmentStatus.WAITING_FOR_DEPENDENCY,
        CommitmentStatus.READY_TO_ACT,
        CommitmentStatus.IN_PROGRESS,
        CommitmentStatus.WAITING_FOR_USER,
        CommitmentStatus.COMPLETED,
    },
    CommitmentStatus.WAITING_FOR_DEPENDENCY: {
        CommitmentStatus.READY_TO_ACT,
        CommitmentStatus.WAITING_FOR_USER,
    },
    CommitmentStatus.READY_TO_ACT: {
        CommitmentStatus.IN_PROGRESS,
        CommitmentStatus.WAITING_FOR_USER,
        CommitmentStatus.COMPLETED,
    },
    CommitmentStatus.IN_PROGRESS: {
        CommitmentStatus.WAITING_FOR_USER,
        CommitmentStatus.COMPLETED,
        CommitmentStatus.READY_TO_ACT,
    },
    CommitmentStatus.WAITING_FOR_USER: {
        CommitmentStatus.READY_TO_ACT,
        CommitmentStatus.COMPLETED,
    },
    CommitmentStatus.COMPLETED: set(),
}


# ── Exceptions ────────────────────────────────────────────────────────────────


class CommitmentValidationError(ValueError):
    """Raised when a Commitment is constructed with invalid data."""


class InvalidTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""


# ── Domain model ──────────────────────────────────────────────────────────────


@dataclass
class Commitment:
    """A single trackable promise or obligation.

    Required fields
    ---------------
    id              Unique identifier (UUID string recommended).
    action          Human-readable description of what must be done.
    owner           Person / system responsible for the commitment.
    status          Current lifecycle state (CommitmentStatus).
    created_at      UTC-aware datetime of initial creation.
    updated_at      UTC-aware datetime of the last modification.

    Optional fields
    ---------------
    recipient           Who the commitment is made to.
    deadline            Target completion datetime (UTC-aware).
    dependency          Free-text reference to a blocking item.
    source_message_id   Reference to the originating message.
    context             Additional background information.
    next_action         Immediate next physical action to take.
    """

    # Required
    id: str
    action: str
    owner: str
    status: CommitmentStatus
    created_at: datetime
    updated_at: datetime

    # Optional
    recipient: Optional[str] = None
    deadline: Optional[datetime] = None
    dependency: Optional[str] = None
    source_message_id: Optional[str] = None
    context: Optional[str] = None
    next_action: Optional[str] = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise CommitmentValidationError(
                "'id' is required and must be a non-empty string."
            )
        if not isinstance(self.action, str) or not self.action.strip():
            raise CommitmentValidationError(
                "'action' is required and must be a non-empty string."
            )
        if not isinstance(self.owner, str) or not self.owner.strip():
            raise CommitmentValidationError(
                "'owner' is required and must be a non-empty string."
            )
        if not isinstance(self.status, CommitmentStatus):
            raise CommitmentValidationError(
                f"'status' must be a CommitmentStatus value, got {self.status!r}."
            )
        if not isinstance(self.created_at, datetime):
            raise CommitmentValidationError(
                "'created_at' must be a datetime instance."
            )
        if not isinstance(self.updated_at, datetime):
            raise CommitmentValidationError(
                "'updated_at' must be a datetime instance."
            )
        if self.created_at.tzinfo is None:
            raise CommitmentValidationError(
                "'created_at' must be UTC-aware (tzinfo must not be None)."
            )
        if self.updated_at.tzinfo is None:
            raise CommitmentValidationError(
                "'updated_at' must be UTC-aware (tzinfo must not be None)."
            )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        action: str,
        owner: str,
        *,
        id: Optional[str] = None,
        status: CommitmentStatus = CommitmentStatus.OPEN,
        recipient: Optional[str] = None,
        deadline: Optional[datetime] = None,
        dependency: Optional[str] = None,
        source_message_id: Optional[str] = None,
        context: Optional[str] = None,
        next_action: Optional[str] = None,
    ) -> "Commitment":
        """Convenience factory: auto-generates id and UTC timestamps."""
        now = datetime.now(timezone.utc)
        return cls(
            id=id or str(uuid.uuid4()),
            action=action,
            owner=owner,
            status=status,
            created_at=now,
            updated_at=now,
            recipient=recipient,
            deadline=deadline,
            dependency=dependency,
            source_message_id=source_message_id,
            context=context,
            next_action=next_action,
        )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def transition_to(self, new_status: CommitmentStatus) -> None:
        """Apply a validated state transition.

        Updates *updated_at* to the current UTC time on success.
        Raises InvalidTransitionError for any disallowed transition.
        """
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            allowed_names = sorted(s.value for s in allowed)
            raise InvalidTransitionError(
                f"Cannot transition {self.id!r} from {self.status.value!r} "
                f"to {new_status.value!r}. "
                f"Allowed targets: {allowed_names if allowed_names else ['none — terminal state']}."
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a fully JSON-serializable dictionary."""
        return {
            "id": self.id,
            "action": self.action,
            "owner": self.owner,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "recipient": self.recipient,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "dependency": self.dependency,
            "source_message_id": self.source_message_id,
            "context": self.context,
            "next_action": self.next_action,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Commitment":
        """Reconstruct a Commitment from a plain dictionary.

        Accepts ISO-8601 strings for datetime fields.
        Naive datetimes are assumed to be UTC.
        """

        def _dt(value: Optional[str]) -> Optional[datetime]:
            if value is None:
                return None
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed

        return cls(
            id=data["id"],
            action=data["action"],
            owner=data["owner"],
            status=CommitmentStatus(data["status"]),
            created_at=_dt(data["created_at"]),
            updated_at=_dt(data["updated_at"]),
            recipient=data.get("recipient"),
            deadline=_dt(data.get("deadline")),
            dependency=data.get("dependency"),
            source_message_id=data.get("source_message_id"),
            context=data.get("context"),
            next_action=data.get("next_action"),
        )

    def to_json(self) -> str:
        """Serialize to a compact JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Commitment":
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(json_str))