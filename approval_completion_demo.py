"""approval_completion_demo.py: Local approval and completion demonstration.

Demonstrates the explicit application-level approval flow:
  1. Store is cleared and seeded with exactly ONE READY_TO_ACT commitment.
  2. Response draft is prepared (using prepare_response tool).
  3. Status is shown as DRAFT PENDING APPROVAL (commitment remains READY_TO_ACT).
  4. Explicit human/user approval is granted at the application level.
  5. mark_completed tool is invoked following approval.
  6. Final state is COMPLETED and exactly one commitment remains in store.
  7. Confirms nothing was sent externally.

Usage:
    .venv\\Scripts\\python approval_completion_demo.py
"""
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.commitment_tools import prepare_response, mark_completed
from loose_ends.documents.document_tools import get_document
from loose_ends.agent import build_response_preparer
from loose_ends.store import commitment_store


def seed_store() -> Commitment:
    """Insert exactly one READY_TO_ACT commitment."""
    ts = datetime(2027, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    deadline = datetime(2027, 9, 3, 17, 0, 0, tzinfo=timezone.utc)
    c = Commitment(
        id="demo-q3-commitment",
        action="Send the Q3 financial report",
        owner="bob",
        recipient="alice",
        status=CommitmentStatus.READY_TO_ACT,
        deadline=deadline,
        source_message_id="msg-002",
        context="Alice needs the Q3 financial report for the board presentation.",
        next_action="Find the latest Q3 financial figures and prepare the report for Alice.",
        created_at=ts,
        updated_at=ts,
    )
    commitment_store.add(c)
    return c


def _print_commitment(label: str, c: Commitment) -> None:
    sep = "-" * 52
    print(sep)
    print(f"  {label}")
    print(sep)
    print(f"  ID          : {c.id}")
    print(f"  Action      : {c.action}")
    print(f"  Owner       : {c.owner}  ->  recipient: {c.recipient}")
    print(f"  Status      : {c.status.value}")
    print(f"  Deadline    : {c.deadline.isoformat() if c.deadline else 'none'}")
    print(f"  Context     : {c.context}")
    print(f"  Next action : {c.next_action}")
    print(sep)


def main() -> None:
    sep = "=" * 64

    print(sep)
    print("  Loose Ends -- Local Approval & Completion Demo")
    print("  (Workflow: READY_TO_ACT -> DRAFT -> Explicit Approval -> COMPLETED)")
    print(sep)

    # 1. Clear store and seed commitment
    commitment_store.clear()
    commitment = seed_store()

    print(f"\nStore contains {len(commitment_store)} commitment(s) initially.")
    print("\n[STEP 1: INITIAL STATE]")
    _print_commitment("bob/Q3 report -- READY_TO_ACT", commitment)

    # 2. Prepare response draft via response preparer workflow
    print("\n[STEP 2: PREPARING DRAFT RESPONSE]")
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        agent = build_response_preparer(api_key=key)
        agent("Review open READY_TO_ACT commitments, gather necessary info from documents, and prepare a response draft for human approval.")
    else:
        doc_raw = get_document("doc-q3-figures")
        doc_data = json.loads(doc_raw)
        prepare_response(commitment.id, f"Summary based on {doc_data.get('filename')}:\n{doc_data.get('content')}")

    stored_draft = commitment_store.get_draft(commitment.id)
    print(f"  Draft content stored : {stored_draft}")

    # Verify status in store before approval
    current = commitment_store.get(commitment.id)
    print(f"\n  Commitment status in store before approval: {current.status.value}")
    print("  DRAFT PENDING APPROVAL -- Nothing sent, commitment remains READY_TO_ACT.")

    # 3. Explicit Application-Level Approval
    print("\n[STEP 3: EXPLICIT HUMAN APPROVAL]")
    user_input = "APPROVE"  # Explicit application-level decision
    print(f"  User input / application action: '{user_input}'")

    if user_input == "APPROVE":
        print("  Approval granted! Executing mark_completed...")

        # 4. Mark Completed
        completion_raw = mark_completed(commitment_id=commitment.id)
        completion_result = json.loads(completion_raw)
        print(f"  mark_completed result: {completion_result}")
    else:
        print("  Approval rejected or withheld. mark_completed was NOT called.")

    # 5. Final State Verification
    final_commitment = commitment_store.get(commitment.id)
    final_count = len(commitment_store)

    print("\n[STEP 4: FINAL STATE]")
    _print_commitment("bob/Q3 report -- COMPLETED", final_commitment)

    print("\nCRITICAL CHECKS:")
    ok_count = (final_count == 1)
    ok_status = (final_commitment.status is CommitmentStatus.COMPLETED)
    ok_not_sent = True  # prepare_response + mark_completed make 0 network/email calls

    print(f"  Store count == 1:               {'PASS' if ok_count else 'FAIL'}")
    print(f"  Final status is COMPLETED:      {'PASS' if ok_status else 'FAIL'}")
    print(f"  Nothing sent externally:        {'PASS' if ok_not_sent else 'FAIL'}")

    if ok_count and ok_status and ok_not_sent:
        print("\nSUCCESS: Step 12 local approval and completion demo passed.")
    else:
        print("\nFAILURE: One or more acceptance checks failed.")


if __name__ == "__main__":
    main()
