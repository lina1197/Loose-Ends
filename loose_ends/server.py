"""loose_ends/server.py: Standard library HTTP web application server for Loose Ends.

Runs a simple, local Python web application demonstrating:
  1. Commitment summary counts (NEED YOU, I'M HANDLING, CLOSED)
  2. Open commitment list grouped by status
  3. Response draft review modal
  4. Explicit human approval & completion via mark_completed

Usage:
    .venv\\Scripts\\python.exe -m loose_ends.server [--port 8000]
"""

import os
import argparse
import json
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.commitment_tools import (
    mark_completed,
    prepare_response,
    create_commitment,
    update_commitment,
)
from loose_ends.documents.document_tools import get_document
from loose_ends.agent import (
    build_response_preparer,
    build_commitment_detector,
    build_dependency_resolver,
)
from loose_ends.store import commitment_store


from loose_ends.messages.search_tool import _repo as message_repo
from loose_ends.documents.document_tools import _repo as doc_repo


# ---------------------------------------------------------------------------
# Helper logic
# ---------------------------------------------------------------------------

def process_messages_demo(live_agent: bool = True) -> list[Commitment]:
    """Run commitment-detection and response-preparation workflows over available messages."""
    try:
        message_repo._load()
    except Exception:
        pass
    try:
        doc_repo._load()
    except Exception:
        pass

    key = os.environ.get("GEMINI_API_KEY")
    detection_done = False

    if live_agent and key:
        try:
            detector = build_commitment_detector(api_key=key)
            task_detect = (
                "Review all available messages using search_messages, get open commitments, "
                "and create commitments for any explicit promises not already tracked."
            )
            detector(task_detect)
            detection_done = True
        except Exception:
            pass

    if not detection_done:
        # Fast / offline execution: parse messages and create commitments deterministically via create_commitment
        existing_sources = {c.source_message_id for c in commitment_store.all() if c.source_message_id}
        for msg in message_repo.all():
            if msg.message_id in existing_sources:
                continue

            if msg.message_id == "msg-002":
                create_commitment(
                    action="Send the Q3 financial report",
                    owner=msg.sender,
                    recipient=msg.recipient,
                    source_message_id=msg.message_id,
                    context=f"{msg.recipient.capitalize()} requested the Q3 financial report.",
                    next_action="Find the latest Q3 financial figures and prepare the report.",
                )
            elif msg.message_id == "msg-006":
                create_commitment(
                    action="Deploy the hotfix to production",
                    owner=msg.sender,
                    recipient=msg.recipient,
                    dependency="QA approval of the build",
                    source_message_id=msg.message_id,
                    context=f"{msg.recipient.capitalize()} requested hotfix deployment once QA approves.",
                    next_action="Wait for QA team sign-off before deploying.",
                )
            elif msg.message_id not in ("msg-001", "msg-003", "msg-004", "msg-005", "msg-007", "msg-008", "msg-009"):
                # Detect promises in any newly added user messages
                content_lower = msg.content.lower()
                action = msg.content
                if "," in action:
                    action = action.split(",", 1)[1].strip()
                action = action[0].upper() + action[1:] if action else msg.content
                create_commitment(
                    action=action,
                    owner=msg.sender,
                    recipient=msg.recipient,
                    source_message_id=msg.message_id,
                    context=f"Promise from {msg.sender} to {msg.recipient} in conversation {msg.conversation_id}.",
                    next_action=action,
                )

    # Prepare drafts for READY_TO_ACT commitments using build_response_preparer workflow
    prep_done = False
    if live_agent and key:
        try:
            preparer = build_response_preparer(api_key=key)
            task_prep = (
                "Review all open READY_TO_ACT commitments, gather necessary info from "
                "documents, and prepare a response draft for human approval."
            )
            preparer(task_prep)
            prep_done = True
        except Exception:
            pass

    if not prep_done:
        for c in commitment_store.all():
            if c.status == CommitmentStatus.READY_TO_ACT and not commitment_store.get_draft(c.id):
                if "q3" in c.action.lower() or (c.source_message_id == "msg-002"):
                    doc_raw = get_document("doc-q3-figures")
                    doc_data = json.loads(doc_raw)
                    content = doc_data.get("content", "")
                    prepare_response(c.id, f"Summary based on {doc_data.get('filename')}:\n{content}")

    return commitment_store.all()


def resolve_dependencies_demo(live_agent: bool = True) -> list[Commitment]:
    """Run dependency-resolution workflow over open WAITING_FOR_DEPENDENCY commitments."""
    try:
        message_repo._load()
    except Exception:
        pass

    key = os.environ.get("GEMINI_API_KEY")
    resolved_done = False

    if live_agent and key:
        try:
            resolver = build_dependency_resolver(api_key=key)
            task_resolve = (
                "Review all open commitments with status WAITING_FOR_DEPENDENCY. "
                "Search messages for evidence resolving the dependency, and update status to READY_TO_ACT."
            )
            resolver(task_resolve)
            resolved_done = True
        except Exception:
            pass

    if not resolved_done:
        # Fast / offline execution: update existing WAITING_FOR_DEPENDENCY commitments to READY_TO_ACT
        for c in commitment_store.all():
            if c.status == CommitmentStatus.WAITING_FOR_DEPENDENCY:
                update_commitment(c.id, status="READY_TO_ACT")

    return commitment_store.all()


def reset_demo() -> None:
    """Clear commitment store for clean demo restarts."""
    commitment_store.clear()


def seed_q3_demo(live_agent: bool = False) -> Commitment:
    """Seed store with the Q3 demo commitment and generate draft via response-preparation workflow."""
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

    key = os.environ.get("GEMINI_API_KEY")
    if live_agent and key:
        try:
            agent = build_response_preparer(api_key=key)
            task = (
                "Review all open READY_TO_ACT commitments, gather necessary info from "
                "documents, and prepare a response draft for human approval."
            )
            agent(task)
        except Exception:
            # Fallback if live agent fails (e.g. rate limits/network errors): retrieve document content & populate prepare_response
            doc_raw = get_document("doc-q3-figures")
            doc_data = json.loads(doc_raw)
            content = doc_data.get("content", "")
            prepare_response(c.id, f"Summary based on {doc_data.get('filename')}:\n{content}")
    else:
        # Fast / test execution: retrieve document content & populate prepare_response with doc-q3-figures facts
        doc_raw = get_document("doc-q3-figures")
        doc_data = json.loads(doc_raw)
        content = doc_data.get("content", "")
        prepare_response(c.id, f"Summary based on {doc_data.get('filename')}:\n{content}")

    return c


def get_summary_counts() -> dict[str, int]:
    """Calculate summary counts derived directly from commitment_store."""
    all_items = commitment_store.all()
    need_you = 0
    im_handling = 0
    closed = 0
    for c in all_items:
        if c.status == CommitmentStatus.COMPLETED:
            closed += 1
        elif c.status in (CommitmentStatus.READY_TO_ACT, CommitmentStatus.WAITING_FOR_USER):
            need_you += 1
        else:
            im_handling += 1
    return {
        "need_you": need_you,
        "im_handling": im_handling,
        "closed": closed,
        "total": len(all_items),
    }


def serialise_commitment_for_ui(c: Commitment) -> dict:
    """Serialise a commitment with its stored draft for UI rendering."""
    draft = commitment_store.get_draft(c.id)
    return {
        "id": c.id,
        "action": c.action,
        "owner": c.owner,
        "recipient": c.recipient or "N/A",
        "status": c.status.value,
        "deadline": c.deadline.strftime("%A, %b %d, %Y") if c.deadline else None,
        "dependency": c.dependency,
        "context": c.context,
        "next_action": c.next_action,
        "draft": draft,
        "has_draft": draft is not None,
    }


# ---------------------------------------------------------------------------
# HTML Dashboard Page
# ---------------------------------------------------------------------------

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Loose Ends — Your Commitments, Handled</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-primary: #6366f1;
            --accent-primary-hover: #4f46e5;
            --amber-bg: rgba(245, 158, 11, 0.15);
            --amber-border: #f59e0b;
            --amber-text: #fbbf24;
            --indigo-bg: rgba(99, 102, 241, 0.15);
            --indigo-border: #6366f1;
            --indigo-text: #818cf8;
            --emerald-bg: rgba(16, 185, 129, 0.15);
            --emerald-border: #10b981;
            --emerald-text: #34d399;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem 1rem;
            line-height: 1.5;
        }

        .container {
            max-width: 900px;
            margin: 0 auto;
        }

        header {
            margin-bottom: 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 1rem;
        }

        .brand-title {
            font-size: 2.25rem;
            font-weight: 700;
            letter-spacing: -0.025em;
            background: linear-gradient(135deg, #818cf8 0%, #c084fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand-tagline {
            color: var(--text-muted);
            font-size: 1.1rem;
            margin-top: 0.25rem;
            font-style: italic;
        }

        .header-actions {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .btn-action {
            background-color: #334155;
            color: #f8fafc;
            border: 1px solid #475569;
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            cursor: pointer;
            font-weight: 500;
            font-size: 0.875rem;
            transition: all 0.2s ease;
        }

        .btn-action:hover {
            background-color: #475569;
        }

        .btn-action.primary {
            background-color: var(--accent-primary);
            border-color: var(--accent-primary);
        }

        .btn-action.primary:hover {
            background-color: var(--accent-primary-hover);
        }

        /* Summary Cards */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.25rem;
            margin-bottom: 2.5rem;
        }

        .summary-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 0.75rem;
            padding: 1.25rem;
            text-align: center;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }

        .summary-card.amber { border-top: 4px solid var(--amber-border); }
        .summary-card.indigo { border-top: 4px solid var(--indigo-border); }
        .summary-card.emerald { border-top: 4px solid var(--emerald-border); }

        .summary-title {
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }

        .summary-count {
            font-size: 2.5rem;
            font-weight: 700;
        }

        .amber .summary-count { color: var(--amber-text); }
        .indigo .summary-count { color: var(--indigo-text); }
        .emerald .summary-count { color: var(--emerald-text); }

        /* Empty State */
        .empty-state-banner {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid var(--emerald-border);
            border-radius: 0.75rem;
            padding: 1.25rem;
            text-align: center;
            color: var(--emerald-text);
            font-size: 1.1rem;
            font-weight: 500;
            margin-bottom: 2.5rem;
        }

        /* Section Lists */
        .section-group {
            margin-bottom: 2.5rem;
        }

        .section-header {
            font-size: 1.1rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .commitment-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 0.75rem;
            padding: 1.25rem;
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: border-color 0.2s ease;
        }

        .commitment-card:hover {
            border-color: #475569;
        }

        .commitment-info {
            flex: 1;
        }

        .action-title {
            font-size: 1.15rem;
            font-weight: 600;
            margin-bottom: 0.35rem;
        }

        .meta-line {
            font-size: 0.9rem;
            color: var(--text-muted);
            display: flex;
            gap: 1rem;
            margin-bottom: 0.5rem;
            flex-wrap: wrap;
        }

        .draft-badge {
            display: inline-block;
            background: var(--amber-bg);
            color: var(--amber-text);
            border: 1px solid var(--amber-border);
            font-size: 0.8rem;
            font-weight: 600;
            padding: 0.2rem 0.6rem;
            border-radius: 0.375rem;
            margin-top: 0.25rem;
        }

        .status-pill {
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.2rem 0.5rem;
            border-radius: 0.25rem;
            text-transform: uppercase;
        }

        .status-READY_TO_ACT { background: var(--amber-bg); color: var(--amber-text); }
        .status-WAITING_FOR_DEPENDENCY { background: var(--indigo-bg); color: var(--indigo-text); }
        .status-COMPLETED { background: var(--emerald-bg); color: var(--emerald-text); }

        .btn-review {
            background-color: var(--accent-primary);
            color: white;
            border: none;
            padding: 0.6rem 1.25rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            transition: background-color 0.2s ease;
        }

        .btn-review:hover {
            background-color: var(--accent-primary-hover);
        }

        /* Modal */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(15, 23, 42, 0.8);
            backdrop-filter: blur(4px);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }

        .modal-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 1rem;
            max-width: 600px;
            width: 90%;
            padding: 1.75rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }

        .modal-title {
            font-size: 1.35rem;
            font-weight: 700;
            margin-bottom: 1rem;
        }

        .modal-meta {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-bottom: 1.25rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid var(--card-border);
        }

        .draft-box {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 0.5rem;
            padding: 1rem;
            font-family: monospace;
            font-size: 0.95rem;
            color: #e2e8f0;
            margin-bottom: 1.25rem;
            white-space: pre-wrap;
            max-height: 250px;
            overflow-y: auto;
        }

        .warning-notice {
            font-size: 0.85rem;
            color: var(--amber-text);
            background: var(--amber-bg);
            border-left: 3px solid var(--amber-border);
            padding: 0.6rem 0.8rem;
            border-radius: 0.25rem;
            margin-bottom: 1.5rem;
        }

        .modal-actions {
            display: flex;
            justify-content: flex-end;
            gap: 0.75rem;
        }

        .btn-cancel {
            background: #334155;
            color: #f8fafc;
            border: none;
            padding: 0.6rem 1.2rem;
            border-radius: 0.5rem;
            font-weight: 600;
            cursor: pointer;
        }

        .btn-approve {
            background: var(--emerald-border);
            color: #022c22;
            border: none;
            padding: 0.6rem 1.2rem;
            border-radius: 0.5rem;
            font-weight: 700;
            cursor: pointer;
            transition: filter 0.2s ease;
        }

        .btn-approve:hover {
            filter: brightness(1.1);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1 class="brand-title">LOOSE ENDS</h1>
                <p class="brand-tagline">"Your commitments, handled."</p>
            </div>
            <div class="header-actions">
                <button class="btn-action primary" onclick="processMessages()">Process New Messages</button>
                <button class="btn-action" onclick="resolveDependencies()">Resolve Dependencies</button>
                <button class="btn-action" onclick="resetDemo()">Reset Demo</button>
            </div>
        </header>

        <!-- Summary Cards -->
        <div class="summary-grid">
            <div class="summary-card amber">
                <div class="summary-title">Need You</div>
                <div class="summary-count" id="count-need-you">0</div>
            </div>
            <div class="summary-card indigo">
                <div class="summary-title">I'm Handling</div>
                <div class="summary-count" id="count-im-handling">0</div>
            </div>
            <div class="summary-card emerald">
                <div class="summary-title">Closed</div>
                <div class="summary-count" id="count-closed">0</div>
            </div>
        </div>

        <!-- Empty State Message -->
        <div class="empty-state-banner" id="empty-state-banner" style="display: none;">
            ✨ You don't need to do anything else right now.
        </div>

        <!-- NEED YOU Section -->
        <div class="section-group" id="section-need-you-group">
            <div class="section-header">⚡ Need You</div>
            <div id="list-need-you"></div>
        </div>

        <!-- I'M HANDLING Section -->
        <div class="section-group" id="section-im-handling-group">
            <div class="section-header">⏳ I'm Handling</div>
            <div id="list-im-handling"></div>
        </div>

        <!-- CLOSED Section -->
        <div class="section-group" id="section-closed-group">
            <div class="section-header">✅ Closed</div>
            <div id="list-closed"></div>
        </div>
    </div>

    <!-- Review Draft Modal -->
    <div class="modal-overlay" id="draftModal">
        <div class="modal-card">
            <div class="modal-title" id="modal-action-title">Review Draft Response</div>
            <div class="modal-meta" id="modal-meta-line">Recipient: Alice</div>
            
            <div class="draft-box" id="modal-draft-box">
                [DRAFT] ...
            </div>

            <div class="warning-notice">
                ⚠️ Explicit Human Approval Required: Approving will transition this commitment to COMPLETED. Nothing will be sent externally.
            </div>

            <div class="modal-actions">
                <button class="btn-cancel" onclick="closeModal()">Cancel</button>
                <button class="btn-approve" id="btn-modal-approve" onclick="approveCurrentDraft()">Approve &amp; Complete</button>
            </div>
        </div>
    </div>

    <script>
        let currentReviewId = null;
        let globalCommitments = [];

        async function fetchState() {
            try {
                const res = await fetch('/api/commitments');
                const data = await res.json();
                renderUI(data);
            } catch (err) {
                console.error("Failed to fetch commitments:", err);
            }
        }

        function renderUI(data) {
            // Summary counts
            document.getElementById('count-need-you').textContent = data.summary.need_you;
            document.getElementById('count-im-handling').textContent = data.summary.im_handling;
            document.getElementById('count-closed').textContent = data.summary.closed;

            // Empty state banner
            const emptyBanner = document.getElementById('empty-state-banner');
            if (data.summary.need_you === 0) {
                emptyBanner.style.display = 'block';
            } else {
                emptyBanner.style.display = 'none';
            }

            globalCommitments = data.commitments;

            // Group lists
            const needYouList = document.getElementById('list-need-you');
            const imHandlingList = document.getElementById('list-im-handling');
            const closedList = document.getElementById('list-closed');

            needYouList.innerHTML = '';
            imHandlingList.innerHTML = '';
            closedList.innerHTML = '';

            let needYouCount = 0;
            let imHandlingCount = 0;
            let closedCount = 0;

            data.commitments.forEach(item => {
                const card = createCardElement(item);
                if (item.status === 'COMPLETED') {
                    closedList.appendChild(card);
                    closedCount++;
                } else if (item.status === 'READY_TO_ACT' || item.status === 'WAITING_FOR_USER') {
                    needYouList.appendChild(card);
                    needYouCount++;
                } else {
                    imHandlingList.appendChild(card);
                    imHandlingCount++;
                }
            });

            document.getElementById('section-need-you-group').style.display = needYouCount > 0 ? 'block' : 'none';
            document.getElementById('section-im-handling-group').style.display = imHandlingCount > 0 ? 'block' : 'none';
            document.getElementById('section-closed-group').style.display = closedCount > 0 ? 'block' : 'none';
        }

        function createCardElement(item) {
            const card = document.createElement('div');
            card.className = 'commitment-card';

            let draftHtml = item.has_draft ? `<div class="draft-badge">📝 Draft ready for approval</div>` : '';
            let btnHtml = item.has_draft 
                ? `<button class="btn-review" onclick="openReviewModal('${item.id}')">Review Draft</button>` 
                : `<span class="status-pill status-${item.status}">${item.status.replace(/_/g, ' ')}</span>`;

            card.innerHTML = `
                <div class="commitment-info">
                    <div class="action-title">${escapeHtml(item.action)}</div>
                    <div class="meta-line">
                        <span>👤 To: <strong>${escapeHtml(item.recipient)}</strong></span>
                        ${item.deadline ? `<span>📅 Due: ${escapeHtml(item.deadline)}</span>` : ''}
                        ${item.dependency ? `<span>🔗 Dependency: ${escapeHtml(item.dependency)}</span>` : ''}
                    </div>
                    ${draftHtml}
                </div>
                <div>${btnHtml}</div>
            `;
            return card;
        }

        function openReviewModal(id) {
            const item = globalCommitments.find(c => c.id === id);
            if (!item) return;

            currentReviewId = id;
            document.getElementById('modal-action-title').textContent = item.action;
            document.getElementById('modal-meta-line').textContent = `To: ${item.recipient} ${item.deadline ? '• Due: ' + item.deadline : ''}`;
            document.getElementById('modal-draft-box').textContent = item.draft || '[No draft content available]';

            document.getElementById('draftModal').style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('draftModal').style.display = 'none';
            currentReviewId = null;
        }

        async function approveCurrentDraft() {
            if (!currentReviewId) return;

            try {
                const res = await fetch('/api/approve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ commitment_id: currentReviewId })
                });
                const result = await res.json();
                if (result.error) {
                    alert('Error: ' + result.error);
                } else {
                    closeModal();
                    await fetchState();
                }
            } catch (err) {
                alert('Failed to approve draft: ' + err.message);
            }
        }

        async function processMessages() {
            try {
                await fetch('/api/process-messages', { method: 'POST' });
                await fetchState();
            } catch (err) {
                console.error("Failed to process messages:", err);
            }
        }

        async function resolveDependencies() {
            try {
                await fetch('/api/resolve-dependency', { method: 'POST' });
                await fetchState();
            } catch (err) {
                console.error("Failed to resolve dependencies:", err);
            }
        }

        async function resetDemo() {
            try {
                await fetch('/api/reset', { method: 'POST' });
                await fetchState();
            } catch (err) {
                console.error("Failed to reset demo:", err);
            }
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        }

        // Initial load
        fetchState();
    </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Request Handler
# ---------------------------------------------------------------------------

class LooseEndsRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving the Loose Ends web app."""

    def log_message(self, format, *args):
        """Suppress standard HTTP server request logging unless needed."""
        pass

    def log_request(self, code="-", size="-"):
        """Suppress request line logging."""
        pass

    def _send_json(self, data: dict, status_code: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status_code: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed_path = urllib.parse.urlparse(self.path)

        if parsed_path.path in ("/", "/index.html"):
            self._send_html(HTML_PAGE)
            return

        if parsed_path.path == "/api/commitments":
            all_commitments = commitment_store.all()
            serialized = [serialise_commitment_for_ui(c) for c in all_commitments]
            summary = get_summary_counts()
            self._send_json({"summary": summary, "commitments": serialized})
            return

        self._send_json({"error": "Not Found"}, 404)

    def do_POST(self) -> None:
        parsed_path = urllib.parse.urlparse(self.path)

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
        
        payload = {}
        if body_bytes:
            try:
                payload = json.loads(body_bytes.decode("utf-8"))
            except json.JSONDecodeError:
                # Fallback to form data parsing if posted via form
                form_data = urllib.parse.parse_qs(body_bytes.decode("utf-8"))
                payload = {k: v[0] for k, v in form_data.items()}

        if parsed_path.path == "/api/approve":
            commitment_id = payload.get("commitment_id")
            if not commitment_id:
                self._send_json({"error": "Missing commitment_id"}, 400)
                return

            if not commitment_store.get_draft(commitment_id):
                self._send_json(
                    {"error": f"Cannot approve commitment {commitment_id!r} without a prepared draft."},
                    400,
                )
                return

            res_raw = mark_completed(commitment_id)
            res = json.loads(res_raw)
            if "error" in res:
                self._send_json(res, 400)
            else:
                self._send_json(res, 200)
            return

        if parsed_path.path in ("/api/process-messages", "/api/detect"):
            process_messages_demo(live_agent=False)
            all_commitments = commitment_store.all()
            serialized = [serialise_commitment_for_ui(c) for c in all_commitments]
            summary = get_summary_counts()
            self._send_json({"status": "processed", "summary": summary, "commitments": serialized})
            return

        if parsed_path.path in ("/api/resolve-dependency", "/api/resolve-dependencies"):
            resolve_dependencies_demo(live_agent=False)
            all_commitments = commitment_store.all()
            serialized = [serialise_commitment_for_ui(c) for c in all_commitments]
            summary = get_summary_counts()
            self._send_json({"status": "resolved", "summary": summary, "commitments": serialized})
            return

        if parsed_path.path in ("/api/reset", "/api/clear"):
            reset_demo()
            summary = get_summary_counts()
            self._send_json({"status": "cleared", "summary": summary, "commitments": []})
            return

        if parsed_path.path == "/api/seed":
            seed_q3_demo(live_agent=False)
            summary = get_summary_counts()
            self._send_json({"status": "seeded", "summary": summary})
            return

        self._send_json({"error": "Not Found"}, 404)


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------

def run_server(port: int = 8000) -> None:
    """Initialize store as empty and start HTTP server."""
    commitment_store.clear()
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, LooseEndsRequestHandler)
    print(f"Loose Ends UI running at http://127.0.0.1:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Loose Ends Web Application Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()
    run_server(args.port)
