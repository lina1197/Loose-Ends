"""resolve_dependencies.py: Dependency-resolution demonstration.

Uses the DEDICATED dependency-resolution workflow (build_dependency_resolver).
This agent has access to ONLY:
  - search_messages
  - get_open_commitments
  - update_commitment

It does NOT have access to create_commitment, so it cannot create
new commitments regardless of what it finds in the messages.

Expected tool sequence:
  search_messages -> get_open_commitments -> update_commitment

Usage:
    .venv\\Scripts\\python resolve_dependencies.py
"""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from loose_ends.agent import build_dependency_resolver
from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.store import commitment_store

# ---------------------------------------------------------------------------
# Task instruction (deterministic -- no free-form user input)
# ---------------------------------------------------------------------------

RESOLUTION_TASK = (
    "Review the available messages and all open commitments.\n"
    "\n"
    "Follow these steps:\n"
    "1. Call search_messages with no filters to retrieve all local messages.\n"
    "2. Call get_open_commitments to see every tracked commitment.\n"
    "3. For each commitment with status WAITING_FOR_DEPENDENCY:\n"
    "   a. Read its 'dependency' field carefully.\n"
    "   b. Look through the messages for one that explicitly and directly\n"
    "      confirms the dependency is resolved -- not just any mention of\n"
    "      the same topic, but a clear confirmation.\n"
    "   c. If you find such evidence, call update_commitment with\n"
    "      status='READY_TO_ACT' for that commitment.\n"
    "4. Do NOT resolve a dependency based on guesswork or keyword overlap alone.\n"
    "5. Do NOT call create_commitment -- that tool is not available here.\n"
    "6. Summarize: which commitments you checked, which dependency was\n"
    "   resolved and by which message, and what the final status is."
)


# ---------------------------------------------------------------------------
# Store seeding
# ---------------------------------------------------------------------------

def seed_store() -> Commitment:
    """Insert exactly one WAITING_FOR_DEPENDENCY commitment into the store.

    This function is importable by tests.
    """
    ts = datetime(2027, 9, 3, 10, 45, 0, tzinfo=timezone.utc)
    c = Commitment(
        id="demo-hotfix-commitment",
        action="Deploy the hotfix to production",
        owner="dave",
        recipient="carol",
        status=CommitmentStatus.WAITING_FOR_DEPENDENCY,
        dependency="QA approval of the build",
        source_message_id="msg-006",
        created_at=ts,
        updated_at=ts,
    )
    commitment_store.add(c)
    return c


# ---------------------------------------------------------------------------
# Display helper
# ---------------------------------------------------------------------------

def _print_commitment(label: str, c: Commitment) -> None:
    sep = "-" * 48
    print(sep)
    print(f"  {label}")
    print(sep)
    print(f"  ID         : {c.id}")
    print(f"  Action     : {c.action}")
    print(f"  Owner      : {c.owner}  ->  recipient: {c.recipient}")
    print(f"  Status     : {c.status.value}")
    print(f"  Dependency : {c.dependency}")
    print(sep)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    sep = "=" * 64

    print(sep)
    print("  Loose Ends -- Dependency Resolution Demo")
    print("  (dedicated resolver, no create_commitment)")
    print(sep)

    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY is not set.")
        print("Copy .env.example to .env and add your key, then re-run.")
        return

    # Start with a clean store, then seed exactly one commitment
    commitment_store.clear()
    hotfix = seed_store()

    print(f"\nStore contains {len(commitment_store)} commitment(s) before resolution.")
    print("\n[BEFORE] Commitment state:")
    _print_commitment("dave/hotfix -- WAITING_FOR_DEPENDENCY", hotfix)

    print("\nEvidence available in messages:")
    print("  msg-007 (qa-team -> dave):")
    print("  'Dave, QA has approved the build. The dependency is resolved")
    print("   and you are clear to deploy the hotfix to production.'\n")

    print("Building dependency-resolution agent (3 tools, no create_commitment)...")
    agent = build_dependency_resolver()

    print(f"\nTask:\n{RESOLUTION_TASK}\n")
    print(sep)
    print()

    response = agent(RESOLUTION_TASK)

    print()
    print(sep)
    print("  Agent Response")
    print(sep)
    print(response)

    # Show final state
    updated = commitment_store.get(hotfix.id)
    final_count = len(commitment_store)
    print(f"\nStore contains {final_count} commitment(s) after resolution.")
    print("\n[AFTER] Commitment state:")
    _print_commitment("dave/hotfix -- final state", updated)

    if final_count == 1:
        print("\nCRITICAL CHECK PASSED: exactly 1 commitment in store (no new ones created).")
    else:
        print(f"\nWARNING: expected 1 commitment, found {final_count}.")
    print()


if __name__ == "__main__":
    main()