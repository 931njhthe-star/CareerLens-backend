"""Bounded, testable LangGraph workflow; rules remain the scoring authority."""

import os
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import ValidationError

from app.agent.prompts.loader import load_prompt
from app.agent.state.analysis import AnalysisState
from app.modules.analysis.schemas import Coaching
from app.integrations.llm.coaching import LlmConfigurationError, build_context, generate_coaching
from app.modules.analysis.reporting.service import analyze as rules_analyze
from app.retrieval.search.local import retrieve_guidance

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_VERSION = "1.0.0"


def validate_coaching(candidate, state):
    try:
        result = Coaching.model_validate(candidate).model_dump()
    except (ValidationError, TypeError):
        return None, "invalid_schema"
    context = build_context(state)
    evidence = [context["resume_excerpt"], *context["answer_excerpts"].values()]
    for item in result["recommendations"]:
        quote = item["evidence_quote"].strip()
        if len(quote) < 8 or not any(quote in source for source in evidence):
            return None, "ungrounded_evidence"
    if not set(result["reference_ids"]) <= {item["id"] for item in context["references"]}:
        return None, "unknown_reference"
    return result, ""


def build_graph(coach=generate_coaching, retriever=retrieve_guidance, prompts_dir=None):
    prompts_dir = prompts_dir or ROOT / "agent/prompts"

    def step(state, name, tool=None):
        return {
            "steps": state.get("steps", []) + [name],
            "tools_called": state.get("tools_called", []) + ([tool] if tool else []),
        }

    def plan(state):
        mode = state.get("mode") or os.environ.get("CAREERLENS_ANALYSIS_MODE", "rules").strip()
        result = {
            **step(state, "plan"),
            "mode": mode,
            "retry_count": 0,
            "fallback_used": False,
            "error_codes": [],
            "current_error": "",
            "candidate": None,
            "coaching": None,
        }
        try:
            text, version, settings = load_prompt(
                prompts_dir, os.environ.get("CAREERLENS_COACH_PROMPT") or None
            )
            result.update(prompt_text=text, prompt_version=version, settings=settings)
        except (OSError, ValueError, KeyError):
            result.update(
                prompt_text="",
                prompt_version="unavailable",
                settings={
                    "max_retries": 0,
                    "max_context_chars": 14000,
                    "retrieval": {"enabled": True, "top_k": 3},
                    "coaching_enabled": False,
                },
                error_codes=["prompt_invalid"],
                fallback_used=True,
            )
        if mode not in {"rules", "llm"}:
            result.update(
                mode="rules",
                error_codes=result["error_codes"] + ["invalid_mode"],
                fallback_used=True,
            )
        return result

    def retrieve(state):
        result = step(state, "retrieve")
        references = []
        if state["settings"]["retrieval"]["enabled"]:
            result["tools_called"] = state.get("tools_called", []) + ["local_guidance_search"]
            try:
                references = retriever(
                    state["role"] + " " + state["job_text"],
                    ROOT.parent / "data/knowledge/policies/career-guidance.json",
                    state["settings"]["retrieval"]["top_k"],
                )
            except (OSError, ValueError, KeyError, TypeError):
                result.update(
                    error_codes=state["error_codes"] + ["retrieval_unavailable"], fallback_used=True
                )
        result["references"] = references
        return result

    def rules(state):
        return {
            **step(state, "rules", "rule_analysis"),
            "report": rules_analyze(
                state["resume_text"],
                state["company"],
                state["role"],
                state["job_text"],
                state["answers"],
                analysis_context=state.get("analysis_context", "job_posting"),
            ),
        }

    def choose(state):
        if state["mode"] != "llm" or not state["settings"]["coaching_enabled"]:
            return "finish"
        return "coach"

    def coaching(state):
        result = step(state, "coach", "structured_coaching")
        try:
            result.update(candidate=coach(state), current_error="")
        except LlmConfigurationError:
            result.update(
                candidate=None,
                current_error="llm_unconfigured",
                error_codes=state["error_codes"] + ["llm_unconfigured"],
            )
        except Exception:
            # Provider exception messages can contain requests, keys or source text.
            result.update(
                candidate=None,
                current_error="provider_error",
                error_codes=state["error_codes"] + ["provider_error"],
            )
        return result

    def validate(state):
        result = step(state, "validate", "evidence_validation")
        if state["current_error"]:
            return result
        coaching_result, error = validate_coaching(state["candidate"], state)
        result.update(coaching=coaching_result, current_error=error)
        if error:
            result["error_codes"] = state["error_codes"] + [error]
        return result

    def decision(state):
        if not state["current_error"]:
            return "finish"
        if state["current_error"] == "llm_unconfigured":
            return "fallback"
        if state["retry_count"] < state["settings"]["max_retries"]:
            return "reflect"
        return "fallback"

    def reflect(state):
        return {**step(state, "reflect"), "retry_count": state["retry_count"] + 1}

    def fallback(state):
        return {**step(state, "fallback"), "coaching": None, "fallback_used": True}

    def finish(state):
        trace = step(state, "finish")
        report = {
            **state["report"],
            "reference_guidance": state["references"],
            "agent": {
                "workflow_version": WORKFLOW_VERSION,
                "mode": "llm_coaching" if state["coaching"] else "rules",
                "steps": trace["steps"],
                "tools_called": trace["tools_called"],
                "error_codes": state["error_codes"],
                "retry_count": state["retry_count"],
                "fallback_used": state["fallback_used"],
                "prompt_version": state["prompt_version"],
                "reference_count": len(state["references"]),
            },
        }
        if state["coaching"]:
            report["ai_coaching"] = state["coaching"]
        return {**trace, "report": report}

    graph = StateGraph(AnalysisState)
    for name, node in (
        ("plan", plan),
        ("retrieve", retrieve),
        ("rules", rules),
        ("coach", coaching),
        ("validate", validate),
        ("reflect", reflect),
        ("fallback", fallback),
        ("finish", finish),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "rules")
    graph.add_conditional_edges("rules", choose, {"coach": "coach", "finish": "finish"})
    graph.add_edge("coach", "validate")
    graph.add_conditional_edges(
        "validate", decision, {"finish": "finish", "reflect": "reflect", "fallback": "fallback"}
    )
    graph.add_edge("reflect", "coach")
    graph.add_edge("fallback", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


def analyze_with_agent(
    resume_text, company, role, job_text, answers=None, analysis_context="job_posting"
):
    with tracing_context(enabled=False):
        state = build_graph().invoke(
            {
                "resume_text": resume_text,
                "company": company,
                "role": role,
                "job_text": job_text,
                "answers": answers or {},
                "analysis_context": analysis_context,
            },
            {"recursion_limit": 16},
        )
    return state["report"]
