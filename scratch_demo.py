import os
import sys
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Enable strands debug logging to see tool calls
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
logging.getLogger("strands").setLevel(logging.DEBUG)

load_dotenv()

from loose_ends.agent import build_response_preparer
from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.store import commitment_store

def run_demo():
    commitment_store.clear()
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
    
    print(f"[BEFORE] Store count: {len(commitment_store)}")
    print(f"[BEFORE] Status: {commitment_store.get('demo-q3-commitment').status.value}")
    
    agent = build_response_preparer()
    
    task = (
        "Find READY_TO_ACT commitments, gather necessary info from documents, "
        "and prepare a response draft for human approval."
    )
    
    print("\n--- AGENT RUN ---")
    response = agent(task)
    print("\n--- AGENT FINISHED ---\n")
    
    print(response)
    
    print(f"\n[AFTER] Store count: {len(commitment_store)}")
    print(f"[AFTER] Status: {commitment_store.get('demo-q3-commitment').status.value}")

if __name__ == "__main__":
    run_demo()
