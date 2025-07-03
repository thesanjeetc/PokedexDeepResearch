from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Union, cast

from pydantic import BaseModel, Field
from pydantic_ai import Agent
import logfire

import os
from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("LOGFIRE_TOKEN"):
    logfire.configure()
    logfire.instrument_pydantic_ai()

from pydantic_ai.agent import Agent, RunContext, Tool
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.models.openai import OpenAIModel
from agents.models import (
    State,
    FollowUpQuestions,
    RefinedPrompt,
    ResearchOutline,
    ExecutionPlan,
    ExecutionOutput,
)

from agents.prompts import (
    CLARIFY_PROMPT,
    REFINE_PROMPT,
    OUTLINE_PROMPT,
    EXECUTE_PROMPT,
    PLAN_EVALUATE_PROMPT,
    REPORT_PROMPT,
    PLAN_EVALUATE_WEB_PROMPT,
    EXECUTE_WEB_PROMPT,
    OUTLINE_WEB_PROMPT,
)
from tools.get_pokemon_profiles import get_pokemon_profiles
from tools.analyse_pokemon_team import analyse_pokemon_team
from tools.search_pokemon_by_criteria import search_pokemon_by_criteria
from tools.search_pokemon_web import search_pokemon_web
from agents.utils import format_execution_results

model = OpenAIModel("gpt-4o")
thinking_model = OpenAIModel("o3")

clarify_agent = Agent(
    model,
    output_type=FollowUpQuestions | RefinedPrompt,
    system_prompt=CLARIFY_PROMPT,
)

refine_agent = Agent(
    model,
    output_type=RefinedPrompt,
    system_prompt=REFINE_PROMPT,
)

outline_agent = Agent(
    model,
    output_type=ResearchOutline,
    system_prompt=OUTLINE_PROMPT,
    deps_type=State,
)

plan_evaluate_agent = Agent(
    thinking_model,
    output_type=ExecutionPlan,
    deps_type=State,
    retries=1,
)

MAX_TOOL_RETRIES = 3


async def toggle_websearch(
    ctx: RunContext[bool], tool_defs: list[ToolDefinition]
) -> Union[list[ToolDefinition], None]:
    if ctx.deps.is_search_enabled is False:
        return [
            tool_def for tool_def in tool_defs if tool_def.name != "search_pokemon_web"
        ]
    return tool_defs


execute_agent = Agent(
    model,
    output_type=ExecutionOutput,
    deps_type=State,
    tools=[
        Tool(get_pokemon_profiles, max_retries=MAX_TOOL_RETRIES),
        Tool(analyse_pokemon_team, max_retries=MAX_TOOL_RETRIES),
        Tool(search_pokemon_by_criteria, max_retries=MAX_TOOL_RETRIES),
        Tool(search_pokemon_web, max_retries=MAX_TOOL_RETRIES),
    ],
    prepare_tools=toggle_websearch,
    retries=1,
)

report_agent = Agent(
    thinking_model, output_type=str, deps_type=State, system_prompt=REPORT_PROMPT
)

basic_agent = Agent(
    OpenAIModel("chatgpt-4o-latest"),
    output_type=str,
    system_prompt="You are a helpful Pokemon assistant.",
)


@outline_agent.system_prompt
def dynamic_outline_prompt(ctx: RunContext[State]) -> str:
    return OUTLINE_WEB_PROMPT if ctx.deps.is_search_enabled else OUTLINE_PROMPT


@plan_evaluate_agent.system_prompt
def dynamic_plan_evaluate_prompt(ctx: RunContext[State]) -> str:
    CORE_PROMPT = (
        PLAN_EVALUATE_WEB_PROMPT if ctx.deps.is_search_enabled else PLAN_EVALUATE_PROMPT
    )
    return CORE_PROMPT.format(
        user_prompt=ctx.deps.user_prompt,
        research_outline=ctx.deps.research_outline,
        execution_results=format_execution_results(ctx.deps.execution_results),
    )


@execute_agent.system_prompt
def dynamic_execute_prompt(ctx: RunContext[State]) -> str:
    CORE_PROMPT = EXECUTE_WEB_PROMPT if ctx.deps.is_search_enabled else EXECUTE_PROMPT
    return CORE_PROMPT.format(user_prompt=ctx.deps.user_prompt)


@report_agent.system_prompt
def dynamic_report_prompt(ctx: RunContext[State]) -> str:
    return REPORT_PROMPT.format(
        user_prompt=ctx.deps.user_prompt,
        research_outline=ctx.deps.research_outline,
        execution_results=format_execution_results(ctx.deps.execution_results),
    )
