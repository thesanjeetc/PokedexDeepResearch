from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Union

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from agents.models import (
    State,
    FollowUpQuestions,
    RefinedPrompt,
    ExecutionPlan,
    ExecutionResult,
)
from agents.agents import (
    clarify_agent,
    refine_agent,
    outline_agent,
    plan_evaluate_agent,
    execute_agent,
    report_agent,
)

import chainlit as cl


@dataclass
class Clarify(BaseNode[State]):
    user_prompt: str
    max_turns: int = 3

    async def run(self, ctx: GraphRunContext[State]) -> Union[Outline, Elicit]:
        ctx.state.num_clarify_turns += 1
        print("💡 Clarification Agent is analyzing the request...")

        if ctx.state.num_clarify_turns <= self.max_turns:
            response = await clarify_agent.run(
                self.user_prompt, message_history=ctx.state.clarify_history
            )
            ctx.state.clarify_history = response.all_messages()
        else:
            response = await refine_agent.run(
                self.user_prompt, message_history=ctx.state.clarify_history
            )
        result = response.output

        print(f"🤖 Agent response: {result}\n")

        if isinstance(result, FollowUpQuestions):
            print("❓ Agent determined more information is needed.")
            return Elicit(follow_up=result)

        if isinstance(result, RefinedPrompt):
            print("✅ Agent created a refined prompt.")
            print(f"✨ Refined Prompt: {result}\n")
            ctx.state.user_prompt = result.refined_prompt
            return Outline(prompt=result.refined_prompt)

        raise TypeError(f"Unexpected agent output type: {type(result)}")


@dataclass
class Elicit(BaseNode[State]):
    follow_up: FollowUpQuestions

    async def run(self, ctx: GraphRunContext[State]) -> Clarify:
        agent_message_content = "\n".join(f"  - {q}" for q in self.follow_up.questions)
        print(f"🤖 Agent asks:\n{agent_message_content}\n")

        await asyncio.sleep(1)
        user_response = "I'm playing Pokémon Emerald. My team is Marshtomp, and I want to beat the Elite Four."
        print(f"👤 User responds: {user_response}\n")
        return Clarify(user_prompt=user_response)


@dataclass
class Outline(BaseNode[State]):
    prompt: str

    async def run(self, ctx: GraphRunContext[State]) -> PlanEvaluate:
        print("📝 Planning agent is now taking over...")
        print(f"   Input for planning phase: {ctx.state.user_prompt}")
        response = await outline_agent.run(self.prompt)
        ctx.state.research_outline = response.output.plan
        print(f"📋 Research Plan created:\n{ctx.state.research_outline}\n")
        return PlanEvaluate()


@dataclass
class PlanEvaluate(BaseNode[State]):
    max_turns: int = 5

    async def run(self, ctx: GraphRunContext[State]) -> Union[Execute, Report]:
        if ctx.state.num_evaluate_turns >= self.max_turns:
            print(
                f"⚠️ Max turns ({self.max_turns}) reached. Proceeding to final report."
            )
            return Report()

        ctx.state.num_evaluate_turns += 1

        response = await plan_evaluate_agent.run(deps=ctx.state)
        plan: ExecutionPlan = response.output

        if plan.is_complete:
            print("✅ Research phase complete. Final thoughts from the agent:")
            print(plan.thoughts)
            return Report()
        else:
            print("🤔 Agent thoughts for the next step:")
            print(plan.thoughts)
            if plan.queries:
                print("📝 New queries to execute:")
                for i, query in enumerate(plan.queries, start=1):
                    print(f"  {i}. {query}")
                return Execute(plan=plan)
            else:
                print(
                    "⚠️ Agent decided to continue but generated no queries. Forcing report."
                )
                return Report()


@dataclass
class Execute(BaseNode[State]):
    plan: ExecutionPlan

    async def run(self, ctx: GraphRunContext[State]) -> PlanEvaluate:
        print("🔍 Execution agent is processing the plan...")
        queries = self.plan.queries
        tasks = [execute_agent.run(query, deps=ctx.state) for query in queries]
        responses = await asyncio.gather(*tasks)
        for query, response in zip(queries, responses):
            tool_message = response.all_messages()[2].parts[0]
            tool_name = tool_message.tool_name
            tool_output = tool_message.content
            print(f"🔧 Tool '{tool_name}' executed for query: {query}")
            ctx.state.execution_results.append(
                ExecutionResult(
                    query=query,
                    tool_name=tool_name,
                    tool_output=tool_output,
                    is_success=response.output.is_success,
                    summary=response.output.summary,
                )
            )

        return PlanEvaluate()


@dataclass
class Report(BaseNode[State]):
    async def run(self, ctx: GraphRunContext[State]) -> End:
        print("📊 Reporting agent is summarizing the results...")
        response = await report_agent.run(deps=ctx.state)
        ctx.state.report = response.output
        print(f"📄 Final Report:\n{ctx.state.report}\n")
        return End(data=ctx.state)


async def main():
    initial_prompt = "What Pokemon should I add next to my party?"
    print(f"👤 User (initial prompt): {initial_prompt}\n")
    initial_state = State()
    graph = Graph(nodes=(Clarify, Elicit, Outline, PlanEvaluate, Execute, Report))

    return await graph.run(Clarify(user_prompt=initial_prompt), state=initial_state)
