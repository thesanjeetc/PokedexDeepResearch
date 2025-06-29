import asyncio
import json
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Union, Dict

from httpx import AsyncClient
from pydantic import BaseModel, ValidationError, Field, ConfigDict

from pydantic_ai import Agent, ModelRetry, RunContext
from tools.get_pokemon_profiles import _get_pokemon_profiles
from tools.analyse_team import (
    analyze_team,
    TeamAnalysisSummary,
)


@dataclass
class Deps:
    model_config = ConfigDict(arbitrary_types_allowed=True)
    client: AsyncClient


poke_agent = Agent(
    "openai:gpt-4o",
    instructions=(
        """
      "You are a Pokémon analysis system. Your purpose is to answer questions by exclusively using the provided tools. You are forbidden from using any pre-existing knowledge.
      --- CORE DIRECTIVES ---
      MANDATORY TOOL USE: All information in your answers MUST be sourced directly from tool outputs.
      EFFICIENCY: Be efficient. When a tool accepts lists (like pokemon_names), use them to handle multiple items in one call instead of calling the tool repeatedly.
      """
    ),
    deps_type=Deps,
    retries=2,
)


@poke_agent.tool
async def get_pokemon_profiles_tool(
    ctx: RunContext[Deps],
    pokemon_names: List[str],
    data_groups: List[str],
    game_version: Optional[str] = None,
) -> dict[str, Any]:
    """Retrieves specified data profiles for one or more Pokémon, optionally filtered by game version.

    This tool is the primary method for accessing all Pokémon information. It can retrieve multiple
    data groups for multiple Pokémon in a single call.

    Args:
        pokemon_names (List[str]): A list of Pokémon names or Pokédex IDs to look up.
        data_groups (List[str], optional): The specific data groups to retrieve. If not provided,
                                           all data groups will be returned. Requesting only necessary
                                           groups is more efficient.
                                           Valid options:
                                           - 'summary': The "Pokédex Card" view. Includes identity
                                             (name, ID, types, genus) and physical_characteristics
                                             (height, weight, color, shape).
                                           - 'battle_profile': The "Trainer's Manual" view. Includes
                                             battle_stats (base stats, abilities), training_and_breeding
                                             (XP, capture/growth rates, egg groups), and evolution paths.
                                           - 'moves': The "Move Encyclopedia". A detailed, potentially large
                                             list of all learnable moves. Best used with 'game_version'.
                                           - 'ecology': The "Field Guide". A detailed, potentially large
                                             list of encounter locations. Best used with 'game_version'.
                                           - 'lore': The "Library Archive". Contains all Pokédex entries.
        game_version (str, optional): The specific game to filter results for (e.g., 'red', 'sword').
                                      This will filter the 'moves' and 'ecology' data groups to
                                      only include data relevant to that game.
    """
    return await _get_pokemon_profiles(
        ctx.deps.client, pokemon_names, data_groups, game_version
    )


@poke_agent.tool
async def analyze_team_tool(
    ctx: RunContext[Deps],
    pokemon_names: List[str],
) -> TeamAnalysisSummary:
    """Performs a holistic analysis of a Pokémon team's offensive and defensive synergy.

    This tool is the ultimate strategic advisor for competitive team building. It simultaneously
    evaluates a team's offensive coverage and its defensive vulnerabilities, providing a complete
    picture of its strengths and weaknesses. By cross-referencing offensive potential against
    defensive gaps, it moves beyond simple data lists to generate actionable, strategic insights.
    The analysis purely evaluates STAB type matchups and does not consider non-STAB moves,
    stats, or abilities.

    Use this tool to answer complex strategic questions like:
    - "My team is critically weak to Rock-type attacks. Do I have a member who can counter it?"
    - "My team has no super-effective moves against Dragon-types. Is the team at least resistant?"
    - "I have three Pokémon that can beat Water-types. Can I swap one to cover my Electric
      weakness without creating a new offensive gap?"

    Args:
        pokemon_names (List[str]): A list of Pokémon names to be analyzed as a single team.

    Returns:
        TeamSynergyReport: A master analysis object with a 360-degree view of the team.
                           The key fields include:
                           - 'defense_summary': A complete breakdown of the team's defensive profile,
                             including top threats, shared weaknesses, and resistance gaps.
                           - 'offense_summary': A complete breakdown of the team's offensive coverage,
                             highlighting redundant attackers and critical coverage gaps.
                           - 'strategic_insights': The core of the analysis. A prioritized list
                             of insights that links defensive threats to offensive answers, flagging
                             critical vulnerabilities and confirming well-covered matchups.
    """

    return await analyze_team(client=ctx.deps.client, pokemon_names=pokemon_names)
