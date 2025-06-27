import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional
from httpx import AsyncClient
from collections import defaultdict
from tools.utils import _fetch_url, pretty_print, BASE_URL
from pydantic import BaseModel, Field


async def fetch_type_list(client: AsyncClient) -> List[str]:
    data = await _fetch_url(client, f"{BASE_URL}/type/")
    return [
        entry["name"]
        for entry in data["results"]
        if int(entry["url"].rstrip("/").split("/")[-1]) <= 18
    ]


async def fetch_type_effectiveness(
    client: AsyncClient, type_id: int, all_types: List[str]
) -> Optional[Dict[str, Dict[str, float]]]:
    data = await _fetch_url(client, f"{BASE_URL}/type/{type_id}")

    type_name = data["name"]
    default = {t: 1.0 for t in all_types}
    offense = default.copy()
    defense = default.copy()

    for rel in data["damage_relations"]["double_damage_to"]:
        offense[rel["name"]] = 2.0
    for rel in data["damage_relations"]["half_damage_to"]:
        offense[rel["name"]] = 0.5
    for rel in data["damage_relations"]["no_damage_to"]:
        offense[rel["name"]] = 0.0

    for rel in data["damage_relations"]["double_damage_from"]:
        defense[rel["name"]] = 2.0
    for rel in data["damage_relations"]["half_damage_from"]:
        defense[rel["name"]] = 0.5
    for rel in data["damage_relations"]["no_damage_from"]:
        defense[rel["name"]] = 0.0

    return {type_name: {"offense": offense, "defense": defense}}


async def build_type_chart() -> Dict[str, Dict[str, Dict[str, float]]]:
    async with AsyncClient() as client:
        type_names = await fetch_type_list(client)
        results = await asyncio.gather(
            *[fetch_type_effectiveness(client, i, type_names) for i in range(1, 19)]
        )

        chart = {}
        for entry in results:
            chart.update(entry)

        with open("data/type_effectiveness_chart.json", "w", encoding="utf-8") as f:
            json.dump(chart, f, indent=2, ensure_ascii=False)
        return chart


TYPE_CHART_PATH = "data/type_effectiveness_chart.json"

with open(TYPE_CHART_PATH, "r", encoding="utf-8") as f:
    TYPE_CHART = json.load(f)
    ALL_ATTACK_TYPES = list(TYPE_CHART.keys())

from tools.get_pokemon_profiles import _get_pokemon_profiles


class PokemonVulnerabilityProfile(BaseModel):
    """Represents the defensive risk profile for a single Pokémon."""

    weakness_count: int = Field(
        description="The total number of attack types this Pokémon is weak to."
    )
    resistance_count: int = Field(
        description="The total number of attack types this Pokémon resists or is immune to."
    )
    net_vulnerability: int = Field(
        description="The difference between weakness and resistance counts (weaknesses - resistances). Higher values indicate more defensive liability."
    )


class DefensiveSynergyAnalysis(BaseModel):
    """
    A comprehensive analysis of a Pokémon team's defensive synergy.
    This schema describes the structure of the analysis output, focusing on
    team-wide weaknesses, resistances, and individual Pokémon vulnerabilities.
    """

    team_size: int = Field(description="The number of Pokémon on the team analyzed.")

    critical_weaknesses: List[str] = Field(
        description="A list of attack types that are a major threat, meaning at least half of the team is weak to them."
    )

    undefended_types: List[str] = Field(
        description="A list of attack types for which no Pokémon on the team has a resistance. These are potential coverage gaps."
    )

    weakness_severity: Dict[str, int] = Field(
        description="A dictionary mapping each attack type to the number of team members weak to it. For example, {'Fire': 2} means two Pokémon are weak to Fire-type attacks."
    )

    pokemon_vulnerability: Dict[str, PokemonVulnerabilityProfile] = Field(
        description="Maps each Pokémon's name to its detailed vulnerability profile."
    )

    total_weakness_types: int = Field(
        description="The total count of unique attack types that the team is weak to in some capacity."
    )

    total_resistance_types: int = Field(
        description="The total count of unique attack types that the team resists in some capacity."
    )


async def analyze_defensive_synergy(
    client: AsyncClient,
    pokemon_names: List[str],
):
    """
    Calculates team's defensive synergy by analyzing weaknesses and resistances
    based on Pokémon types. Returns a summary of critical weaknesses, undefended types,
    and individual Pokémon's vulnerability profiles.
    """
    team = await _get_pokemon_profiles(client, pokemon_names, ["summary"])

    team_weaknesses = defaultdict(list)
    team_resistances = defaultdict(list)

    for pokemon_name, profile in team.items():
        pokemon_types = [t.lower() for t in profile["summary"]["identity"]["types"]]

        for attack_type in TYPE_CHART:
            multiplier = 1.0
            for own_type in pokemon_types:
                multiplier *= TYPE_CHART[own_type]["defense"][attack_type]

            attack_type_cap = attack_type.capitalize()

            if multiplier > 1.0:
                team_weaknesses[attack_type_cap].append(pokemon_name)
            elif multiplier < 1.0:
                team_resistances[attack_type_cap].append(pokemon_name)

    team_size = len(team)

    weakness_severity = {
        attack_type: len(pokemon_list)
        for attack_type, pokemon_list in team_weaknesses.items()
    }

    critical_weaknesses = [
        attack_type
        for attack_type, count in weakness_severity.items()
        if count >= team_size // 2
    ]

    all_attack_types = {t.capitalize() for t in TYPE_CHART.keys()}
    undefended_types = sorted(all_attack_types - set(team_resistances.keys()))

    pokemon_vulnerability = {}
    for pokemon_name in team.keys():
        weakness_count = sum(
            pokemon_name in pokemons for pokemons in team_weaknesses.values()
        )
        resistance_count = sum(
            pokemon_name in pokemons for pokemons in team_resistances.values()
        )
        pokemon_vulnerability[pokemon_name] = PokemonVulnerabilityProfile(
            weakness_count=weakness_count,
            resistance_count=resistance_count,
            net_vulnerability=weakness_count - resistance_count,
        )

    return DefensiveSynergyAnalysis(
        team_size=team_size,
        critical_weaknesses=critical_weaknesses,
        undefended_types=undefended_types,
        weakness_severity=weakness_severity,
        pokemon_vulnerability=pokemon_vulnerability,
        total_weakness_types=len(team_weaknesses),
        total_resistance_types=len(team_resistances),
    )
