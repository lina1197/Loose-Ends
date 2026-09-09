"""Tests for the Step 11 response-preparation workflow."""
import json
from loose_ends.agent import build_response_preparer
from loose_ends.commitment_tools import prepare_response
from loose_ends.store import commitment_store
from loose_ends.domain.commitment import Commitment, CommitmentStatus

def test_prepare_response_tool_success():
    """Test that prepare_response creates a draft for a valid commitment."""
    commitment_store.clear()
    
    # Create a test commitment
    c = Commitment.create(
        action="Draft test response",
        owner="Alice",
        status=CommitmentStatus.READY_TO_ACT
    )
    commitment_store.add(c)
    
    # Call the tool
    result_str = prepare_response(c.id, "This is the draft text.")
    result = json.loads(result_str)
    
    # Verify the output
    assert result["status"] == "DRAFT_PENDING_APPROVAL"
    assert result["commitment_id"] == c.id
    assert result["draft_content"] == "[DRAFT] This is the draft text."
    
    # Verify the commitment status was NOT changed
    stored_c = commitment_store.get(c.id)
    assert stored_c.status == CommitmentStatus.READY_TO_ACT

def test_prepare_response_tool_not_found():
    """Test that prepare_response handles non-existent commitments."""
    commitment_store.clear()
    
    result_str = prepare_response("missing-id", "Some draft")
    result = json.loads(result_str)
    
    assert "error" in result
    assert "not found" in result["error"]

def test_prepare_response_tool_not_ready():
    """Test that prepare_response rejects commitments not READY_TO_ACT."""
    commitment_store.clear()
    
    c = Commitment.create(
        action="Pending action",
        owner="Bob",
        status=CommitmentStatus.WAITING_FOR_DEPENDENCY
    )
    commitment_store.add(c)
    
    result_str = prepare_response(c.id, "Draft")
    result = json.loads(result_str)
    
    assert "error" in result
    assert "is not READY_TO_ACT" in result["error"]

def test_response_preparer_tools():
    """Test that the response preparer has exactly the right tools."""
    from loose_ends.agent import RESPONSE_PREPARATION_TOOLS
    tool_names = {t.__name__ for t in RESPONSE_PREPARATION_TOOLS}
    
    assert tool_names == {
        "get_open_commitments",
        "search_documents",
        "get_document",
        "prepare_response",
    }
