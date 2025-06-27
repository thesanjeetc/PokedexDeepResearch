import asyncio
import json
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Union, Dict

from httpx import AsyncClient
from pydantic import BaseModel, ValidationError, Field, ConfigDict

from pydantic_ai import Agent, ModelRetry, RunContext
from tools.get_pokemon_profiles import _get_pokemon_profiles
from tools.analyse_team_defense import (
    analyze_defensive_synergy,
    DefensiveSynergyAnalysis,
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
async def analyze_defensive_synergy_tool(
    ctx: RunContext[Deps],
    pokemon_names: List[str],
) -> DefensiveSynergyAnalysis:
    """Analyzes a Pokémon team's defensive strengths and weaknesses based on their types.

    This tool is essential for competitive team building and strategic planning. It takes a list
    of Pokémon and evaluates how their types work together defensively. The analysis identifies
    critical vulnerabilities (types that threaten most of the team), undefended types (types
    the team has no resistance to), and provides a risk profile for each individual Pokémon.
    It purely evaluates type matchups and does not consider stats, abilities, or moves.

    Use this tool to answer questions like:
    - "What are the biggest weaknesses of a team with Charizard, Venusaur, and Blastoise?"
    - "How well does my team of Snorlax, Gengar, and Alakazam cover its defensive bases?"
    - "Which Pokémon on my team is the most defensively vulnerable?"

    Args:
        pokemon_names (List[str]): A list of Pokémon names to be analyzed as a single team.
                                   For best results, provide a full team of up to 6 Pokémon.

    Returns:
        DefensiveSynergyAnalysis: A structured analysis object with detailed results.
                                  The key fields include:
                                  - 'critical_weaknesses': A list of types that half or more
                                    of the team is weak to. These are the most urgent threats.
                                  - 'undefended_types': Types that no one on the team resists.
                                    These represent significant defensive gaps.
                                  - 'weakness_severity': A breakdown of how many Pokémon are
                                    weak to each specific attack type.
                                  - 'pokemon_vulnerability': A profile for each Pokémon,
                                    detailing its number of weaknesses and resistances.
    """

    return await analyze_defensive_synergy(
        client=ctx.deps.client, pokemon_names=pokemon_names
    )
