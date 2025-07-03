import chainlit as cl
from agents.models import State
from agents.graph import Outline, PlanEvaluate, Execute, Report
from pydantic_graph import Graph, GraphRunContext
from agents.agents import clarify_agent, refine_agent
from agents.models import FollowUpQuestions, RefinedPrompt

graph = Graph(nodes=(Outline, PlanEvaluate, Execute, Report))


async def run_clarify_turn(user_input: str, state: State, max_turns: int = 3):
    state.num_clarify_turns += 1

    if state.num_clarify_turns <= max_turns:
        response = await clarify_agent.run(
            user_input, message_history=state.clarify_history
        )
    else:
        response = await refine_agent.run(
            user_input, message_history=state.clarify_history
        )

    state.clarify_history = response.all_messages()
    result = response.output

    if isinstance(result, FollowUpQuestions):
        questions = "\n".join(f"- {q}" for q in result.questions)
        await cl.Message(
            content=f"🤖 I need a bit more info:\n{questions}", author="Clarify Agent"
        ).send()
        return False
    elif isinstance(result, RefinedPrompt):
        await cl.Message(
            content=f"✅ Refined Prompt:\n\n**{result.refined_prompt}**",
            author="Clarify Agent",
        ).send()
        state.user_prompt = result.refined_prompt
        return True


@cl.on_chat_start
async def on_chat_start():
    await cl.Message("👋 Hi! What would you like help researching today?").send()
    cl.user_session.set("state", State())


@cl.on_message
async def on_message(msg: cl.Message):
    state = cl.user_session.get("state")

    if await run_clarify_turn(msg.content, state):
        await graph.run(start_node=Outline(prompt=state.user_prompt), state=state)
