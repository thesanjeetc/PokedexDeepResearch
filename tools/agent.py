import asyncio
import json
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Union, Dict

from httpx import AsyncClient
from pydantic import BaseModel, ValidationError, Field, ConfigDict

from pydantic_ai import Agent, ModelRetry, RunContext
from tools.get_pokemon_profiles import _get_pokemon_profiles


@dataclass
class Deps:
    model_config = ConfigDict(arbitrary_types_allowed=True)
    client: AsyncClient


poke_agent = Agent(
    "openai:gpt-4o-mini",
    instructions=(
        "You are a world-class Pokémon expert assistant. Your primary goal is to answer user questions completely and efficiently by using your tools.\n"
        "--- TOOL USAGE STRATEGY ---\n"
        "1. For any general question about specific Pokémon (e.g., 'tell me about Pikachu', 'how does Eevee evolve?'), you **MUST** use the `get_pokemon_profiles` tool. It is your most powerful tool.\n"
    ),
    deps_type=Deps,
    retries=2,
)


@poke_agent.tool
async def get_pokemon_profiles_tool(
    ctx: RunContext[Deps], names: List[str]
) -> dict[str, Any]:
    """The primary tool for all-in-one information about multiple known Pokémon.
    Args:
    names (List[str]): The exact names or Pokédex IDs of the Pokémon.
    """
    return await _get_pokemon_profiles(ctx.deps.client, names)
