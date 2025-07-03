from agents.models import ExecutionResult
from pydantic_ai import format_as_xml


def format_execution_results(execution_results: list[ExecutionResult]) -> str:
    return format_as_xml(
        {
            "execution_results": [
                {
                    "query": result.query,
                    "summary": result.summary,
                }
                for result in execution_results
            ]
        },
        root_tag="results",
        item_tag="execution_result",
        indent="",
    )
