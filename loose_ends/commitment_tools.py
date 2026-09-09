"""Strands tools for commitment management.

Tools:
  create_commitment     - validate and persist a new commitment
  get_open_commitments  - read all non-COMPLETED commitments
  update_commitment     - update status or metadata of an existing commitment
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from strands import tool

from loose_ends.domain.commitment import (
    Commitment,
    CommitmentStatus,
    CommitmentValidationError,
    InvalidTransitionError,
)
from loose_ends.store import commitment_store


# ---------------------------------------------------------------------------
# create_commitment
# ---------------------------------------------------------------------------

@tool
def create_commitment(
    action: str,
    owner: str,
    recipient: Optional[str] = None,
    deadline: Optional[str] = None,
    dependency: Optional[str] = None,
    source_message_id: Optional[str] = None,
    context: Optional[str] = None,
    next_action: Optional[str] = None,
) -> str:
    """Create a new commitment and persist it in the in-memory store.

    The initial status is chosen deterministically by the tool:
    - WAITING_FOR_DEPENDENCY when *dependency* is specified.
    - READY_TO_ACT otherwise.

    Args:
        action: What must be done (required, non-empty).
        owner: Person responsible for completing this commitment (required).
        recipient: Who the commitment is made to (optional).
        deadline: Target completion time as an ISO 8601 string,
            e.g. '2025-12-31T18:00:00Z' (optional).
        dependency: Free-text description of a blocking item (optional).
        source_message_id: ID of the message that triggered this
            commitment (optional).
        context: Additional background information (optional).
        next_action: The immediate physical next action (optional).

    Returns:
        A JSON string containing:
            commitment_id - unique identifier of the new commitment
            action        - the action text
            owner         - responsible party
            status        - initial lifecycle status
            dependency    - the dependency string or null
        On error, returns a JSON string with an "error" key describing
        the problem.
    """
    # Parse deadline if provided
    parsed_deadline: Optional[datetime] = None
    if deadline:
        try:
            parsed_deadline = datetime.fromisoformat(deadline)
            if parsed_deadline.tzinfo is None:
                # Treat naive datetime strings as UTC
                parsed_deadline = parsed_deadline.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            return json.dumps(
                {
                    "error": (
                        f"Invalid deadline format {deadline!r}. "
                        "Use ISO 8601, e.g. '2025-12-31T18:00:00Z'."
                    ),
                    "detail": str(exc),
                }
            )

    # Determine initial status deterministically (not LLM-chosen)
    initial_status = (
        CommitmentStatus.WAITING_FOR_DEPENDENCY
        if dependency
        else CommitmentStatus.READY_TO_ACT
    )

    # Build and validate via the domain model
    try:
        commitment = Commitment.create(
            action=action,
            owner=owner,
            status=initial_status,
            recipient=recipient,
            deadline=parsed_deadline,
            dependency=dependency,
            source_message_id=source_message_id,
            context=context,
            next_action=next_action,
        )
    except CommitmentValidationError as exc:
        return json.dumps({"error": str(exc)})

    # Persist to the in-memory store
    commitment_store.add(commitment)

    # Return concise summary
    return json.dumps(
        {
            "commitment_id": commitment.id,
            "action": commitment.action,
            "owner": commitment.owner,
            "status": commitment.status.value,
            "dependency": commitment.dependency,
        }
    )


# ---------------------------------------------------------------------------
# Private serialiser: read-only, no mutation
# ---------------------------------------------------------------------------


def _serialise_commitment(c: Commitment) -> dict:
    """Return a JSON-safe dict for a single Commitment.

    Exposes agent-relevant fields only; omits internal timestamps and context.
    """
    return {
        "commitment_id": c.id,
        "action": c.action,
        "owner": c.owner,
        "recipient": c.recipient,
        "deadline": c.deadline.isoformat() if c.deadline else None,
        "dependency": c.dependency,
        "status": c.status.value,
        "source_message_id": c.source_message_id,
        "next_action": c.next_action,
    }


# ---------------------------------------------------------------------------
# get_open_commitments
# ---------------------------------------------------------------------------

@tool
def get_open_commitments() -> str:
    """Return all commitments that are not yet COMPLETED.

    Reads the in-memory store without mutating any entry.
    Results are ordered by creation time ascending (oldest first).

    Returns:
        A JSON string containing:
            count       - number of open commitments (int)
            commitments - list of commitment objects ordered by created_at asc,
                          each with: commitment_id, action, owner, recipient,
                          deadline, dependency, status, source_message_id,
                          next_action.
        Returns {"count": 0, "commitments": []} when the store is empty
        or all commitments are COMPLETED.
    """
    open_items = [
        c for c in commitment_store.all()
        if c.status is not CommitmentStatus.COMPLETED
    ]

    # Sort by creation time ascending -- stable and deterministic.
    open_items.sort(key=lambda c: c.created_at)

    return json.dumps(
        {
            "count": len(open_items),
            "commitments": [_serialise_commitment(c) for c in open_items],
        }
    )


# ---------------------------------------------------------------------------
# update_commitment
# ---------------------------------------------------------------------------

@tool
def update_commitment(
    commitment_id: str,
    status: Optional[str] = None,
    dependency: Optional[str] = None,
    next_action: Optional[str] = None,
    context: Optional[str] = None,
) -> str:
    """Update the status and/or metadata of an existing commitment.

    Locates the commitment by commitment_id and applies the requested changes.
    Status changes are validated through the domain model's state machine --
    invalid transitions are rejected with a clear error.

    Allowed status transitions include:
      WAITING_FOR_DEPENDENCY -> READY_TO_ACT  (dependency resolved)
      READY_TO_ACT           -> IN_PROGRESS
      IN_PROGRESS            -> COMPLETED
      (see domain model for the full transition table)

    Args:
        commitment_id: ID of the commitment to update (required).
        status: New lifecycle status value (e.g. 'READY_TO_ACT').
                Must follow valid transition rules.
        dependency: Updated dependency description. Pass empty string to clear.
        next_action: Updated immediate next action text.
        context: Updated background context.

    Returns:
        A JSON string containing:
            commitment_id  - the updated commitment's ID
            updated_fields - list of field names that were changed
            status         - the resulting status after the update
        On error, returns a JSON string with an "error" key.
    """
    # Locate the commitment
    commitment = commitment_store.get(commitment_id)
    if commitment is None:
        return json.dumps(
            {"error": f"Commitment {commitment_id!r} not found in the store."}
        )

    updated_fields: list[str] = []

    # Status change: must go through the domain model's transition_to()
    if status is not None:
        try:
            new_status = CommitmentStatus(status)
        except ValueError:
            valid = [s.value for s in CommitmentStatus]
            return json.dumps(
                {
                    "error": (
                        f"Unknown status {status!r}. "
                        f"Valid values: {valid}."
                    )
                }
            )
        try:
            commitment.transition_to(new_status)  # also updates updated_at
            updated_fields.append("status")
        except InvalidTransitionError as exc:
            return json.dumps({"error": str(exc)})

    # Mutable metadata fields: None means "do not change"
    now = datetime.now(timezone.utc)
    if dependency is not None:
        commitment.dependency = dependency
        commitment.updated_at = now
        updated_fields.append("dependency")
    if next_action is not None:
        commitment.next_action = next_action
        commitment.updated_at = now
        updated_fields.append("next_action")
    if context is not None:
        commitment.context = context
        commitment.updated_at = now
        updated_fields.append("context")

    return json.dumps(
        {
            "commitment_id": commitment.id,
            "updated_fields": updated_fields,
            "status": commitment.status.value,
        }
    )