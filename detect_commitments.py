"""detect_commitments.py: Deterministic commitment-detection demo.

Invokes the commitment-detection agent once against the local mock message
dataset and prints what it does.  No user input required.

Usage:
    .venv\\Scripts\\python detect_commitments.py
"""
import os
from dotenv import load_dotenv

# Load .env before any module that reads GEMINI_API_KEY
load_dotenv()

from loose_ends.agent import build_commitment_detector  # noqa: E402
from loose_ends.store import commitment_store           # noqa: E402

# ---------------------------------------------------------------------------
# Task instruction given to the agent (deterministic, not typed by the user)
# ---------------------------------------------------------------------------

DETECTION_TASK = (
    "Review all available messages and identify any new commitments made by "
    "the user.\n"
    "\n"
    "Follow these steps exactly:\n"
    "1. Call search_messages with no filters to retrieve all local messages.\n"
    "2. Call get_open_commitments to see what is already tracked and avoid "
    "   creating duplicates.\n"
    "3. For each explicit promise you find in the messages, call "
    "   create_commitment to record it -- but only if it is not already "
    "   tracked in the open commitments.\n"
    "4. After processing, summarize: how many new commitments you created, "
    "   which ones already existed, and the final status of each new commitment."
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    sep = "=" * 64

    print(sep)
    print("  Loose Ends -- Commitment Detection Demo")
    print(sep)
    print()

    # Check for API key before attempting to build the agent
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY is not set.")
        print("Copy .env.example to .env and add your key, then re-run.")
        return

    print("Building commitment-detection agent...")
    agent = build_commitment_detector()

    print(f"\nTask:\n{DETECTION_TASK}\n")
    print(sep)
    print()

    response = agent(DETECTION_TASK)

    print()
    print(sep)
    print("  Agent Response")
    print(sep)
    print(response)
    print()
    print(sep)

    # Show what ended up in the commitment store
    all_commitments = commitment_store.all()
    print(f"\nCommitments now in store: {len(all_commitments)}")
    for c in all_commitments:
        dep = f" | dependency: {c.dependency}" if c.dependency else ""
        print(
            f"  [{c.status.value}] {c.action} "
            f"(owner: {c.owner}, recipient: {c.recipient})"
            f"{dep}"
        )


if __name__ == "__main__":
    main()