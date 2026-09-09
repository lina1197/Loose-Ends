"""prepare_action_demo.py: Action-preparation demonstration.

Seeds the in-memory commitment store with exactly ONE READY_TO_ACT commitment
(bob must send the Q3 financial report to alice) and then runs the read-only
action-preparation workflow.

The agent should:
  1. get_open_commitments   -- find the Q3 commitment
  2. search_documents       -- search for relevant documents
  3. get_document           -- retrieve the Q3 financial figures

The commitment MUST remain READY_TO_ACT throughout -- this workflow is
strictly read-only.

Usage:
    .venv\\Scripts\\python prepare_action_demo.py
"""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from loose_ends.agent import build_action_preparer
from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.store import commitment_store

# ---------------------------------------------------------------------------
# Task instruction (deterministic)
# ---------------------------------------------------------------------------

PREPARATION_TASK = (
    "Review all open commitments and gather the information needed to act.\n"
    "\n"
    "Follow these steps:\n"
    "1. Call get_open_commitments to see what is currently tracked.\n"
    "2. For each READY_TO_ACT commitment:\n"
    "   a. Read its action, context, and next_action fields carefully.\n"
    "   b. Derive a specific search query from the commitment content.\n"
    "   c. Call search_documents with that query.\n"
    "   d. Identify the most relevant result and call get_document to read it.\n"
    "   e. Assess whether the document provides sufficient information.\n"
    "3. Do NOT call create_commitment or update_commitment.\n"
    "4. Do NOT change any commitment's status.\n"
    "5. Summarize:\n"
    "   - the commitment reviewed\n"
    "   - the document(s) found\n"
    "   - key information extracted\n"
    "   - whether sufficient information is available to proceed\n"
    "   - anything still missing"
)


# ---------------------------------------------------------------------------
# Store seeding
# ---------------------------------------------------------------------------

def seed_store() -> Commitment:
    """Insert exactly one READY_TO_ACT commitment.  Importable by tests."""
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


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    sep = "=" * 64

    print(sep)
    print("  Loose Ends -- Action Preparation Demo")
    print("  (read-only: get_open_commitments, search_documents, get_document)")
    print(sep)

    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY is not set.")
        print("Copy .env.example to .env and add your key, then re-run.")
        return

    # Clean slate -- seed exactly one commitment
    commitment_store.clear()
    commitment = seed_store()

    print(f"\nStore contains {len(commitment_store)} commitment(s) before run.")
    print("\n[BEFORE] Commitment state:")
    _print_commitment("bob/Q3 report -- READY_TO_ACT", commitment)

    print("\nBuilding action-preparation agent (3 read-only tools)...")
    agent = build_action_preparer()

    print(f"\nTask:\n{PREPARATION_TASK}\n")
    print(sep)
    print()

    response = agent(PREPARATION_TASK)

    print()
    print(sep)
    print("  Agent Response")
    print(sep)
    print(response)

    # Verify commitment is unchanged
    after = commitment_store.get(commitment.id)
    final_count = len(commitment_store)

    print(f"\nStore contains {final_count} commitment(s) after run.")
    print("\n[AFTER] Commitment state:")
    _print_commitment("bob/Q3 report -- final state", after)

    # Critical acceptance checks
    print()
    ok_count = (final_count == 1)
    ok_status = (after.status is CommitmentStatus.READY_TO_ACT)

    print(f"  Store count == 1:          {'PASS' if ok_count  else 'FAIL'}")
    print(f"  Status still READY_TO_ACT: {'PASS' if ok_status else 'FAIL'}")
    if ok_count and ok_status:
        print("\nCRITICAL CHECKS PASSED: workflow was read-only.")
    else:
        print("\nWARNING: one or more critical checks failed.")
    print()


if __name__ == "__main__":
    main()