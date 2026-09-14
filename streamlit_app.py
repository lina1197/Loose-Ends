"""streamlit_app.py: Interactive Streamlit Web Application for Loose Ends 🧵.

Deterministic Commitment Tracking & Follow-through Agent Powered by Strands Agents SDK.
"""
import os
import json
from datetime import datetime, timezone
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Page configuration - MUST BE FIRST STREAMLIT COMMAND
st.set_page_config(
    page_title="Loose Ends 🧵 - Commitment Tracking Agent",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import internal modules
from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.store import commitment_store
from loose_ends.commitment_tools import (
    mark_completed,
    prepare_response,
    create_commitment,
    update_commitment,
)
from loose_ends.documents.document_tools import get_document
from loose_ends.agent import (
    build_commitment_detector,
    build_dependency_resolver,
    build_response_preparer,
)
from loose_ends.messages.search_tool import _repo as message_repo
from loose_ends.documents.document_tools import _repo as doc_repo
from loose_ends.server import process_messages_demo, resolve_dependencies_demo


# Custom CSS styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #a5b4fc 0%, #6366f1 50%, #4338ca 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #94a3b8;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #f8fafc;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }
    .badge-ready { background-color: rgba(99, 102, 241, 0.2); color: #818cf8; border: 1px solid #6366f1; }
    .badge-waiting { background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }
    .badge-completed { background-color: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }
    .commitment-card {
        background: #1e293b;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .draft-box {
        background: #0f172a;
        border-left: 4px solid #6366f1;
        border-radius: 6px;
        padding: 1rem;
        font-family: monospace;
        color: #e2e8f0;
        margin-top: 0.75rem;
        white-space: pre-wrap;
    }
    .guardrail-tag {
        font-size: 0.75rem;
        color: #ec4899;
        background: rgba(236, 72, 153, 0.1);
        border: 1px solid rgba(236, 72, 153, 0.3);
        padding: 0.2rem 0.6rem;
        border-radius: 4px;
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
    }
</style>
""", unsafe_allow_html=True)


# Initialize Session State
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    # Seed initial demo commitments if empty
    if len(commitment_store.all()) == 0:
        process_messages_demo(live_agent=False)

# Header Section
col_title, col_logo = st.columns([4, 1])
with col_title:
    st.markdown('<div class="main-header">Loose Ends 🧵</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Deterministic Commitment Tracking & Follow-through Agent Powered by <b>Strands Agents SDK</b></div>', unsafe_allow_html=True)

# Sidebar Controls
st.sidebar.image("https://raw.githubusercontent.com/strands-ai/assets/main/banner.png", use_container_width=True) if os.path.exists("banner.png") else None
st.sidebar.title("🎛️ Control Center")

api_key_input = st.sidebar.text_input(
    "Google Gemini API Key",
    value=os.environ.get("GEMINI_API_KEY", ""),
    type="password",
    help="Provided API key will enable live LLM agents. Leave empty to use deterministic local mock agents.",
)
if api_key_input:
    os.environ["GEMINI_API_KEY"] = api_key_input

st.sidebar.markdown("---")
st.sidebar.subheader("⚡ Agent Workflows")

col_sb1, col_sb2 = st.sidebar.columns(2)
with col_sb1:
    if st.button("🔍 Detect Promises", use_container_width=True, help="Scan message logs for explicit commitments"):
        with st.spinner("Detecting commitments..."):
            process_messages_demo(live_agent=bool(os.environ.get("GEMINI_API_KEY")))
            st.toast("Commitment detection complete!", icon="✅")
            st.rerun()

with col_sb2:
    if st.button("⚡ Resolve Dependencies", use_container_width=True, help="Run steering agent to verify dependencies"):
        with st.spinner("Resolving dependencies..."):
            resolve_dependencies_demo(live_agent=bool(os.environ.get("GEMINI_API_KEY")))
            st.toast("Dependency resolution complete!", icon="🚀")
            st.rerun()

st.sidebar.markdown("---")

# Message simulation form in sidebar
with st.sidebar.expander("💬 Simulate Workplace Message", expanded=False):
    with st.form("new_message_form"):
        sender = st.selectbox("Sender", ["bob", "dave", "alice", "carol", "eve", "frank"])
        recipient = st.selectbox("Recipient", ["alice", "bob", "carol", "dave", "frank", "eve"])
        msg_text = st.text_area("Message Content", placeholder="e.g. I promise to send the budget review by 4pm.")
        submitted = st.form_submit_button("Send & Run Detection")
        if submitted and msg_text:
            msg_id = f"msg-custom-{int(datetime.now().timestamp())}"
            new_msg = {
                "message_id": msg_id,
                "sender": sender,
                "recipient": recipient,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "content": msg_text,
                "conversation_id": f"conv-{sender}-{recipient}",
            }
            # Append to message repo
            message_repo._messages.append(
                type("Message", (), new_msg)()
            )
            # Create commitment deterministically or via agent
            create_commitment(
                action=msg_text,
                owner=sender,
                recipient=recipient,
                source_message_id=msg_id,
                context=f"Simulated message from {sender} to {recipient}.",
                next_action=f"Fulfill commitment: {msg_text}",
            )
            st.success("Message recorded & commitment created!")
            st.rerun()

if st.sidebar.button("🗑️ Reset Commitment Store", use_container_width=True):
    commitment_store.clear()
    process_messages_demo(live_agent=False)
    st.toast("Store reset to initial state.", icon="🔄")
    st.rerun()

# System Metrics Bar
all_commitments = commitment_store.all()
ready_count = sum(1 for c in all_commitments if c.status == CommitmentStatus.READY_TO_ACT)
waiting_count = sum(1 for c in all_commitments if c.status == CommitmentStatus.WAITING_FOR_DEPENDENCY)
completed_count = sum(1 for c in all_commitments if c.status == CommitmentStatus.COMPLETED)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(f'<div class="metric-card"><div class="metric-value">{len(all_commitments)}</div><div class="metric-label">Total Tracked</div></div>', unsafe_allow_html=True)
with m2:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#818cf8;">{ready_count}</div><div class="metric-label">Ready to Act (Need Action)</div></div>', unsafe_allow_html=True)
with m3:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#fbbf24;">{waiting_count}</div><div class="metric-label">Waiting for Dependency</div></div>', unsafe_allow_html=True)
with m4:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#34d399;">{completed_count}</div><div class="metric-label">Completed</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Main Workspace Tabs
tab_action, tab_waiting, tab_closed, tab_messages, tab_docs, tab_arch = st.tabs([
    "📥 Need Action / Draft Review",
    "⏳ Waiting for Dependency",
    "✅ Closed Commitments",
    "💬 Message Stream",
    "📄 Document Vault",
    "🏗️ Architecture & SDK",
])

# TAB 1: NEED ACTION / DRAFT REVIEW
with tab_action:
    st.subheader("Commitments Ready for Human Approval")
    ready_items = [c for c in all_commitments if c.status == CommitmentStatus.READY_TO_ACT]
    
    if not ready_items:
        st.info("No pending commitments require action right now. All caught up! 🎉")
    else:
        for c in ready_items:
            with st.container():
                st.markdown(f"""
                <div class="commitment-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h4 style="margin: 0; color: #f8fafc;">🎯 {c.action}</h4>
                        <span class="status-badge badge-ready">READY TO ACT</span>
                    </div>
                    <div style="color: #94a3b8; font-size: 0.9rem; margin-top: 0.4rem;">
                        <b>Owner:</b> {c.owner.capitalize()} &nbsp; | &nbsp; <b>Recipient:</b> {c.recipient.capitalize()} &nbsp; | &nbsp; <b>Source:</b> <code>{c.source_message_id or 'Manual'}</code>
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.9rem; color: #cbd5e1;">
                        <b>Context:</b> {c.context or 'No additional context provided.'}<br>
                        <b>Next Action:</b> {c.next_action or 'Review draft response below.'}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                draft = commitment_store.get_draft(c.id)
                col_d1, col_d2 = st.columns([3, 1])

                with col_d1:
                    if draft:
                        st.markdown("**Prepared Response Draft (Pending Human Review):**")
                        st.markdown(f'<div class="draft-box">{draft}</div>', unsafe_allow_html=True)
                    else:
                        st.warning("No draft generated yet. Click below to generate a context draft.")

                with col_d2:
                    st.markdown('<div class="guardrail-tag">🛡️ Guardrail Enforced</div>', unsafe_allow_html=True)
                    st.caption("Human approval required before completion tool execution.")

                    if not draft:
                        if st.button("📝 Prepare Draft", key=f"prep_{c.id}", use_container_width=True):
                            doc_raw = get_document("doc-q3-figures")
                            doc_data = json.loads(doc_raw)
                            prepare_response(c.id, f"Summary based on {doc_data.get('filename')}:\n{doc_data.get('content')}")
                            st.success("Draft generated!")
                            st.rerun()

                    if st.button("✅ Approve & Complete", key=f"app_{c.id}", type="primary", use_container_width=True):
                        mark_completed(c.id)
                        st.balloons()
                        st.toast(f"Commitment '{c.action}' approved & completed!", icon="🎉")
                        st.rerun()

            st.markdown("---")

# TAB 2: WAITING FOR DEPENDENCY
with tab_waiting:
    st.subheader("Commitments Blocked by External Dependencies")
    waiting_items = [c for c in all_commitments if c.status == CommitmentStatus.WAITING_FOR_DEPENDENCY]

    if not waiting_items:
        st.info("No commitments are currently waiting on external dependencies.")
    else:
        for c in waiting_items:
            st.markdown(f"""
            <div class="commitment-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h4 style="margin: 0; color: #f8fafc;">⏳ {c.action}</h4>
                    <span class="status-badge badge-waiting">WAITING FOR DEPENDENCY</span>
                </div>
                <div style="color: #94a3b8; font-size: 0.9rem; margin-top: 0.4rem;">
                    <b>Owner:</b> {c.owner.capitalize()} &nbsp; | &nbsp; <b>Recipient:</b> {c.recipient.capitalize()}
                </div>
                <div style="margin-top: 0.75rem; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); padding: 0.75rem; border-radius: 6px;">
                    <b style="color: #fbbf24;">Blocked On:</b> {c.dependency or 'External sign-off / build approval'}
                </div>
                <div style="margin-top: 0.5rem; font-size: 0.85rem; color: #94a3b8;">
                    <b>Steering Resolver Status:</b> Waiting for direct evidence in message logs (e.g. QA approval message msg-007).
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("⚡ Run Dependency Resolution Check", key=f"res_{c.id}"):
                with st.spinner("Checking message logs for evidence..."):
                    resolve_dependencies_demo(live_agent=bool(os.environ.get("GEMINI_API_KEY")))
                    st.toast("Dependency check completed!", icon="🔍")
                    st.rerun()

# TAB 3: CLOSED COMMITMENTS
with tab_closed:
    st.subheader("Successfully Fulfilled & Completed Commitments")
    closed_items = [c for c in all_commitments if c.status == CommitmentStatus.COMPLETED]

    if not closed_items:
        st.info("No completed commitments yet.")
    else:
        for c in closed_items:
            st.markdown(f"""
            <div class="commitment-card" style="border-color: rgba(16, 185, 129, 0.3);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h4 style="margin: 0; color: #f8fafc;">✅ {c.action}</h4>
                    <span class="status-badge badge-completed">COMPLETED</span>
                </div>
                <div style="color: #94a3b8; font-size: 0.9rem; margin-top: 0.4rem;">
                    <b>Owner:</b> {c.owner.capitalize()} &nbsp; | &nbsp; <b>Recipient:</b> {c.recipient.capitalize()} &nbsp; | &nbsp; <b>Updated:</b> {c.updated_at.strftime('%Y-%m-%d %H:%M UTC')}
                </div>
            </div>
            """, unsafe_allow_html=True)

# TAB 4: MESSAGE STREAM
with tab_messages:
    st.subheader("Workspace Message Streams & Communication Logs")
    st.caption("Raw communication logs ingested by Phase 1 Commitment Detector Agent.")
    
    msgs = message_repo.all()
    for m in msgs:
        with st.expander(f"💬 [{m.timestamp[:16]}] {m.sender.capitalize()} ➔ {m.recipient.capitalize()} ({m.message_id})"):
            st.write(m.content)
            st.caption(f"Conversation ID: {m.conversation_id}")

# TAB 5: DOCUMENT VAULT
with tab_docs:
    st.subheader("Knowledge Base & Enterprise Documents")
    st.caption("Read-only document store queried by Phase 3 Action Preparer Agent.")

    docs = doc_repo.all()
    for d in docs:
        with st.expander(f"📄 {d.title} ({d.filename})"):
            st.code(d.content, language="text")

# TAB 6: ARCHITECTURE & SDK
with tab_arch:
    st.subheader("🏗️ Multi-Agent Lifecycle & Architecture")

    st.markdown("""
```mermaid
graph TD
    A[Message Streams / Communication Logs] --> B[Phase 1: Commitment Detector Agent]
    B -->|Hooks Guardrail Enforced| C[Commitment Store]
    C --> D[Phase 2: Steering Dependency Resolver]
    D -->|Evidence Verified| E[READY_TO_ACT State]
    E --> F[Phase 3: Action Preparer & Response Draft]
    F --> G[Human-in-the-Loop Approval UI]
    G -->|User Approves| H[COMPLETED]
```
    """)

    st.markdown("""
    ### Technical Highlights (Strands Agents SDK)
    1. **Model Agnostic**: Swappable between Google Gemini, AWS Bedrock, and offline mock fallbacks.
    2. **Runtime Guardrails (`BeforeToolCallEvent`)**: Intercepts tool execution to prevent unauthorized status changes or external actions without explicit human approval.
    3. **Dual-Agent Verification**: Steering agents cross-check blocked dependencies against incoming logs to prevent premature activation.
    4. **Scoped Tools**: Toolsets strictly scoped per phase (`commitment_tools`, `document_tools`).
    """)

# Footer
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #64748b; font-size: 0.85rem;">'
    'Loose Ends 🧵 &bull; Deterministic Commitment Management Agent &bull; Powered by Strands Agents SDK'
    '</div>',
    unsafe_allow_html=True,
)
