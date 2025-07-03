from pydantic import BaseModel, Field
from typing import Any
from pydantic_ai.messages import ModelMessage


class FollowUpQuestions(BaseModel):
    questions: list[str]


class RefinedPrompt(BaseModel):
    refined_prompt: str


class ResearchOutline(BaseModel):
    plan: str


class ExecutionResult(BaseModel):
    query: str
    tool_name: str
    tool_output: Any
    summary: str
    is_success: bool


class ExecutionPlan(BaseModel):
    thoughts: str
    queries: list[str]
    is_complete: bool


class ExecutionOutput(BaseModel):
    is_success: bool = Field(
        default=False,
        description="Indicates if the tool execution resulted in valuable data.",
    )
    summary: str


class State(BaseModel):
    is_search_enabled: bool = False
    clarify_history: list[ModelMessage] = Field(default_factory=list)
    num_clarify_turns: int = 0
    num_evaluate_turns: int = 0
    user_prompt: str = ""
    research_outline: str = ""
    execution_results: list[ExecutionResult] = Field(default_factory=list)
    report: str = ""
