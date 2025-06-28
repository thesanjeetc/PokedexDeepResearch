import asyncio
import json
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Union, Dict

from httpx import AsyncClient
from pydantic import BaseModel, ValidationError, Field, ConfigDict

from pydantic_ai import Agent, ModelRetry, RunContext
from tools.get_pokemon_profiles import _get_pokemon_profiles
from tools.analyse_team_defense import (
    analyze_team_defense,
    TeamDefenseSummary,
)


@dataclass
class Deps:
    model_config = ConfigDict(arbitrary_types_allowed=True)
    client: AsyncClient


poke_agent = Agent(
    "openai:gpt-4o",
    instructions=(
        "You are a Pokémon analysis system. Your purpose is to answer questions by exclusively using the provided tools. You are forbidden from using any pre-existing knowledge.\n"
        "\n"
        "--- CORE DIRECTIVES ---\n"
        "1.  **MANDATORY TOOL USE:** All information in your answers MUST be sourced directly from tool outputs.\n"
        "2.  **EFFICIENCY:** Be efficient. When a tool accepts lists (like `pokemon_names`), use them to handle multiple items in one call instead of calling the tool repeatedly.\n"
        "\n"
        "--- TOOL USAGE GUIDE ---\n"
        "You have two tools. Choose the correct one based on the user's query:\n"
        "\n"
        "1.  `get_pokemon_profiles_tool`:\n"
        "    - **WHEN TO USE:** For retrieving **raw data** about one or more Pokémon (e.g., their types, stats, abilities, moves, or Pokédex entries).\n"
        "    - **HOW TO USE:** Request only the necessary `data_groups`. If the user specifies a game, use the `game_version` parameter.\n"
        "    - **Example:** \"What are Snorlax's base stats?\" -> Use this tool with `data_groups=['battle_profile']`.\n"
        "\n"
        "2.  `analyze_defensive_synergy_tool`:\n"
        "    - **WHEN TO USE:** For **analysis and interpretation** of a team's defensive capabilities.\n"
        "    - **HOW TO USE:** Provide the list of Pokémon names that make up the team.\n"
        '    - **Example:** "What are the weaknesses of a team with Charizard and Gengar?" -> Use this tool.'
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
async def analyze_team_defense_tool(
    ctx: RunContext[Deps],
    pokemon_names: List[str],
) -> TeamDefenseSummary:
    """Analyzes a Pokémon team's defensive synergy, focusing on a deep, actionable breakdown of type matchups.

    This tool is essential for competitive team building and strategic planning. It evaluates how a team's
    types interact defensively, moving beyond simple weakness counts to provide a nuanced, prioritized
    analysis. It identifies the most severe threats (like 4x weaknesses), common vulnerabilities shared
    across the team, and areas where the team lacks any defensive coverage. The analysis purely evaluates
    type matchups and does not consider stats, abilities, or moves.

    Use this tool to answer questions like:
    - "What are the most dangerous threats to a team with Tyranitar, Metagross, and Gengar?"
    - "My team of Dragonite, Gyarados, and Charizard shares a 4x weakness to Rock. How can I see that?"
    - "Which types can my team not safely switch into? Are there any coverage gaps?"

    Args:
        pokemon_names (List[str]): A list of Pokémon names to be analyzed as a single team.

    Returns:
        TeamDefenseSummary: A structured analysis object with concise, actionable insights.
                            The key fields include:
                            - 'top_threats': A dictionary mapping the most dangerous attack types to the
                              highest damage multiplier they inflict (e.g., {'rock': 4.0, 'electric': 2.0}).
                            - 'shared_weaknesses': Maps attack types to the number of team members weak to it,
                              highlighting systemic vulnerabilities. Only includes types that affect more than one member.
                            - 'coverage_gaps': A list of types for which the team has NO resistances or immunities,
                              revealing holes in the team's defensive wall.
                            - 'pokemon_vulnerabilities': The detailed defensive profile for each individual
                              Pokémon, serving as a reference for drill-down analysis.
    """

    return await analyze_team_defense(
        client=ctx.deps.client, pokemon_names=pokemon_names
    )
