"""lambda_function.py: AWS Lambda entry point for Loose Ends.

Adapts HTTP requests from AWS API Gateway to the Loose Ends agentic backend.
Supports running with Amazon Bedrock, Google Gemini, or offline deterministic fallback.
"""

import json
import os
from datetime import datetime, timezone

from loose_ends.domain.commitment import Commitment, CommitmentStatus
from loose_ends.store import commitment_store
from loose_ends.server import (
    process_messages_demo,
    resolve_dependencies_demo,
    reset_demo,
    seed_q3_demo,
    get_summary_counts,
    serialise_commitment_for_ui,
)


def _json_response(status_code: int, body_dict: dict) -> dict:
    """Format a standard API Gateway proxy response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
        },
        "body": json.dumps(body_dict),
    }


def lambda_handler(event: dict, context: object) -> dict:
    """AWS Lambda entry point for API Gateway HTTP API routes."""
    request_context = event.get("requestContext", {})
    http = request_context.get("http", {})
    method = http.get("method", event.get("httpMethod", "GET")).upper()
    path = event.get("rawPath", event.get("path", "/"))

    # CORS preflight
    if method == "OPTIONS":
        return _json_response(200, {"status": "ok"})

    # GET /api/commitments
    if path == "/api/commitments" and method == "GET":
        all_commitments = commitment_store.all()
        serialized = [serialise_commitment_for_ui(c) for c in all_commitments]
        summary = get_summary_counts()
        return _json_response(200, {"summary": summary, "commitments": serialized})

    # POST /api/process-messages
    if path in ("/api/process-messages", "/api/detect") and method == "POST":
        process_messages_demo(live_agent=True)
        all_commitments = commitment_store.all()
        serialized = [serialise_commitment_for_ui(c) for c in all_commitments]
        summary = get_summary_counts()
        return _json_response(200, {"status": "processed", "summary": summary, "commitments": serialized})

    # POST /api/resolve-dependency
    if path in ("/api/resolve-dependency", "/api/resolve-dependencies") and method == "POST":
        resolve_dependencies_demo(live_agent=True)
        all_commitments = commitment_store.all()
        serialized = [serialise_commitment_for_ui(c) for c in all_commitments]
        summary = get_summary_counts()
        return _json_response(200, {"status": "resolved", "summary": summary, "commitments": serialized})

    # POST /api/approve
    if path == "/api/approve" and method == "POST":
        body_raw = event.get("body", "{}")
        try:
            body = json.loads(body_raw) if body_raw else {}
        except Exception:
            body = {}
        commitment_id = body.get("commitment_id")
        if not commitment_id:
            return _json_response(400, {"error": "Missing commitment_id parameter"})
        if not commitment_store.get_draft(commitment_id):
            return _json_response(400, {"error": f"Cannot approve commitment {commitment_id!r} without a prepared draft."})

        from loose_ends.commitment_tools import mark_completed
        res_raw = mark_completed(commitment_id)
        res = json.loads(res_raw)
        status_code = 400 if "error" in res else 200
        return _json_response(status_code, res)

    # POST /api/reset
    if path in ("/api/reset", "/api/clear") and method == "POST":
        reset_demo()
        summary = get_summary_counts()
        return _json_response(200, {"status": "cleared", "summary": summary, "commitments": []})

    # POST /api/seed
    if path == "/api/seed" and method == "POST":
        seed_q3_demo(live_agent=False)
        summary = get_summary_counts()
        all_commitments = commitment_store.all()
        serialized = [serialise_commitment_for_ui(c) for c in all_commitments]
        return _json_response(200, {"status": "seeded", "summary": summary, "commitments": serialized})

    return _json_response(404, {"error": f"Route not found: {method} {path}"})
