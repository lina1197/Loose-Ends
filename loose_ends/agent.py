"""Gemini-backed Strands agents for Loose Ends.

Three specialized commitment-management workflows are provided:

  build_commitment_detector()
    Phase 1+2: detects new commitments AND resolves dependencies.
    Has access to: search_messages, get_open_commitments,
                   create_commitment, update_commitment.

  build_dependency_resolver()
    Resolution only: inspects existing commitments and resolves blocked ones.
    Has access to: search_messages, get_open_commitments, update_commitment.
    Does NOT have create_commitment -- cannot create new commitments.

  build_action_preparer()
    Read-only action preparation: inspects READY_TO_ACT commitments and
    gathers the information needed to act on them from local documents.
    Has access to: get_open_commitments, search_documents, get_document.
    Does NOT have create_commitment, update_commitment, or search_messages.

All workflows share the same Gemini model configuration via _build_model().
"""
import os
from typing import Optional

from strands import Agent
from strands.hooks import BeforeToolCallEvent
from strands.models.gemini import GeminiModel

from loose_ends.tools import get_loose_ends_status
from loose_ends.commitment_tools import (
    create_commitment,
    get_open_commitments,
    update_commitment,
    prepare_response,
    mark_completed,
)
from loose_ends.messages.search_tool import search_messages
from loose_ends.documents.document_tools import search_documents, get_document

_GEMINI_MODEL_ID = os.environ.get("GEMINI_MODEL_ID", "gemini-3.5-flash-lite")


# ---------------------------------------------------------------------------
# Shared model factory (private) -- single place for provider configuration
# ---------------------------------------------------------------------------

def _build_model(api_key: Optional[str] = None):
    """Resolve model provider (Bedrock or Gemini) and return a configured Strands Model.

    Provider Selection Logic:
    1. If MODEL_PROVIDER == 'bedrock' or AWS credentials are in environment,
       attempts to instantiate BedrockModel.
    2. Falls back to GeminiModel using GEMINI_API_KEY.
    3. Raises RuntimeError if no model credentials/keys are configured.
    """
    provider = os.environ.get("MODEL_PROVIDER", "").lower()

    # Path 1: Amazon Bedrock (if explicitly requested or AWS credentials present)
    if provider == "bedrock" or os.environ.get("AWS_ACCESS_KEY_ID"):
        try:
            from strands.models.bedrock import BedrockModel
            bedrock_model_id = os.environ.get(
                "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
            )
            region = os.environ.get("AWS_REGION", "us-east-1")
            return BedrockModel(model_id=bedrock_model_id, region_name=region)
        except Exception:
            pass  # Fallback to GeminiModel if Bedrock import/credentials fail

    # Path 2: Google Gemini (default)
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Neither AWS Bedrock nor GEMINI_API_KEY environment variable is configured. "
            "Set GEMINI_API_KEY in .env or configure AWS credentials."
        )
    model_id = os.environ.get("GEMINI_MODEL_ID", _GEMINI_MODEL_ID)
    return GeminiModel(
        client_args={"api_key": key},
        model_id=model_id,
    )


# ---------------------------------------------------------------------------
# Step 1: proof-of-concept agent (unchanged)
# ---------------------------------------------------------------------------

def build_agent() -> Agent:
    """Construct and return the Loose Ends Strands proof-of-concept agent."""
    model = _build_model()
    return Agent(
        model=model,
        tools=[get_loose_ends_status],
        system_prompt=(
            "You are the Loose Ends agent, a minimal proof-of-concept AI "
            "assistant. When asked about the system status, you MUST call the "
            "get_loose_ends_status tool and report exactly what it returns."
        ),
    )


# ---------------------------------------------------------------------------
# Step 6: commitment-detection workflow (Phase 1 + Phase 2 combined)
# Tools: search_messages, get_open_commitments, create_commitment, update_commitment
# ---------------------------------------------------------------------------

COMMITMENT_DETECTION_TOOLS = [
    search_messages,
    get_open_commitments,
    create_commitment,
    update_commitment,
]

COMMITMENT_DETECTION_SYSTEM_PROMPT = (
    "You are a commitment-management assistant for the Loose Ends system.\n"
    "\n"
    "Your role has two phases:\n"
    "  Phase 1 - Commitment Detection: find explicit promises in messages and record them.\n"
    "  Phase 2 - Dependency Resolution: identify when a message satisfies a blocked commitment.\n"
    "\n"
    "DEFINITION OF A COMMITMENT:\n"
    "A commitment is a clear, explicit promise or obligation by a specific person to\n"
    "perform a specific action. Examples:\n"
    "  - 'I will send the report by Friday' (direct promise)\n"
    "  - 'Once QA approves, I will deploy the fix' (dependency-based promise)\n"
    "\n"
    "WHAT IS NOT A COMMITMENT:\n"
    "  - A question or request from someone else (only record who PROMISES, not who ASKS)\n"
    "  - A status update that describes the current state without a future obligation\n"
    "  - Vague intentions without a clear action or owner\n"
    "\n"
    "PHASE 1 - COMMITMENT DETECTION (mandatory rules):\n"
    "1. Call search_messages (no filters) to retrieve all messages.\n"
    "2. Call get_open_commitments to check what is already tracked.\n"
    "3. For each explicit promise NOT already tracked, call create_commitment.\n"
    "4. The 'owner' is the person who made the promise.\n"
    "   The 'recipient' is the person they promised.\n"
    "5. If the promise is conditional on a dependency, include that dependency.\n"
    "6. Do not invent deadlines, recipients, or context not in the messages.\n"
    "\n"
    "PHASE 2 - DEPENDENCY RESOLUTION (mandatory rules):\n"
    "7. After detection, review all WAITING_FOR_DEPENDENCY commitments.\n"
    "8. For each blocked commitment, read its 'dependency' field carefully.\n"
    "9. Examine the messages for one that directly and explicitly confirms\n"
    "   the dependency is now resolved.\n"
    "   Example: 'QA has approved the build' satisfies 'waiting for QA approval'.\n"
    "   A tangential or unrelated mention of the same keyword does NOT satisfy it.\n"
    "10. If you find clear, direct evidence that a dependency is resolved, call\n"
    "    update_commitment with status='READY_TO_ACT' for that commitment.\n"
    "11. Never update a commitment based on assumed or inferred evidence.\n"
    "    The supporting message must explicitly confirm the dependency is done.\n"
    "\n"
    "FINAL STEP:\n"
    "After both phases, summarize:\n"
    "  - new commitments created\n"
    "  - dependencies resolved\n"
    "  - commitments that remain blocked and why\n"
)


# ---------------------------------------------------------------------------
# Strands Runtime Hooks & Guardrails (Deterministic Agent Controls)
# ---------------------------------------------------------------------------

def enforce_human_approval_guardrail(event: BeforeToolCallEvent) -> None:
    """Deterministic Strands runtime hook (Guardrail).

    Enforces that:
    1. No tool can directly transition any commitment to COMPLETED (human approval required).
    2. Commitments created without a valid owner are rejected before execution.
    """
    tool_use = event.tool_use or {}
    tool_name = tool_use.get("name") if isinstance(tool_use, dict) else getattr(tool_use, "name", None)
    tool_args = (tool_use.get("input") or {}) if isinstance(tool_use, dict) else (getattr(tool_use, "input", {}) or {})

    if tool_name == "update_commitment" and tool_args.get("status") == "COMPLETED":
        raise ValueError(
            "Guardrail Triggered: Automatic completion rejected. "
            "Commitments can ONLY be completed via explicit human approval."
        )
    if tool_name == "create_commitment" and not tool_args.get("owner"):
        raise ValueError("Guardrail Triggered: Commitment owner must not be empty.")


def build_commitment_detector(api_key: Optional[str] = None) -> Agent:
    """Construct the commitment-detection agent (Phase 1 + Phase 2).

    Has access to all four commitment tools including create_commitment.

    Parameters
    ----------
    api_key:
        Gemini API key. Falls back to GEMINI_API_KEY env var.
        Pass an explicit value in tests to avoid requiring the env var.
    """
    return Agent(
        model=_build_model(api_key),
        tools=COMMITMENT_DETECTION_TOOLS,
        system_prompt=COMMITMENT_DETECTION_SYSTEM_PROMPT,
        hooks=[enforce_human_approval_guardrail],
    )


# ---------------------------------------------------------------------------
# Step 8: dependency-resolution workflow (focused, no create_commitment)
# Tools: search_messages, get_open_commitments, update_commitment
# ---------------------------------------------------------------------------

DEPENDENCY_RESOLUTION_TOOLS = [
    search_messages,
    get_open_commitments,
    update_commitment,
]

DEPENDENCY_RESOLUTION_SYSTEM_PROMPT = (
    "You are a dependency-resolution assistant for the Loose Ends system.\n"
    "\n"
    "YOUR ONLY JOB:\n"
    "Inspect existing open commitments that are blocked (WAITING_FOR_DEPENDENCY)\n"
    "and determine whether any available message provides direct evidence that\n"
    "the blocking dependency has been satisfied. If it has, transition the\n"
    "commitment to READY_TO_ACT using update_commitment.\n"
    "\n"
    "WHAT YOU MUST NOT DO:\n"
    "  - Do NOT create new commitments. The create_commitment tool is NOT\n"
    "    available to you and must not be called.\n"
    "  - Do NOT invent or assume evidence. A message must clearly and explicitly\n"
    "    confirm the dependency is resolved, not merely mention the same topic.\n"
    "  - Do NOT resolve a dependency based on keyword overlap alone.\n"
    "    Example of sufficient evidence:\n"
    "      Dependency: 'QA approval of the build'\n"
    "      Message: 'QA has approved the build. You are clear to proceed.'\n"
    "    Example that is NOT sufficient:\n"
    "      Message: 'QA is still reviewing the build.' (not a confirmation)\n"
    "  - Do NOT modify any commitment field unless the update is genuinely\n"
    "    necessary to reflect a resolved dependency.\n"
    "\n"
    "MANDATORY STEPS:\n"
    "1. Call search_messages (no filters) to retrieve all available messages.\n"
    "2. Call get_open_commitments to see all currently tracked commitments.\n"
    "3. For each commitment with status WAITING_FOR_DEPENDENCY:\n"
    "   a. Read its 'dependency' field carefully.\n"
    "   b. Look through the messages for one that explicitly confirms\n"
    "      the dependency is now resolved.\n"
    "   c. If -- and only if -- you find such a message, call\n"
    "      update_commitment with status='READY_TO_ACT'.\n"
    "4. For commitments whose dependency is NOT yet confirmed by a message,\n"
    "   leave them unchanged and note them as still blocked.\n"
    "\n"
    "FINAL STEP:\n"
    "Summarize:\n"
    "  - which commitments you checked\n"
    "  - which dependency was resolved and by which message\n"
    "  - which commitments remain blocked and why\n"
    "  - the final status of every commitment you examined\n"
)


def build_dependency_resolver(api_key: Optional[str] = None) -> Agent:
    """Construct the dependency-resolution agent.

    This agent has access to ONLY search_messages, get_open_commitments,
    and update_commitment.  It cannot create new commitments.

    Parameters
    ----------
    api_key:
        Gemini API key. Falls back to GEMINI_API_KEY env var.
        Pass an explicit value in tests to avoid requiring the env var.
    """
    return Agent(
        model=_build_model(api_key),
        tools=DEPENDENCY_RESOLUTION_TOOLS,
        system_prompt=DEPENDENCY_RESOLUTION_SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Step 10: action-preparation workflow (read-only)
# Tools: get_open_commitments, search_documents, get_document
# NOT: create_commitment, update_commitment, search_messages
# ---------------------------------------------------------------------------

ACTION_PREPARATION_TOOLS = [
    get_open_commitments,
    search_documents,
    get_document,
]

ACTION_PREPARATION_SYSTEM_PROMPT = (
    "You are an action-preparation assistant for the Loose Ends system.\n"
    "\n"
    "YOUR ONLY JOB:\n"
    "Review existing READY_TO_ACT commitments and gather the information needed\n"
    "to act on them. Use the commitment's action, recipient, context, and\n"
    "next_action fields to guide your document search.\n"
    "\n"
    "WHAT YOU MUST NOT DO:\n"
    "  - Do NOT create new commitments. create_commitment is not available.\n"
    "  - Do NOT change the status of any commitment. update_commitment is not\n"
    "    available. This workflow is strictly read-only.\n"
    "  - Do NOT resolve dependency conditions. That is a separate workflow.\n"
    "  - Do NOT search messages. search_messages is not available here.\n"
    "  - Do NOT invent information that is not in the retrieved documents.\n"
    "  - Do NOT assume a document is relevant based solely on a shared keyword.\n"
    "    Verify relevance by reading the document content.\n"
    "\n"
    "MANDATORY STEPS:\n"
    "1. Call get_open_commitments to see all currently tracked commitments.\n"
    "2. Focus on commitments with status READY_TO_ACT.\n"
    "3. For each READY_TO_ACT commitment:\n"
    "   a. Read its action, context, and next_action fields carefully.\n"
    "   b. Derive a specific search query from the commitment content.\n"
    "      Use precise terms from the action description, not generic words.\n"
    "   c. Call search_documents with that query to find candidate documents.\n"
    "   d. From the search results, identify the most relevant document.\n"
    "   e. Call get_document to retrieve its full content.\n"
    "   f. Read the content and assess whether it contains sufficient\n"
    "      information to fulfil the commitment's next action.\n"
    "4. Report for each READY_TO_ACT commitment:\n"
    "   - the document(s) found and their relevance\n"
    "   - key information retrieved (e.g., figures, data points)\n"
    "   - whether sufficient information is available\n"
    "   - what is still missing, if anything\n"
    "\n"
    "FINAL STEP:\n"
    "Summarize whether each commitment has sufficient information to proceed\n"
    "to response preparation, and identify any information gaps.\n"
    "Do not alter any commitment's status or create any new records.\n"
)


def build_action_preparer(api_key: Optional[str] = None) -> Agent:
    """Construct the read-only action-preparation agent.

    This agent has access to ONLY get_open_commitments, search_documents,
    and get_document.  It cannot create or update any commitment, and it
    cannot search messages.  Its sole purpose is information gathering.

    Parameters
    ----------
    api_key:
        Gemini API key. Falls back to GEMINI_API_KEY env var.
        Pass an explicit value in tests to avoid requiring the env var.
    """
    return Agent(
        model=_build_model(api_key),
        tools=ACTION_PREPARATION_TOOLS,
        system_prompt=ACTION_PREPARATION_SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Step 11: response-preparation workflow
# Tools: get_open_commitments, search_documents, get_document, prepare_response
# NOT: create_commitment, update_commitment, search_messages
# ---------------------------------------------------------------------------

RESPONSE_PREPARATION_TOOLS = [
    get_open_commitments,
    search_documents,
    get_document,
    prepare_response,
]

RESPONSE_PREPARATION_SYSTEM_PROMPT = (
    "You are a response-preparation assistant for the Loose Ends system.\n"
    "\n"
    "YOUR ONLY JOB:\n"
    "Review existing READY_TO_ACT commitments, gather necessary information from\n"
    "documents, and prepare a draft response for human approval.\n"
    "\n"
    "WHAT YOU MUST NOT DO:\n"
    "  - Do NOT create new commitments.\n"
    "  - Do NOT change the status of any commitment.\n"
    "  - Do NOT search messages.\n"
    "  - Do NOT send the response directly.\n"
    "\n"
    "MANDATORY STEPS:\n"
    "1. Call get_open_commitments to find READY_TO_ACT commitments.\n"
    "2. Use search_documents and get_document to gather information.\n"
    "3. Call prepare_response to create a DRAFT for human approval.\n"
    "\n"
    "FINAL STEP:\n"
    "Summarize the drafts prepared and confirm they await human approval.\n"
)


def build_response_preparer(api_key: Optional[str] = None) -> Agent:
    """Construct the response-preparation agent.

    This agent has access to ONLY get_open_commitments, search_documents,
    get_document, and prepare_response. It cannot create or update any
    commitment, and it cannot search messages. Its sole purpose is to
    draft a response for human approval.

    Parameters
    ----------
    api_key:
        Gemini API key. Falls back to GEMINI_API_KEY env var.
        Pass an explicit value in tests to avoid requiring the env var.
    """
    return Agent(
        model=_build_model(api_key),
        tools=RESPONSE_PREPARATION_TOOLS,
        system_prompt=RESPONSE_PREPARATION_SYSTEM_PROMPT,
    )