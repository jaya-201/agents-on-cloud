"""
tools.py — Utility tools available to agents in the pipeline.
These are simple, self-contained functions the orchestrator can call.
"""

import json
import re
from typing import Any


def parse_json_response(text: str) -> dict:
    """
    Safely parse a JSON response from an LLM.
    Handles markdown code fences and minor formatting issues.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\n?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from LLM response: {e}\nRaw text: {text[:300]}")


def build_messages(system_prompt: str, conversation: list[dict]) -> tuple[str, list[dict]]:
    """
    Separate the system prompt from the messages list for the LLM API.
    Returns (system_prompt, messages_list).
    """
    return system_prompt, conversation


def summarize_state(state: dict) -> str:
    """
    Create a compact human-readable summary of the current graph state.
    Useful for logging and debugging.
    """
    lines = [
        f"Phase      : {state.get('current_phase', 'N/A')}",
        f"Iterations : {state.get('iteration_count', 0)}",
        f"Has Draft  : {'Yes' if state.get('draft_content') else 'No'}",
        f"Has Review : {'Yes' if state.get('review_feedback') else 'No'}",
        f"Approved   : {state.get('approved', False)}",
    ]
    return "\n".join(lines)


def truncate_content(content: str, max_chars: int = 2000) -> str:
    """
    Truncate long content for inclusion in prompts, preserving start and end.
    """
    if len(content) <= max_chars:
        return content
    half = max_chars // 2
    return content[:half] + "\n\n...[content truncated]...\n\n" + content[-half:]


def validate_manager_response(response: dict) -> bool:
    """Validate that Manager's JSON response has required fields."""
    required = {"phase", "instruction", "reasoning"}
    return required.issubset(response.keys()) and response["phase"] in {
        "draft", "review", "revise", "finish"
    }


def validate_reviewer_response(response: dict) -> bool:
    """Validate that Reviewer's JSON response has required fields."""
    required = {"verdict", "score", "strengths", "issues", "feedback"}
    return required.issubset(response.keys()) and response["verdict"] in {"approve", "reject"}
