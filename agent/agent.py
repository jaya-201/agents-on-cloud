"""
agent.py — Multi-Agent Orchestrator (Manager → Writer ⇄ Reviewer)

Architecture:
  Manager decides phase → Writer drafts → Reviewer evaluates
       ↑                                        |
       └──────────── reject (loop) ─────────────┘
                           |
                        approve → finish

State is passed as a plain dict so it serialises cleanly to/from Lambda JSON.
"""

import json
import logging
import os
from typing import Any

import google.generativeai as genai

from agent.prompts import MANAGER_SYSTEM_PROMPT, WRITER_SYSTEM_PROMPT, REVIEWER_SYSTEM_PROMPT
from agent.tools import (
    parse_json_response,
    summarize_state,
    truncate_content,
    validate_manager_response,
    validate_reviewer_response,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ── Constants ──────────────────────────────────────────────────────────────────
MODEL = "gemini-flash-latest"
MAX_TOKENS = 4096
MAX_ITERATIONS = 5          # Safety cap: prevent infinite Writer↔Reviewer loops
APPROVAL_THRESHOLD = 7      # Reviewer score >= 7 → approve


# ── Google GenAI client (lazy init for Lambda cold-start optimisation) ────────────
_client_configured: bool = False


def _get_client() -> genai:
    global _client_configured
    if not _client_configured:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        _client_configured = True
    return genai


# ── Low-level LLM call ─────────────────────────────────────────────────────────
def _call_llm(system: str, messages: list[dict], label: str = "agent") -> str:
    """Call the Google GenAI API and return the text content of the response."""
    client = _get_client()
    logger.info("[%s] calling LLM with %d message(s)", label, len(messages))

    model = client.GenerativeModel(
        model_name=MODEL,
        system_instruction=system,
        generation_config=genai.types.GenerationConfig(max_output_tokens=MAX_TOKENS)
    )

    # Assuming messages is a list with one user message
    content = messages[0]["content"] if messages else ""
    response = model.generate_content(content)

    text = response.text
    logger.info("[%s] received %d chars", label, len(text))
    return text


# ── Agent node functions ───────────────────────────────────────────────────────

def manager_node(state: dict) -> dict:
    """
    Manager Agent: decides the next phase based on current state.
    Updates state["current_phase"] and state["manager_instruction"].
    """
    iteration = state.get("iteration_count", 0)
    logger.info("=== MANAGER NODE (iteration %d) ===", iteration)

    # Build context message for the Manager
    context_parts = [f"User request: {state['user_request']}"]

    if state.get("draft_content"):
        context_parts.append(
            f"\nCurrent draft:\n{truncate_content(state['draft_content'], 1500)}"
        )
    if state.get("review_feedback"):
        context_parts.append(f"\nReviewer feedback:\n{json.dumps(state['review_feedback'], indent=2)}")

    context_parts.append(f"\nIteration: {iteration + 1}/{MAX_ITERATIONS}")

    messages = [{"role": "user", "content": "\n".join(context_parts)}]

    raw = _call_llm(MANAGER_SYSTEM_PROMPT, messages, label="manager")
    decision = parse_json_response(raw)

    if not validate_manager_response(decision):
        raise ValueError(f"Invalid Manager response structure: {decision}")

    logger.info("Manager decision → phase=%s | reason=%s", decision["phase"], decision["reasoning"])

    state["current_phase"] = decision["phase"]
    state["manager_instruction"] = decision["instruction"]
    state["iteration_count"] = iteration + 1
    return state


def writer_node(state: dict) -> dict:
    """
    Writer Agent: produces or revises content based on Manager's instruction.
    Updates state["draft_content"].
    """
    logger.info("=== WRITER NODE ===")

    prompt_parts = [
        f"Task: {state['manager_instruction']}",
        f"Original user request: {state['user_request']}",
    ]

    if state.get("review_feedback"):
        fb = state["review_feedback"]
        prompt_parts.append(
            f"\nPrevious reviewer feedback to address:\n"
            f"Score: {fb.get('score')}/10\n"
            f"Issues: {json.dumps(fb.get('issues', []))}\n"
            f"Specific instructions: {fb.get('feedback', '')}"
        )
        if state.get("draft_content"):
            prompt_parts.append(
                f"\nYour previous draft (revise this):\n{truncate_content(state['draft_content'], 2000)}"
            )

    messages = [{"role": "user", "content": "\n\n".join(prompt_parts)}]

    draft = _call_llm(WRITER_SYSTEM_PROMPT, messages, label="writer")
    state["draft_content"] = draft
    logger.info("Writer produced %d chars", len(draft))
    return state


def reviewer_node(state: dict) -> dict:
    """
    Reviewer Agent: evaluates the Writer's draft.
    Updates state["review_feedback"] and state["approved"].
    """
    logger.info("=== REVIEWER NODE ===")

    messages = [
        {
            "role": "user",
            "content": (
                f"Original request: {state['user_request']}\n\n"
                f"Content to review:\n{state['draft_content']}"
            ),
        }
    ]

    raw = _call_llm(REVIEWER_SYSTEM_PROMPT, messages, label="reviewer")
    feedback = parse_json_response(raw)

    if not validate_reviewer_response(feedback):
        raise ValueError(f"Invalid Reviewer response structure: {feedback}")

    score = feedback.get("score", 0)
    verdict = feedback.get("verdict")
    approved = verdict == "approve" and score >= APPROVAL_THRESHOLD

    state["review_feedback"] = feedback
    state["approved"] = approved

    logger.info(
        "Reviewer verdict=%s score=%d/10 approved=%s",
        verdict, score, approved
    )
    return state


# ── Graph router ───────────────────────────────────────────────────────────────

def should_continue(state: dict) -> str:
    """
    Routing function: determines the next node after the Manager decides.

    Returns one of: "writer" | "reviewer" | "end"
    """
    phase = state.get("current_phase")
    iteration = state.get("iteration_count", 0)

    # Hard stop: prevent runaway loops
    if iteration >= MAX_ITERATIONS:
        logger.warning("Max iterations (%d) reached — forcing finish", MAX_ITERATIONS)
        return "end"

    if phase in ("draft", "revise"):
        return "writer"
    if phase == "review":
        return "reviewer"
    if phase == "finish":
        return "end"

    logger.warning("Unknown phase '%s' — ending", phase)
    return "end"


# ── Main orchestration loop ────────────────────────────────────────────────────

def run_agent(user_request: str) -> dict[str, Any]:
    """
    Entry point: run the full Manager→Writer↔Reviewer pipeline.

    Returns a result dict with:
      - final_content : the approved (or best available) content
      - approved      : whether Reviewer approved it
      - iterations    : how many loops were needed
      - review_summary: final reviewer feedback
    """
    logger.info("Starting agent pipeline for request: %s", user_request[:100])

    # Initialise graph state
    state: dict = {
        "user_request": user_request,
        "current_phase": None,
        "manager_instruction": None,
        "draft_content": None,
        "review_feedback": None,
        "approved": False,
        "iteration_count": 0,
    }

    # ── Graph execution loop ───────────────────────────────────────────────────
    while True:
        # 1. Manager decides phase
        state = manager_node(state)

        # 2. Route based on Manager decision
        next_step = should_continue(state)
        logger.info("Router → next_step=%s", next_step)

        if next_step == "end":
            break

        if next_step == "writer":
            state = writer_node(state)
            # After writing, always go to review (Manager will handle phase transition)
            # Set up for next Manager call to move to "review"
            # Override phase so Manager sees we need review next
            state["current_phase"] = "pending_review"
            # Call Manager again to transition to review phase
            state = manager_node(state)
            next_step = should_continue(state)
            if next_step != "reviewer":
                # Manager decided to finish without review — honour it
                if next_step == "end":
                    break
                continue

        if next_step == "reviewer":
            state = reviewer_node(state)
            if state["approved"]:
                logger.info("Content APPROVED — finishing pipeline")
                break
            else:
                logger.info("Content REJECTED — looping back to Writer")
                # Manager will see the feedback and issue "revise" on next iteration
                continue

    logger.info("Pipeline complete.\n%s", summarize_state(state))

    return {
        "final_content": state.get("draft_content", ""),
        "approved": state.get("approved", False),
        "iterations": state.get("iteration_count", 0),
        "review_summary": state.get("review_feedback"),
    }
