from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Union

from pydantic_graph import BaseNode, End, GraphRunContext
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
from pydantic_ai.usage import UsageLimits
import chainlit as cl


# @dataclass
# class Clarify(BaseNode[State]):
#     user_prompt: str
#     max_turns: int = 3

#     async def run(self, ctx: GraphRunContext[State]) -> Union[Outline, Elicit]:
#         ctx.state.num_clarify_turns += 1
#         if ctx.state.num_clarify_turns <= self.max_turns:
#             response = await clarify_agent.run(
#                 self.user_prompt, message_history=ctx.state.clarify_history
#             )
#         else:
#             response = await refine_agent.run(
#                 self.user_prompt, message_history=ctx.state.clarify_history
#             )

#         ctx.state.clarify_history = response.all_messages()
#         result = response.output

#         if isinstance(result, FollowUpQuestions):
#             return Elicit(follow_up=result)

#         if isinstance(result, RefinedPrompt):
#             ctx.state.user_prompt = result.refined_prompt
#             return Outline(prompt=result.refined_prompt)


# @dataclass
# class Elicit(BaseNode[State]):
#     follow_up: FollowUpQuestions

#     async def run(self, ctx: GraphRunContext[State]) -> Clarify:
#         user_response = "I'm playing Pokémon Emerald. My team is Marshtomp, and I want to beat the Elite Four."
#         return Clarify(user_prompt=user_response)


@dataclass
class Outline(BaseNode[State]):
    prompt: str

    async def run(self, ctx: GraphRunContext[State]) -> PlanEvaluate:
        step = cl.Step(name="📝 Planning", type="run")
        await step.send()

        response = await outline_agent.run(self.prompt, deps=ctx.state)
        ctx.state.research_outline = response.output.plan

        await step.stream_token(f"📋 Plan:\n{ctx.state.research_outline}")
        await step.update()

        return PlanEvaluate()


@dataclass
class PlanEvaluate(BaseNode[State]):
    max_turns: int = 5

    async def run(self, ctx: GraphRunContext[State]) -> Union[Execute, Report]:
        step = cl.Step(name=f"🧠 Thinking", type="run")
        await step.send()

        if ctx.state.num_evaluate_turns >= self.max_turns:
            await step.stream_token(
                "⚠️ Max planning steps reached. Proceeding to report."
            )
            await step.update()
            return Report()

        ctx.state.num_evaluate_turns += 1

        response = await plan_evaluate_agent.run(deps=ctx.state)
        plan: ExecutionPlan = response.output

        if plan.thoughts:
            await step.stream_token(f"💭 Thoughts:\n{plan.thoughts}\n")

        if plan.is_complete:
            await step.stream_token("✅ Research complete. Generating report...")
            await step.update()
            return Report()

        if plan.queries:
            queries = "\n".join(f"- {q}" for q in plan.queries)
            await step.stream_token(f"\n📌 New Queries:\n{queries}")
            await step.update()
            return Execute(plan=plan)

        await step.stream_token("⚠️ No queries generated. Ending early.")
        await step.update()
        return Report()


@dataclass
class Execute(BaseNode[State]):
    plan: ExecutionPlan

    async def run(self, ctx: GraphRunContext[State]) -> PlanEvaluate:
        step = cl.Step(name="🔧 Executing", type="run")
        await step.send()

        queries = self.plan.queries
        tasks = [
            execute_agent.run(
                query,
                usage_limits=UsageLimits(request_limit=4),
                deps=ctx.state,
            )
            for query in queries
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for query, response in zip(queries, responses):
            tool_message = response.all_messages()[2].parts[0]
            tool_name = tool_message.tool_name
            tool_output = tool_message.content
            summary = response.output.summary

            ctx.state.execution_results.append(
                ExecutionResult(
                    query=query,
                    tool_name=tool_name,
                    tool_output=tool_output,
                    is_success=response.output.is_success,
                    summary=summary,
                )
            )

            await step.stream_token(
                f"\n\n🔍 {tool_name} ran on _{query}_:\n\n{summary}\n"
            )

        await step.update()
        return PlanEvaluate()


# @dataclass
# class Report(BaseNode[State]):
#     async def run(self, ctx: GraphRunContext[State]) -> End:
#         step = cl.Step(name="📊 Generating Report", type="run")
#         await step.send()

#         response = await report_agent.run(deps=ctx.state)
#         ctx.state.report = response.output

#         await step.stream_token("✅ Report complete.")
#         await step.update()

#         text_elements = []
#         for i, source in enumerate(ctx.state.execution_results):
#             if source.is_success:
#                 source_name = f"{source.tool_name} [{i}]"
#                 text_elements.append(
#                     cl.Text(
#                         content=source.summary,
#                         name=source_name,
#                         display="side",
#                     )
#                 )

#         source_names = [text_el.name for text_el in text_elements]
#         final_report = response.output + "\n\nSources: " + " ".join(source_names)

#         await cl.Message(content=final_report, elements=text_elements).send()
#         return End(data=ctx.state)


@dataclass
class Report(BaseNode[State]):
    async def run(self, ctx: GraphRunContext[State]) -> End:
        start_step = cl.Step(name="📊 Generating", type="run")
        await start_step.send()

        response = await report_agent.run(deps=ctx.state)
        ctx.state.report = response.output

        text_elements = []
        for i, source in enumerate(ctx.state.execution_results):
            if source.is_success:
                source_name = f"{source.tool_name} [{i}]"
                text_elements.append(
                    cl.Text(
                        content=source.summary,
                        name=source_name,
                        display="side",
                    )
                )

        source_names = [text_el.name for text_el in text_elements]
        final_report = response.output + "\n\nSources: " + " ".join(source_names)

        final_step = cl.Step(name="✅ Final Report", type="run")
        final_step.output = final_report
        final_step.elements = text_elements
        await final_step.send()

        return End(data=ctx.state)
