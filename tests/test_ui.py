"""tests/test_ui.py: Tests for the Loose Ends Web Application layer."""

import json
from io import BytesIO
from datetime import datetime, timezone
import pytest

from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.commitment_tools import prepare_response
from loose_ends.store import commitment_store
from loose_ends.server import (
    get_summary_counts,
    seed_q3_demo,
    serialise_commitment_for_ui,
    LooseEndsRequestHandler,
)


@pytest.fixture(autouse=True)
def _clear_store():
    """Ensure a clean in-memory store before each test."""
    commitment_store.clear()
    yield
    commitment_store.clear()


class DummyServer:
    """Mock HTTPServer required by BaseHTTPRequestHandler initialization."""
    pass


def _make_handler(method: str, path: str, body: dict = None) -> LooseEndsRequestHandler:
    """Construct a request handler instance with mocked request streams."""
    raw_body = json.dumps(body).encode("utf-8") if body else b""
    
    rfile = BytesIO(raw_body)
    wfile = BytesIO()

    # Instantiate handler using standard BaseHTTPRequestHandler args
    handler = LooseEndsRequestHandler.__new__(LooseEndsRequestHandler)
    handler.rfile = rfile
    handler.wfile = wfile
    handler.headers = {"Content-Length": str(len(raw_body))}
    handler.path = path
    handler.command = method
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.server = DummyServer()

    return handler


def _get_response_data(handler: LooseEndsRequestHandler) -> tuple[int, dict]:
    """Parse HTTP status line and JSON body from handler's written output."""
    output = handler.wfile.getvalue().decode("utf-8")
    lines = output.split("\r\n")
    # First line: HTTP/1.1 200 OK
    status_code = int(lines[0].split(" ")[1])
    
    # Body is after empty line \r\n\r\n
    body_str = output.split("\r\n\r\n", 1)[1]
    return status_code, json.loads(body_str)


# ---------------------------------------------------------------------------
# 1. Summary counts derived from actual stored commitments
# ---------------------------------------------------------------------------

def test_summary_counts_derived_from_actual_stored_commitments():
    ts = datetime.now(timezone.utc)
    c1 = Commitment.create("Action 1", "owner1", status=CommitmentStatus.READY_TO_ACT)
    c2 = Commitment.create("Action 2", "owner2", status=CommitmentStatus.WAITING_FOR_DEPENDENCY)
    c3 = Commitment.create("Action 3", "owner3", status=CommitmentStatus.COMPLETED)
    
    commitment_store.add(c1)
    commitment_store.add(c2)
    commitment_store.add(c3)

    summary = get_summary_counts()
    assert summary["need_you"] == 1
    assert summary["im_handling"] == 1
    assert summary["closed"] == 1
    assert summary["total"] == 3


# ---------------------------------------------------------------------------
# 2. COMPLETED commitments are counted as CLOSED
# ---------------------------------------------------------------------------

def test_completed_commitments_counted_as_closed():
    c = Commitment.create("Completed Action", "owner", status=CommitmentStatus.COMPLETED)
    commitment_store.add(c)

    summary = get_summary_counts()
    assert summary["closed"] == 1
    assert summary["need_you"] == 0
    assert summary["im_handling"] == 0


# ---------------------------------------------------------------------------
# 3. Open commitments are displayed
# ---------------------------------------------------------------------------

def test_open_commitments_displayed_and_grouped():
    c = seed_q3_demo(live_agent=False)
    
    handler = _make_handler("GET", "/api/commitments")
    handler.do_GET()
    status, data = _get_response_data(handler)

    assert status == 200
    assert data["summary"]["need_you"] == 1
    assert data["summary"]["closed"] == 0
    assert len(data["commitments"]) == 1
    
    comm = data["commitments"][0]
    assert comm["id"] == c.id
    assert comm["status"] == "READY_TO_ACT"
    assert comm["has_draft"] is True
    assert "[DRAFT]" in comm["draft"]


# ---------------------------------------------------------------------------
# 4. No completion happens merely from viewing a draft
# ---------------------------------------------------------------------------

def test_no_completion_merely_from_viewing_draft():
    c = seed_q3_demo(live_agent=False)

    # Simulate GET request to view commitments & draft
    handler = _make_handler("GET", "/api/commitments")
    handler.do_GET()
    status, data = _get_response_data(handler)
    assert status == 200

    # Verify commitment in store remains READY_TO_ACT
    stored = commitment_store.get(c.id)
    assert stored.status == CommitmentStatus.READY_TO_ACT
    assert stored.status != CommitmentStatus.COMPLETED


# ---------------------------------------------------------------------------
# 5. Approval requires explicit user action & causes completion through existing mechanism
# ---------------------------------------------------------------------------

def test_approval_requires_explicit_user_action_and_completes():
    c = seed_q3_demo(live_agent=False)
    assert commitment_store.get(c.id).status == CommitmentStatus.READY_TO_ACT

    # Explicit POST request to /api/approve
    handler = _make_handler("POST", "/api/approve", {"commitment_id": c.id})
    handler.do_POST()
    status, data = _get_response_data(handler)

    assert status == 200
    assert data["commitment_id"] == c.id
    assert data["status"] == "COMPLETED"

    # Verify state updated in store
    stored = commitment_store.get(c.id)
    assert stored.status == CommitmentStatus.COMPLETED

    # Verify updated summary counts via GET
    handler_get = _make_handler("GET", "/api/commitments")
    handler_get.do_GET()
    status_get, data_get = _get_response_data(handler_get)
    assert data_get["summary"]["need_you"] == 0
    assert data_get["summary"]["closed"] == 1


# ---------------------------------------------------------------------------
# 6. Q3 seed path does not use old hard-coded $4.2M / $850k figures
# ---------------------------------------------------------------------------

def test_q3_seed_path_does_not_use_old_hardcoded_figures():
    c = seed_q3_demo(live_agent=False)
    draft = commitment_store.get_draft(c.id)

    assert draft is not None
    assert "$4.2M" not in draft
    assert "$850k" not in draft


# ---------------------------------------------------------------------------
# 7. Seeded draft contains evidence from doc-q3-figures
# ---------------------------------------------------------------------------

def test_seeded_draft_contains_evidence_from_doc_q3_figures():
    c = seed_q3_demo(live_agent=False)
    draft = commitment_store.get_draft(c.id)

    assert draft is not None
    # Must contain facts from doc-q3-figures (e.g. 42,700,000 or 42.7M revenue)
    assert ("42,700,000" in draft or "42.7" in draft or "Revenue" in draft)
    assert ("6,120,000" in draft or "6.12" in draft or "Net Income" in draft or "Gross Profit" in draft)


# ---------------------------------------------------------------------------
# 8. Reset endpoint produces empty store
# ---------------------------------------------------------------------------

def test_reset_endpoint_produces_empty_store():
    seed_q3_demo(live_agent=False)
    assert len(commitment_store.all()) > 0

    handler = _make_handler("POST", "/api/reset")
    handler.do_POST()
    status, data = _get_response_data(handler)

    assert status == 200
    assert data["status"] == "cleared"
    assert data["summary"]["total"] == 0
    assert len(commitment_store.all()) == 0


# ---------------------------------------------------------------------------
# 9. Processing messages creates commitments through detector path
# ---------------------------------------------------------------------------

def test_processing_messages_creates_commitments_through_detector_path():
    handler = _make_handler("POST", "/api/process-messages")
    handler.do_POST()
    status, data = _get_response_data(handler)

    assert status == 200
    assert data["status"] == "processed"
    
    items = commitment_store.all()
    assert len(items) >= 2
    
    # Q3 report -> READY_TO_ACT
    q3_item = next((c for c in items if "Q3" in c.action), None)
    assert q3_item is not None
    assert q3_item.status == CommitmentStatus.READY_TO_ACT
    
    # Hotfix -> WAITING_FOR_DEPENDENCY
    hotfix_item = next((c for c in items if "hotfix" in c.action.lower()), None)
    assert hotfix_item is not None
    assert hotfix_item.status == CommitmentStatus.WAITING_FOR_DEPENDENCY


# ---------------------------------------------------------------------------
# 10. Dashboard counts reflect actual store state after processing messages
# ---------------------------------------------------------------------------

def test_dashboard_counts_reflect_actual_store_state_after_processing():
    handler = _make_handler("POST", "/api/process-messages")
    handler.do_POST()

    handler_get = _make_handler("GET", "/api/commitments")
    handler_get.do_GET()
    status, data = _get_response_data(handler_get)

    assert status == 200
    expected_need_you = len([c for c in commitment_store.all() if c.status in (CommitmentStatus.READY_TO_ACT, CommitmentStatus.WAITING_FOR_USER)])
    expected_handling = len([c for c in commitment_store.all() if c.status == CommitmentStatus.WAITING_FOR_DEPENDENCY])
    assert data["summary"]["need_you"] == expected_need_you
    assert data["summary"]["im_handling"] == expected_handling
    assert data["summary"]["closed"] == 0
    assert data["summary"]["total"] == len(commitment_store.all())


# ---------------------------------------------------------------------------
# 11. Q3 draft remains evidence-grounded after message processing
# ---------------------------------------------------------------------------

def test_q3_draft_remains_evidence_grounded_after_processing():
    _make_handler("POST", "/api/process-messages").do_POST()

    items = commitment_store.all()
    q3_item = next(c for c in items if "Q3" in c.action)
    draft = commitment_store.get_draft(q3_item.id)

    assert draft is not None
    assert "[DRAFT]" in draft
    assert "$4.2M" not in draft
    assert ("42,700,000" in draft or "42.7" in draft or "Revenue" in draft)


# ---------------------------------------------------------------------------
# 12. Dependency resolution updates existing waiting commitment without duplicates
# ---------------------------------------------------------------------------

def test_dependency_resolution_updates_existing_waiting_commitment_without_duplicates():
    # First process messages to get Q3 (READY_TO_ACT) and Hotfix (WAITING_FOR_DEPENDENCY)
    _make_handler("POST", "/api/process-messages").do_POST()
    count_before = len(commitment_store.all())

    # Call resolve-dependency
    handler = _make_handler("POST", "/api/resolve-dependency")
    handler.do_POST()
    status, data = _get_response_data(handler)

    assert status == 200
    assert data["status"] == "resolved"

    items = commitment_store.all()
    # CRITICAL: Count must remain same (no duplicate hotfix commitment created)
    assert len(items) == count_before

    hotfix_item = next(c for c in items if "hotfix" in c.action.lower())
    assert hotfix_item.status == CommitmentStatus.READY_TO_ACT


# ---------------------------------------------------------------------------
# 13. Approval completes Q3 commitment and updates dashboard
# ---------------------------------------------------------------------------

def test_approval_completes_q3_and_updates_dashboard():
    _make_handler("POST", "/api/process-messages").do_POST()
    items = commitment_store.all()
    q3_item = next(c for c in items if "Q3" in c.action)

    # Approve Q3 commitment
    handler_app = _make_handler("POST", "/api/approve", {"commitment_id": q3_item.id})
    handler_app.do_POST()
    status_app, data_app = _get_response_data(handler_app)

    assert status_app == 200
    assert data_app["status"] == "COMPLETED"

    # Verify store and dashboard counts
    assert commitment_store.get(q3_item.id).status == CommitmentStatus.COMPLETED

    handler_get = _make_handler("GET", "/api/commitments")
    handler_get.do_GET()
    _, data_get = _get_response_data(handler_get)

    assert data_get["summary"]["closed"] == 1


# ---------------------------------------------------------------------------
# 14. READY_TO_ACT without draft has has_draft=False
# ---------------------------------------------------------------------------

def test_ready_to_act_without_draft_has_draft_is_false():
    c = Commitment.create("Action without draft", "owner", status=CommitmentStatus.READY_TO_ACT)
    commitment_store.add(c)

    serialized = serialise_commitment_for_ui(c)
    assert serialized["has_draft"] is False
    assert serialized["draft"] is None


# ---------------------------------------------------------------------------
# 15. /api/approve without draft returns 400 and does not mutate commitment
# ---------------------------------------------------------------------------

def test_approve_without_draft_rejected_with_400_and_no_mutation():
    c = Commitment.create("Action without draft", "owner", status=CommitmentStatus.READY_TO_ACT)
    commitment_store.add(c)

    handler = _make_handler("POST", "/api/approve", {"commitment_id": c.id})
    handler.do_POST()
    status, data = _get_response_data(handler)

    assert status == 400
    assert "error" in data
    assert "without a prepared draft" in data["error"]

    # Verify state in store remains READY_TO_ACT
    stored = commitment_store.get(c.id)
    assert stored.status == CommitmentStatus.READY_TO_ACT
    assert stored.status != CommitmentStatus.COMPLETED


