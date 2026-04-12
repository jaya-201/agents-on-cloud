"""
lambda_handler.py — AWS Lambda entry point for the Multi-Agent Orchestrator.

Trigger: API Gateway POST /run-agent
         OR direct Lambda invocation

Expected event body (JSON):
  { "prompt": "Write a technical blog post about Graph Neural Networks" }

Response (JSON):
  {
    "statusCode": 200,
    "body": {
      "final_content": "...",
      "approved": true,
      "iterations": 2,
      "review_summary": { ... }
    }
  }
"""

import json
import logging
import os
import traceback

from agent.agent import run_agent

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── CORS headers for API Gateway responses ─────────────────────────────────────
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


def _error_response(status_code: int, message: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }


def _success_response(data: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps(data),
    }


def handler(event: dict, context) -> dict:
    """
    Main Lambda handler.

    Supports two invocation modes:
    1. API Gateway proxy integration (event has 'body' key as JSON string)
    2. Direct Lambda invocation (event IS the payload)
    """
    logger.info("Lambda invoked | request_id=%s", getattr(context, "aws_request_id", "local"))
    logger.info("Event keys: %s", list(event.keys()))

    # ── Parse input ────────────────────────────────────────────────────────────
    try:
        # API Gateway wraps body as a JSON string
        if "body" in event:
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        else:
            # Direct invocation
            body = event

        prompt = body.get("prompt", "").strip()

        if not prompt:
            return _error_response(400, "Missing required field: 'prompt'")

        if len(prompt) > 5000:
            return _error_response(400, "Prompt too long (max 5000 characters)")

    except (json.JSONDecodeError, TypeError) as e:
        logger.error("Failed to parse request body: %s", e)
        return _error_response(400, f"Invalid JSON body: {str(e)}")

    # ── Validate environment ───────────────────────────────────────────────────
    if not os.environ.get("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY not set")
        return _error_response(500, "Server configuration error: missing API key")

    # ── Run the agent pipeline ─────────────────────────────────────────────────
    try:
        logger.info("Running agent for prompt: %s...", prompt[:80])
        result = run_agent(prompt)
        logger.info(
            "Agent finished | approved=%s | iterations=%d | content_length=%d",
            result["approved"],
            result["iterations"],
            len(result.get("final_content", "")),
        )
        return _success_response(result)

    except ValueError as e:
        logger.error("Validation error in agent: %s", e)
        return _error_response(422, str(e))

    except gemini_import_error_handler() as e:
        logger.error("Gemini API error: %s\n%s", e, traceback.format_exc())
        return _error_response(502, f"Upstream LLM API error: {str(e)}")

    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error: %s\n%s", e, traceback.format_exc())
        return _error_response(500, "Internal server error — check CloudWatch logs")

def gemini_import_error_handler():
    """Return the Gemini API error class if available, else a dummy."""
    try:
        from google.api_core import exceptions
        return exceptions.GoogleAPIError
    except (ImportError, AttributeError):
        return type("_NeverMatch", (Exception,), {})
