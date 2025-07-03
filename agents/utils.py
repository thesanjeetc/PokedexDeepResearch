from agents.models import ExecutionResult
from pydantic_ai import format_as_xml

from pydantic_ai.exceptions import (
    UsageLimitExceeded,
    UnexpectedModelBehavior,
    ModelHTTPError,
    AgentRunError,
)


def format_execution_results(execution_results: list[ExecutionResult]) -> str:
    return format_as_xml(
        {
            "execution_results": [
                {
                    "query": result.query,
                    "tool_name": result.tool_name,
                    "summary": result.summary,
                }
                for result in execution_results
            ]
        },
        include_root_tag=False,
        item_tag="execution_result",
        indent="",
    )


def format_execution_error(exc: Exception, query: str = "") -> str:
    if isinstance(exc, UsageLimitExceeded):
        return (
            "🚫 You've hit the usage limit for this step — either in token count or request volume.\n"
            "👉 Try simplifying the request or breaking it into smaller parts."
        )

    if isinstance(exc, UnexpectedModelBehavior):
        return (
            "🤖 The model responded in an unexpected format and couldn't be interpreted.\n"
            "🔍 Try rewording your query to be more specific or reduce ambiguity."
        )

    if isinstance(exc, ModelHTTPError):
        return (
            f"🌐 The model service responded with HTTP {exc.status_code}.\n"
            "🔁 This could be a temporary issue — you might retry in a moment."
        )

    if isinstance(exc, AgentRunError):
        return (
            "⚠️ The system couldn't complete this step due to conflicting inputs or an internal inconsistency.\n"
            "💡 Try clarifying or narrowing down your request for better results."
        )

    return (
        "❌ We ran into an unexpected problem while handling your request.\n"
        "🧹 Try simplifying or rephrasing your question."
    )
