from agents.models import ExecutionResult
from pydantic_ai import format_as_xml


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
