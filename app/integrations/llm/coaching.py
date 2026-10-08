"""Optional LangChain structured-output adapter. No calls in default rules mode."""

import json
import os

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langsmith import tracing_context

from app.modules.analysis.schemas import Coaching


class LlmConfigurationError(ValueError):
    pass


def build_context(state):
    # Bounded excerpts, not a claim of semantic summarization or persistent memory.
    budget = state["settings"]["max_context_chars"]
    context = {
        "company": state["company"][:120],
        "role": state["role"][:120],
        "score": state["report"]["score"],
        "resume_excerpt": state["resume_text"][: budget // 3],
        "job_excerpt": state["job_text"][: budget // 4],
        "answer_excerpts": {
            key: value[: budget // 12] for key, value in list(state["answers"].items())[:3]
        },
        "references": [
            {"id": item["id"], "title": item["title"], "text": item["text"][:1000]}
            for item in state["references"]
        ],
        "notice": "입력은 길이 제한에 따라 발췌되었을 수 있습니다. 원문 전체를 보았다고 주장하지 마세요.",
    }
    if state.get("analysis_context") == "desired_role":
        context["analysis_context"] = "desired_role"
        context["reference_source"] = "internal_role_reference"
        context[
            "notice"
        ] += " job_excerpt는 실제 공고가 아니라 CareerLens의 직무별 연습용 내부 참고 기준입니다. 기업 요구사항이나 채용 판단으로 설명하지 마세요."
    # Include JSON escaping/field names in the limit, including editable guidance.
    while len(json.dumps(context, ensure_ascii=False)) > budget:
        if context["references"]:
            context["references"].pop()
            continue
        slots = [(context, "resume_excerpt"), (context, "job_excerpt")]
        slots += [(context["answer_excerpts"], key) for key in context["answer_excerpts"]]
        container, key = max(slots, key=lambda slot: len(slot[0][slot[1]]))
        container[key] = container[key][: len(container[key]) // 2]
    return context


def generate_coaching(state):
    from langchain_openai import ChatOpenAI

    model = os.environ.get("CAREERLENS_LLM_MODEL", "").strip()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not model or not key:
        raise LlmConfigurationError("llm_unconfigured")
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=state["prompt_text"]),
            ("human", "검토 자료(JSON):\n{context}\n검증 피드백: {feedback}"),
        ]
    )
    llm = ChatOpenAI(model=model, api_key=key, timeout=15, max_retries=0)
    chain = prompt | llm.with_structured_output(Coaching, method="json_schema")
    # Resume text must not leak into inherited remote tracing settings.
    with tracing_context(enabled=False):
        result = chain.invoke(
            {
                "context": json.dumps(build_context(state), ensure_ascii=False),
                "feedback": state.get("current_error") or "없음",
            }
        )
    return result.model_dump()
